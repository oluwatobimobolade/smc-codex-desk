from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smc_desk.colleague.wp0020_gauntlet import reconcile_engine_vs_tradingview
from smc_desk.data.schemas import Candle
from smc_desk.data.truth_validator import validate_market_truth
from smc_desk.decision.contradiction_resolver import resolve_timeframe_contradictions
from smc_desk.decision.refusal_engine import evaluate_refusal
from smc_desk.decision.uncertainty_engine import score_uncertainty
from smc_desk.perception.regime_engine import classify_market_regime


def _step(timeframe: str) -> timedelta:
    return {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }[timeframe]


def _candles(
    *,
    timeframe: str = "15m",
    count: int = 40,
    start: datetime = datetime(2026, 6, 1, tzinfo=timezone.utc),
    symbol: str = "BTCUSDT",
) -> list[Candle]:
    rows = []
    step = _step(timeframe)
    price = Decimal("100")
    for index in range(count):
        open_time = start + index * step
        close = price + Decimal("0.5")
        rows.append(
            Candle(
                venue="BINANCE",
                instrument=symbol,
                timeframe=timeframe,
                open_time=open_time,
                close_time=open_time + step,
                open=price,
                high=close + Decimal("1"),
                low=price - Decimal("1"),
                close=close,
                volume=Decimal("100"),
                trade_count=10,
                is_closed=True,
                is_complete=True,
                contains_gap=False,
                source_event_start=open_time,
                source_event_end=open_time + step,
            )
        )
        price = close
    return rows


def _decision(candles: list[Candle]) -> datetime:
    return candles[-1].close_time


def _issue_codes(candles: list[Candle], timeframe: str = "15m") -> set[str]:
    report = validate_market_truth({timeframe: candles}, _decision(candles), expected_instrument="BTCUSDT")
    return {issue.code for issue in report.issues}


def test_missing_duplicate_out_of_order_and_unfinalized_candles_are_refused():
    missing = _candles()
    missing.pop(5)
    assert "missing_data_gap" in _issue_codes(missing)

    duplicate = _candles()
    duplicate.insert(8, duplicate[7])
    assert "duplicate_timestamp" in _issue_codes(duplicate)
    assert "non_monotonic_timestamp" in _issue_codes(duplicate)

    out_of_order = _candles()
    out_of_order[10], out_of_order[11] = out_of_order[11], out_of_order[10]
    assert "non_monotonic_timestamp" in _issue_codes(out_of_order)

    unfinalized = _candles()
    decision_time = unfinalized[-2].close_time
    report = validate_market_truth({"15m": unfinalized}, decision_time, expected_instrument="BTCUSDT")
    refusal = evaluate_refusal(truth_report=report)
    assert "unfinalized_candle" in {issue.code for issue in report.issues}
    assert refusal.final_action == "REFUSE_PERCEPTION"
    assert refusal.signal_allowed is False


def test_htf_ltf_conflicts_collapse_to_no_signal():
    bullish_htf_bearish_ltf = resolve_timeframe_contradictions(
        {"1d": "bullish", "4h": "bullish", "1h": "bullish", "15m": "bearish"}
    )
    bearish_htf_bullish_ltf = resolve_timeframe_contradictions(
        {"1d": "bearish", "4h": "bearish", "1h": "bearish", "15m": "bullish"}
    )
    htf_conflict = resolve_timeframe_contradictions({"1d": "bullish", "4h": "bearish", "1h": "bearish"})
    truth = validate_market_truth({"15m": _candles()}, _decision(_candles()), expected_instrument="BTCUSDT")
    regime = classify_market_regime(_candles(count=40))

    for contradiction in (bullish_htf_bearish_ltf, bearish_htf_bullish_ltf, htf_conflict):
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
        assert contradiction.outcome in {"WAIT", "INVALIDATE_ALL"}
        assert refusal.final_action == "NO_SIGNAL"
        assert refusal.signal_allowed is False


def test_low_confidence_regime_and_visual_mismatch_do_not_force_signal(tmp_path):
    candles = _candles(count=10)
    truth = validate_market_truth({"15m": candles}, _decision(candles), expected_instrument="BTCUSDT")
    regime = classify_market_regime(candles)
    contradiction = resolve_timeframe_contradictions({"1d": "bullish", "4h": "bullish", "1h": "bullish"})
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
    visual = reconcile_engine_vs_tradingview(
        engine_chart_manifest={"status": "PASS"},
        tradingview_manifest={"status": "FAILED", "screenshots": {}, "tradingview_used_as_market_truth": False},
        output_dir=tmp_path,
    )

    assert regime.should_downgrade
    assert refusal.final_action == "NO_SIGNAL"
    assert refusal.signal_allowed is False
    assert visual["status"] == "REVIEW_REQUIRED"
    assert visual["market_truth_changed"] is False


def test_incomplete_tradingview_screenshots_are_context_mismatch(tmp_path):
    screenshot = tmp_path / "btc_15m.png"
    screenshot.write_bytes(b"fake-png")

    visual = reconcile_engine_vs_tradingview(
        engine_chart_manifest={"status": "PASS"},
        tradingview_manifest={
            "status": "PASS",
            "screenshots": {"15": str(screenshot)},
            "tradingview_used_as_market_truth": False,
        },
        output_dir=tmp_path / "reconcile",
    )

    assert visual["status"] == "VISUAL_CONTEXT_UNVERIFIED"
    assert visual["review_required"] is True
    assert visual["context_mismatch"] is False
    assert visual["market_truth_changed"] is False
    assert set(visual["missing_timeframes"]) == {"1h", "4h", "1d"}
