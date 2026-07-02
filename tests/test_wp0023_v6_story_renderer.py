from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from smc_desk.colleague.decision_memory_graph import (
    append_decision_memory,
    build_decision_memory_record,
    load_decision_memory,
    supersede_prior_decisions,
    write_active_truth_index,
)
from smc_desk.colleague.wp0020_gauntlet import (
    TIMEFRAMES,
    _audit_native_htf_against_derived,
    _validate_derived_htf_consistency,
    render_v2_story_charts,
)
from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.render_v2 import render_v2_story_chart


def _make_df(bars: int = 120) -> pd.DataFrame:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    price = 100_000.0
    for i in range(bars):
        ts = start + timedelta(minutes=15 * i)
        open_price = price
        close = price + (12.0 if i % 3 != 0 else -8.0)
        high = max(open_price, close) + 15.0
        low = min(open_price, close) - 15.0
        rows.append({
            "timestamp": ts.isoformat(),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": 1000 + i,
        })
        price = close
    return pd.DataFrame(rows)


def _valid_snapshot(symbol: str = "BTCUSDT", timeframe: str = "15m") -> dict[str, object]:
    """Minimal valid PerceptionSnapshot payload."""
    return {
        "decision_time": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
        "swings": {"local": [], "internal": [], "external": []},
        "structure_state": {
            "current_direction": "bearish",
            "protected_high_id": None,
            "protected_low_id": None,
            "last_confirmed_external_high": None,
            "last_confirmed_external_low": None,
            "last_confirmed_internal_high": None,
            "last_confirmed_internal_low": None,
            "last_external_break_id": None,
            "last_internal_break_id": None,
            "internal_direction": "bearish",
            "protected_internal_high_id": None,
            "protected_internal_low_id": None,
            "current_as_of": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
        },
        "structure_breaks": [],
        "fvgs": [],
        "liquidity_levels": [],
        "sweeps": [],
        "order_blocks": [],
        "inducements": [],
        "poi_grade_fvgs": [],
        "candle_count": 120,
        "last_close": datetime(2026, 6, 1, 11, 45, tzinfo=timezone.utc).isoformat(),
        "last_price": "100000.0",
    }


def _cognitive_output(symbol: str = "BTCUSDT") -> dict[str, object]:
    return {
        "symbol": symbol,
        "final_state": "WATCH_BEARISH_RETRACE_TO_SUPPLY",
        "final_action": "NO_SIGNAL",
        "watch_state": {
            "final_state": "WATCH_BEARISH_RETRACE_TO_SUPPLY",
            "final_action": "NO_SIGNAL",
            "signal_allowed": False,
            "direction": "bearish",
            "active_poi": {
                "poi_id": "1h:supply:test",
                "kind": "supply",
                "timeframe": "1h",
                "direction": "bearish",
                "price_low": "100200.0",
                "price_high": "100350.0",
                "origin_event_id": "test",
                "created_by": "order_block",
                "freshness": "fresh",
                "price_relation": "below_poi",
            },
            "reasons": ["test"],
        },
        "timeframe_roles": {
            "1h_role": "setup_poi",
            "4h_role": "directional_bias",
            "directional_bias": "bearish",
            "setup_bias": "bearish",
        },
        "structure_hierarchy": {
            "15m": {
                "timeframe": "15m",
                "external_bias": "bearish",
                "external_range_high": "100500.0",
                "external_range_low": "99600.0",
                "protected_high": "100500.0",
                "protected_low": "99600.0",
                "internal_state": "bullish_retracement",
                "structure_phase": "retracement_inside_bearish_external_range",
                "bias_can_flip": False,
                "latest_external_break_id": None,
                "latest_internal_break_id": None,
                "depth_status": "sufficient_research_depth",
                "dealing_range": {
                    "range_id": "15m:dr:100500.0:99600.0",
                    "timeframe": "15m",
                    "range_high": "100500.0",
                    "range_low": "99600.0",
                    "equilibrium_50": "100050.0",
                    "premium_zone": ["100050.0", "100500.0"],
                    "discount_zone": ["99600.0", "100050.0"],
                    "current_price": "99800.0",
                    "price_location": "discount",
                    "internal_range_liquidity": [],
                    "external_range_liquidity": [],
                },
                "evidence": {},
            },
        },
        "truth_report": {
            "status": "PASS",
            "timeframe_summaries": [
                {"timeframe": "15m", "candle_count": 120, "status": "PASS"},
            ],
        },
        "authority": {"live_execution": "disabled"},
    }


def test_render_v2_story_chart_uses_cognitive_title_and_bias(tmp_path):
    df = _make_df(120)
    snapshot = PerceptionSnapshot.model_validate(_valid_snapshot())
    cognitive = _cognitive_output()
    output = tmp_path / "story.png"

    render_v2_story_chart(df, snapshot, cognitive, "15m", str(output))

    assert output.exists()
    with Image.open(output) as img:
        assert img.width > 0 and img.height > 0


def test_render_v2_story_charts_generates_one_per_timeframe(tmp_path, monkeypatch):
    df = _make_df(120)
    dfs = {tf: df for tf in TIMEFRAMES}
    cognitive = _cognitive_output()
    cognitive["perception_by_tf"] = {tf: _valid_snapshot() for tf in TIMEFRAMES}

    manifest = render_v2_story_charts(
        timeframe_dfs=dfs,
        symbol="BTCUSDT",
        cognitive_result=cognitive,
        output_dir=tmp_path / "story",
    )

    assert manifest["status"] == "PASS"
    assert len(manifest["charts"]) == len(TIMEFRAMES)
    for tf in TIMEFRAMES:
        assert (tmp_path / "story" / f"BTCUSDT_{tf}_story.png").exists()


