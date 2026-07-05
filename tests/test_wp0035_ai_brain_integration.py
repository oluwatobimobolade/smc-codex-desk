from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER, parse_ai_smc_decision
from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest, StubAISMCProvider
from smc_desk.colleague.orchestrator_v3 import assert_official_report_uses_ai_brain, run_ai_smc_orchestrator_v3
from smc_desk.data.historical_backfill import build_context_depth_report, fetch_historical_closed_ohlcv
from smc_desk.eval.ai_smc_gold_evaluator import compare_ai_output_to_human_labels
from smc_desk.eval.gold_set_loader import GoldChartCase, load_gold_chart_cases
from smc_desk.rendering.smc_trader_annotation_renderer import build_smc_trader_annotation_scene


def _df(rows: int = 40, timeframe: str = "15min") -> pd.DataFrame:
    freq = "1D" if timeframe == "1d" else timeframe
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq=freq, tz="UTC"),
            "open": [100 + (i % 10) * 0.1 for i in range(rows)],
            "high": [101 + (i % 10) * 0.1 for i in range(rows)],
            "low": [99 - (i % 5) * 0.1 for i in range(rows)],
            "close": [100 - (i % 7) * 0.1 for i in range(rows)],
            "volume": [1000 + i for i in range(rows)],
        }
    )


def _timeframe_dfs() -> dict[str, pd.DataFrame]:
    return {"15m": _df(80, "15min"), "1h": _df(80, "1h"), "4h": _df(80, "4h"), "1d": _df(80, "1d")}


def _candidates() -> dict:
    return {
        "15m": {
            "sweeps": [{"object_id": "sweep1", "side": "buy_side", "price": 102.0, "direction": "bearish"}],
            "structure_breaks": [{"object_id": "break1", "direction": "bearish", "price": 98.0}],
            "fvgs": [{"object_id": "fvg1", "direction": "bearish", "price_low": 99.6, "price_high": 100.4}],
            "order_blocks": [{"object_id": "poi1", "direction": "bearish", "price_low": 100.0, "price_high": 101.0}],
            "liquidity_levels": [{"object_id": "liq1", "side": "sell_side", "price": 95.0}],
        }
    }


