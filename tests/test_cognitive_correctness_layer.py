from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from smc_desk.colleague.decision_memory_graph import (
    build_decision_memory_record,
    load_decision_memory,
    update_decision_outcome,
)
from smc_desk.colleague.orchestrator_v2 import run_colleague_brain_v2
from smc_desk.data.schemas import Candle
from smc_desk.data.truth_validator import validate_market_truth
from smc_desk.decision.contradiction_resolver import resolve_timeframe_contradictions
from smc_desk.decision.refusal_engine import evaluate_refusal
from smc_desk.decision.uncertainty_engine import score_uncertainty
from smc_desk.perception.regime_engine import classify_market_regime


def _step(timeframe: str) -> timedelta:
    return {
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }[timeframe]


def _candles(
    *,
    timeframe: str = "15m",
    count: int = 80,
    start: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc),
    symbol: str = "BTCUSDT",
    trend: float = 1.0,
    contains_gap_at: int | None = None,
    is_closed: bool = True,
) -> list[Candle]:
    rows = []
    step = _step(timeframe)
    price = 100.0
    for index in range(count):
        open_time = start + index * step
        open_price = price
        close_price = price + trend + (0.15 if index % 3 == 0 else -0.05)
        high = max(open_price, close_price) + 0.6
        low = min(open_price, close_price) - 0.6
        rows.append(
            Candle(
                venue="BINANCE",
                instrument=symbol,
                timeframe=timeframe,
                open_time=open_time,
                close_time=open_time + step,
                open=Decimal(str(round(open_price, 4))),
                high=Decimal(str(round(high, 4))),
                low=Decimal(str(round(low, 4))),
                close=Decimal(str(round(close_price, 4))),
                volume=Decimal("100"),
                trade_count=10,
                is_closed=is_closed,
                is_complete=is_closed,
                contains_gap=contains_gap_at == index,
                source_event_start=open_time,
                source_event_end=open_time + step,
            )
        )
        price = close_price
    return rows


def _all_timeframes(symbol: str = "BTCUSDT") -> dict[str, list[Candle]]:
    return {
        "15m": _candles(timeframe="15m", count=90, symbol=symbol),
        "1h": _candles(timeframe="1h", count=80, symbol=symbol),
        "4h": _candles(timeframe="4h", count=70, symbol=symbol),
        "1d": _candles(timeframe="1d", count=60, symbol=symbol),
    }


def _decision_time(candles: list[Candle]) -> datetime:
    return candles[-1].close_time


def test_truth_validator_passes_clean_closed_candles():
    candles = {"15m": _candles()}
    report = validate_market_truth(candles, _decision_time(candles["15m"]), expected_instrument="BTCUSDT")
    assert report.status == "PASS"
    assert not report.refuse_perception


def test_truth_validator_rejects_missing_gap_and_unclosed_candles():
    candles = {"15m": _candles(contains_gap_at=5, is_closed=True)}
    report = validate_market_truth(candles, _decision_time(candles["15m"]), expected_instrument="BTCUSDT")
    assert report.status == "REFUSE_PERCEPTION"
    assert "candle_contains_gap" in {issue.code for issue in report.issues}

    unclosed = {"15m": _candles(is_closed=False)}
    report = validate_market_truth(unclosed, _decision_time(unclosed["15m"]), expected_instrument="BTCUSDT")
    assert {"candle_not_closed", "candle_not_complete"} <= {issue.code for issue in report.issues}


def test_truth_validator_rejects_provider_ohlc_mismatch():
    primary = {"15m": _candles()}
    alternate_rows = list(primary["15m"])
    changed = alternate_rows[-1].model_copy(update={"close": Decimal("150")})
    alternate_rows[-1] = changed
    report = validate_market_truth(
        primary,
        _decision_time(primary["15m"]),
        expected_instrument="BTCUSDT",
        provider_feeds={"primary": primary, "alternate": {"15m": alternate_rows}},
    )
    assert report.status == "REFUSE_PERCEPTION"
    assert "provider_ohlc_mismatch" in {issue.code for issue in report.issues}