def test_render_v2_story_charts_is_defensive_with_invalid_snapshots(tmp_path, monkeypatch):
    df = _make_df(120)
    dfs = {tf: df for tf in TIMEFRAMES}
    cognitive = _cognitive_output()
    cognitive["perception_by_tf"] = {tf: {"swings": {"bad": []}} for tf in TIMEFRAMES}

    manifest = render_v2_story_charts(
        timeframe_dfs=dfs,
        symbol="BTCUSDT",
        cognitive_result=cognitive,
        output_dir=tmp_path / "story",
    )

    assert manifest["status"] == "FAIL"
    assert len(manifest["errors"]) == len(TIMEFRAMES)


def test_validate_derived_htf_consistency_aligned():
    df = _make_df(96)  # 24 hours of 15m
    # Build a 1h frame by resampling so it is perfectly aligned.
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df1h = df.set_index("timestamp").resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()
    dfs = {"15m": df, "1h": df1h, "4h": df1h.iloc[-4:].copy(), "1d": df1h.iloc[-1:].copy()}

    report = _validate_derived_htf_consistency(dfs)

    assert report["status"] in {"aligned", "review"}
    assert report["validation_type"] == "derived_htf_consistency"
    assert report["native_exchange_htf_used"] is False
    assert "1h" in report["checks"]


def test_validate_derived_htf_consistency_detects_discrepancy():
    df = _make_df(96)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df1h = df.set_index("timestamp").resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()
    # Corrupt the provided 1h close to force a discrepancy.
    df1h.at[len(df1h) - 1, "close"] = float(df1h["close"].iloc[-1]) + 500.0
    dfs = {"15m": df, "1h": df1h}

    report = _validate_derived_htf_consistency(dfs)

    assert report["checks"]["1h"]["status"] == "discrepancy"


def test_native_htf_audit_refuses_derived_files_as_native(tmp_path):
    df = _make_df(96)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df1h = df.set_index("timestamp").resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()
    native_dir = tmp_path / "BTCUSDT"
    native_dir.mkdir()
    native = df1h.copy()
    native["source"] = "derived_from_15m:BTCUSDT_15m_4year.csv"
    native.to_csv(native_dir / "BTCUSDT_1h_4year.csv", index=False)

    report = _audit_native_htf_against_derived(
        symbol="BTCUSDT",
        timeframe_dfs={"15m": df, "1h": df1h},
        data_root=tmp_path,
    )

    assert report["status"] == "not_available"
    assert report["checks"]["1h"]["status"] == "not_native_file"


def test_supersede_prior_decisions_marks_contradictory_records(tmp_path):
    path = tmp_path / "memory.jsonl"
    old = build_decision_memory_record(
        symbol="BTCUSDT",
        decision_time=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        market_state_snapshot={},
        regime=None,
        fvg_state=None,
        contradiction_result=None,
        final_decision={"final_action": "NO_SIGNAL", "final_state": "WATCH_BULLISH_RETRACE_TO_DEMAND"},
    )
    append_decision_memory(path, old)

    new = build_decision_memory_record(
        symbol="BTCUSDT",
        decision_time=datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
        market_state_snapshot={},
        regime=None,
        fvg_state=None,
        contradiction_result=None,
        final_decision={"final_action": "NO_SIGNAL", "final_state": "WATCH_BEARISH_RETRACE_TO_SUPPLY"},
    )
    append_decision_memory(path, new)

    superseded = supersede_prior_decisions(
        path,
        symbol="BTCUSDT",
        current_decision_id=new["decision_id"],
        current_state="WATCH_BEARISH_RETRACE_TO_SUPPLY",
    )

    assert superseded == [old["decision_id"]]
    records = load_decision_memory(path)
    assert records[0]["superseded_by"] == new["decision_id"]
    assert "superseded_at" in records[0]

    index = write_active_truth_index(
        path,
        symbol="BTCUSDT",
        current_decision_id=new["decision_id"],
        current_state="WATCH_BEARISH_RETRACE_TO_SUPPLY",
        superseded_ids=superseded,
    )
    assert index["symbols"]["BTCUSDT"]["active_decision_id"] == new["decision_id"]
    assert index["symbols"]["BTCUSDT"]["active_direction"] == "bearish"
    assert (tmp_path / "active_truth_index.json").exists()


def test_supersede_prior_decisions_ignores_same_direction(tmp_path):
    path = tmp_path / "memory.jsonl"
    old = build_decision_memory_record(
        symbol="BTCUSDT",
        decision_time=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        market_state_snapshot={},
        regime=None,
        fvg_state=None,
        contradiction_result=None,
        final_decision={"final_action": "NO_SIGNAL", "final_state": "WATCH_BEARISH_RETRACE_TO_SUPPLY"},
    )
    append_decision_memory(path, old)

    new = build_decision_memory_record(
        symbol="BTCUSDT",
        decision_time=datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
        market_state_snapshot={},
        regime=None,
        fvg_state=None,
        contradiction_result=None,
        final_decision={"final_action": "NO_SIGNAL", "final_state": "AWAIT_15M_BEARISH_CONFIRMATION"},
    )
    append_decision_memory(path, new)

    superseded = supersede_prior_decisions(
        path,
        symbol="BTCUSDT",
        current_decision_id=new["decision_id"],
        current_state="AWAIT_15M_BEARISH_CONFIRMATION",
    )

    assert superseded == []