def _payload() -> dict:
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "TRADE_PLAN_READY",
        "setup_grade": "A",
        "direction": "bearish",
        "setup_model": "buy_side_sweep_to_bearish_continuation",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": ["context"]},
        "active_range": {"timeframe": "1h", "high": 103.0, "low": 95.0, "equilibrium": 99.0, "price_location": "premium", "evidence": ["range"]},
        "liquidity_story": {
            "obvious_liquidity": [{"liquidity_id": "bsl1", "side": "buy_side", "price": 102.0, "label": "equal highs"}],
            "swept_liquidity": [{"liquidity_id": "sweep1", "side": "buy_side", "price": 102.0, "label": "buy-side sweep", "evidence_object_ids": ["sweep1"]}],
            "unswept_liquidity": [{"liquidity_id": "liq1", "side": "sell_side", "price": 95.0, "label": "sell-side target", "evidence_object_ids": ["liq1"]}],
            "narrative": "Buy-side sweep into bearish displacement toward sell-side liquidity.",
        },
        "displacement_assessment": {"direction": "bearish", "quality": "clean", "structure_broken": True, "evidence_object_ids": ["break1"], "summary": "Clean bearish displacement."},
        "active_poi": {"poi_id": "poi1", "timeframe": "15m", "kind": "supply", "direction": "bearish", "price_low": 100.0, "price_high": 101.0, "freshness": "fresh", "evidence_object_ids": ["poi1"], "summary": "Active supply."},
        "entry_plan": {"entry_ready": True, "entry_timeframe": "15m", "refinement_timeframe": "5m", "entry_price": 100.5, "mapped_entry_price": 100.5, "entry_zone_low": 100.0, "entry_zone_high": 101.0, "entry_anchor": "poi1", "signal_type": "supply rejection", "required_confirmation": ["reject"], "evidence_object_ids": ["poi1"], "summary": "Ready."},
        "stop_loss_plan": {"stop_price": 102.0, "mapped_stop_price": 102.0, "stop_anchor": "above_sweep_high", "structural_invalidation_price": 102.0, "source": "above supply", "buffer_notes": "structural", "evidence_object_ids": ["sweep1"], "summary": "SL equals invalidation."},
        "target_plan": {"targets": [{"price": 95.0, "mapped_target_price": 95.0, "target_anchor": "liq1", "label": "TP1", "timeframe": "1h", "reason": "model-completion liquidity", "evidence_object_ids": ["liq1"]}], "model_completion_liquidity_id": "liq1", "summary": "Target sell-side liquidity."},
        "rr_status": {"rr": 3.3333, "minimum_rr": 3.0, "pass_rr": True, "notes": "3R+."},
        "invalidation": {"invalidation_price": 102.0, "mapped_invalidation_price": 102.0, "invalidation_anchor": "above_sweep_high", "condition": "Acceptance above supply.", "source": "supply_high", "evidence_object_ids": ["sweep1"]},
        "annotation_plan": {
            "chart_template": "trade_plan_chart",
            "show_trade_box": True,
            "labels": [
                {"text": "Bearish HTF context", "kind": "context"},
                {"text": "Buy-side swept", "kind": "sweep", "price": 102.0},
                {"text": "Active supply", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
                {"text": "Trade plan ready", "kind": "state"},
            ],
            "levels": [
                {"label": "Supply", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
                {"label": "Entry", "kind": "entry", "price": 100.5},
                {"label": "SL", "kind": "stop", "price": 102.0},
                {"label": "TP1", "kind": "target", "price": 95.0},
            ],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {
            "active_range_check": "passed",
            "poi_check": "passed",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [],
            "remaining_uncertainties": [],
        },
        "final_thesis": "Validated bearish plan.",
    }


def _watch_payload() -> dict:
    payload = _payload()
    payload["official_state"] = "WAIT_FOR_RETRACE_TO_SUPPLY"
    payload["entry_plan"]["entry_ready"] = False
    payload["entry_plan"]["entry_price"] = None
    payload["stop_loss_plan"]["stop_price"] = None
    payload["target_plan"]["targets"] = []
    payload["target_plan"]["model_completion_liquidity_id"] = None
    payload["rr_status"] = {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "Watch only."}
    payload["annotation_plan"]["chart_template"] = "watch_chart"
    payload["annotation_plan"]["show_trade_box"] = False
    payload["annotation_plan"]["levels"] = [{"label": "Supply watch", "kind": "poi", "price_low": 100.0, "price_high": 101.0}]
    return payload


def _real_provider(payload=None, calls=None):
    def complete(request: LLMCompletionRequest):
        if calls is not None:
            calls.append(request)
        return payload or _payload()

    return CallableAISMCProvider(complete, provider_name="local_real_reasoning", model_name="manual-ai-json", provider_mode="MANUAL_AI_ASSISTED_JSON")


def test_orchestrator_calls_ai_smc_brain(tmp_path):
    calls = []
    result = run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(),
        provider=_real_provider(calls=calls),
        output_dir=tmp_path,
        detector_candidates=_candidates(),
        enforce_minimum_depth=False,
    )
    assert result.report["ai_brain_used"] is True
    assert result.report["official_decision_source"] == "AISMCTraderBrainValidated"
    assert calls and "required_reasoning_order" in calls[0].prompt


def test_orchestrator_rejects_legacy_authority_for_official_output():
    with pytest.raises(AssertionError):
        assert_official_report_uses_ai_brain(
            {
                "official_decision_source": "legacy_smc_narrative_authority",
                "legacy_narrative_authority_allowed_for_official_output": True,
            }
        )


def test_real_provider_must_be_injected_for_ai_pass(tmp_path):
    with pytest.raises(ValueError, match="provider"):
        run_ai_smc_orchestrator_v3(
            symbol="BTCUSDT",
            timeframe_dfs=_timeframe_dfs(),
            provider=None,
            output_dir=tmp_path,
            detector_candidates=_candidates(),
            enforce_minimum_depth=False,
        )


def test_stub_provider_marks_run_as_not_real_reasoning(tmp_path):
    result = run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(),
        provider=StubAISMCProvider(_payload()),
        output_dir=tmp_path,
        detector_candidates=_candidates(),
        enforce_minimum_depth=False,
    )
    assert result.status == "NOT_REAL_AI_REASONING"
    assert result.report["provider"]["metadata"]["warning"] == "NOT_REAL_AI_REASONING - STUB_PROVIDER"


def test_ai_brain_receives_chart_images(tmp_path):
    calls = []
    run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(),
        provider=_real_provider(calls=calls),
        output_dir=tmp_path,
        detector_candidates=_candidates(),
        enforce_minimum_depth=False,
    )
    assert calls[0].chart_images
    assert set(calls[0].chart_images) == {"1d", "4h", "1h", "15m"}


def test_ai_brain_receives_evidence_pack(tmp_path):
    calls = []
    run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(),
        provider=_real_provider(calls=calls),
        output_dir=tmp_path,
        detector_candidates=_candidates(),
        enforce_minimum_depth=False,
    )
    assert calls[0].evidence_pack["schema"] == "smc_evidence_pack_v1"
    assert calls[0].evidence_hash == calls[0].evidence_pack["provenance"]["pack_hash"]