def test_regime_engine_returns_required_schema_and_downgrades_short_history():
    assessment = classify_market_regime(_candles(count=90, trend=1.2))
    payload = assessment.to_dict()
    assert payload["structure_regime"] in {"trending", "ranging", "transitional"}
    assert payload["volatility_regime"] in {"compression", "expansion", "exhaustion"}
    assert payload["liquidity_regime"] in {"sweep-dominant", "accumulation", "distribution"}
    assert 0 <= payload["confidence"] <= 1

    short = classify_market_regime(_candles(count=10))
    assert short.should_downgrade


def test_contradiction_resolver_align_wait_and_invalidate_all():
    aligned = resolve_timeframe_contradictions({"1d": "bullish", "4h": "bullish", "1h": "bullish", "15m": "bullish"})
    assert aligned.outcome == "ALIGN"

    wait = resolve_timeframe_contradictions({"1d": "bearish", "4h": "bearish", "1h": "bearish", "15m": "bullish"})
    assert wait.outcome == "WAIT"

    invalid = resolve_timeframe_contradictions({"1d": "bullish", "4h": "bearish", "1h": "bearish"})
    assert invalid.outcome == "INVALIDATE_ALL"


def test_uncertainty_and_refusal_block_low_confidence():
    candles = {"15m": _candles(count=10)}
    truth = validate_market_truth(candles, _decision_time(candles["15m"]), expected_instrument="BTCUSDT")
    regime = classify_market_regime(candles["15m"])
    contradiction = resolve_timeframe_contradictions({})
    uncertainty = score_uncertainty(
        truth_report=truth,
        regime_assessment=regime,
        contradiction_resolution=contradiction,
        perception_by_tf={},
    )
    refusal = evaluate_refusal(
        truth_report=truth,
        regime_assessment=regime,
        contradiction_resolution=contradiction,
        uncertainty_assessment=uncertainty,
    )
    assert uncertainty.final_verdict == "NO_SIGNAL"
    assert refusal.final_action == "NO_SIGNAL"
    assert not refusal.signal_allowed


def test_orchestrator_v2_refuses_bad_truth_before_perception(monkeypatch, tmp_path):
    class ExplodingPerception:
        def __init__(self, *args, **kwargs):
            raise AssertionError("perception must not be constructed when truth fails")

    monkeypatch.setattr("smc_desk.colleague.orchestrator_v2.PerceptionEngineV2", ExplodingPerception)
    candles = _all_timeframes()
    candles["15m"] = _candles(timeframe="15m", contains_gap_at=3)
    result = run_colleague_brain_v2(
        candles_by_timeframe=candles,
        decision_time=_decision_time(candles["15m"]),
        symbol="BTCUSDT",
        memory_path=str(tmp_path / "memory.jsonl"),
    )
    assert result.refusal.final_action == "REFUSE_PERCEPTION"
    assert result.perception_by_tf == {}
    assert load_decision_memory(tmp_path / "memory.jsonl")


def test_orchestrator_v2_clean_path_observe_only_and_writes_memory(tmp_path):
    candles = _all_timeframes()
    decision_time = max(rows[-1].close_time for rows in candles.values())
    result = run_colleague_brain_v2(
        candles_by_timeframe=candles,
        decision_time=decision_time,
        symbol="BTCUSDT",
        memory_path=str(tmp_path / "memory.jsonl"),
    )
    payload = result.to_dict()
    assert payload["truth_report"]["status"] == "PASS"
    assert payload["perception_status"] == "completed"
    assert payload["authority"]["live_execution"] == "disabled"
    assert payload["final_action"] in {"OBSERVE_ONLY", "NO_SIGNAL"}
    assert load_decision_memory(tmp_path / "memory.jsonl")[0]["schema_version"] == "decision_memory_graph.v1"


def test_decision_memory_graph_outcome_update(tmp_path):
    path = tmp_path / "memory.jsonl"
    record = build_decision_memory_record(
        symbol="BTCUSDT",
        decision_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        market_state_snapshot={"15m": {"last_price": "100"}},
        regime={"confidence": 0.7},
        fvg_state={"total": 1},
        contradiction_result={"outcome": "ALIGN"},
        final_decision={"final_action": "OBSERVE_ONLY"},
    )
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert update_decision_outcome(path, decision_id=record["decision_id"], outcome="FAIL", correction={"reason": "missed_regime_shift"})
    updated = load_decision_memory(path)[0]
    outcome_nodes = [node for node in updated["nodes"] if node["node_type"] == "later_outcome"]
    assert outcome_nodes[0]["payload"]["outcome"] == "FAIL"