def test_validator_hard_issue_strips_trade_plan():
    payload = _payload()
    payload["target_plan"]["targets"][0]["price"] = 103.0
    decision = parse_ai_smc_decision(payload)
    result = validate_ai_smc_decision(
        decision,
        {
            "detector_candidates": _candidates(),
        },
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.official_decision["official_state"] == "REVIEW_REQUIRED"
    assert result.official_decision["entry_plan"]["entry_price"] is None
    assert result.official_decision["stop_loss_plan"]["stop_price"] is None
    assert result.official_decision["target_plan"]["targets"] == []
    kinds = {level["kind"] for level in result.official_decision["annotation_plan"]["levels"]}
    assert not {"entry", "stop", "target"}.intersection(kinds)


def test_official_renderer_uses_validated_ai_annotation_plan():
    decision = parse_ai_smc_decision(_payload())
    result = validate_ai_smc_decision(decision, {"detector_candidates": _candidates()})
    scene = build_smc_trader_annotation_scene(result)
    assert scene["source"] == "ValidatedAISMCDecision"
    assert scene["labels"] == result.official_decision["annotation_plan"]["labels"]


def test_watch_state_cannot_draw_trade_box():
    decision = parse_ai_smc_decision(_watch_payload())
    result = validate_ai_smc_decision(decision, {"detector_candidates": _candidates()})
    scene = build_smc_trader_annotation_scene(result)
    assert scene["show_trade_box"] is False
    assert scene["chart_template"] == "watch_chart"


def test_trade_ready_requires_entry_sl_tp_rr():
    decision = parse_ai_smc_decision(_payload())
    result = validate_ai_smc_decision(decision, {"detector_candidates": _candidates()})
    assert result.status == "VALIDATED"
    official = result.official_decision
    assert official["entry_plan"]["entry_price"] == 100.5
    assert official["stop_loss_plan"]["stop_price"] == 102.0
    assert official["target_plan"]["targets"]
    assert official["rr_status"]["rr"] >= 3.0


def _klines(start: int, count: int, interval_ms: int = 900_000):
    rows = []
    for i in range(start, start + count):
        open_ms = i * interval_ms
        close_ms = open_ms + interval_ms - 1
        rows.append([open_ms, "100", "101", "99", "100", "10", close_ms, "0", 1, "0", "0", "0"])
    return rows


def test_historical_backfill_paginates_beyond_1500(tmp_path):
    calls = []
    server_time = 3000 * 900_000

    def fetcher(symbol, interval, limit, end_time_ms):
        calls.append(end_time_ms)
        if end_time_ms is None:
            return _klines(500, 1500), server_time
        return _klines(0, 500), server_time

    result = fetch_historical_closed_ohlcv(
        symbol="BTCUSDT",
        interval="15m",
        required_candles=1600,
        fetcher=fetcher,
        cache_dir=tmp_path,
    )
    assert len(result.dataframe) == 1600
    assert result.manifest["page_count"] == 2
    assert len(calls) == 2


def test_backfill_excludes_current_forming_candle():
    server_time = 10 * 900_000
    rows = _klines(0, 10)
    forming = [10 * 900_000, "100", "101", "99", "100", "10", 11 * 900_000, "0", 1, "0", "0", "0"]

    def fetcher(symbol, interval, limit, end_time_ms):
        return [*rows, forming], server_time

    result = fetch_historical_closed_ohlcv(symbol="BTCUSDT", interval="15m", required_candles=10, fetcher=fetcher)
    assert len(result.dataframe) == 10
    assert result.dataframe["timestamp"].max() < pd.to_datetime(forming[0], unit="ms", utc=True)


def test_backfill_verifies_monotonic_timestamps():
    server_time = 10 * 900_000

    def fetcher(symbol, interval, limit, end_time_ms):
        rows = _klines(0, 5)
        rows[3][0] = rows[3][0] + 900_000
        return rows, server_time

    with pytest.raises(ValueError):
        fetch_historical_closed_ohlcv(symbol="BTCUSDT", interval="15m", required_candles=5, fetcher=fetcher)


def test_htf_depth_warning_when_daily_shallow():
    report = build_context_depth_report({"1d": _df(100, "1d")})
    assert report["1d"]["context_depth_warning"] is True
    assert report["1d"]["authority_adjustment"] == "reduce_confidence_or_review_required"


def test_gold_set_loader_requires_human_labels(tmp_path):
    case = {
        "case_id": "c1",
        "symbol": "BTCUSDT",
        "decision_time": "2026-01-01T00:00:00Z",
        "chart_images": {"1d": "d.png", "4h": "4h.png", "1h": "1h.png", "15m": "15m.png"},
        "human_smc_labels": {},
        "expected_state": "WAIT_FOR_RETRACE_TO_SUPPLY",
        "expected_direction": "bearish",
    }
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError, match="human_smc_labels"):
        load_gold_chart_cases(path)


def test_gold_evaluator_compares_ai_output_to_human_labels():
    case = GoldChartCase(
        case_id="c1",
        symbol="BTCUSDT",
        decision_time="2026-01-01T00:00:00Z",
        chart_images={"1d": "d.png", "4h": "4h.png", "1h": "1h.png", "15m": "15m.png"},
        human_smc_labels={"setup": "bearish continuation"},
        expected_setup_grade="A",
        expected_state="TRADE_PLAN_READY",
        expected_direction="bearish",
        expected_poi={"price_low": 100.0, "price_high": 101.0},
        expected_invalidation={"price": 102.0},
        expected_target={"price": 95.0},
    )
    result = compare_ai_output_to_human_labels(official_decision=_payload(), gold_case=case)
    assert result["status"] == "PASS"
    assert result["score"] == 1.0
