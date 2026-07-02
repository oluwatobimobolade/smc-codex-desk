from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from smc_desk.colleague.wp0020_gauntlet import TIMEFRAMES, render_v2_story_charts


def _df() -> pd.DataFrame:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for index in range(80):
        ts = start + timedelta(minutes=15 * index)
        close = price + (1 if index % 2 else -0.5)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": price,
                "high": max(price, close) + 1,
                "low": min(price, close) - 1,
                "close": close,
                "volume": 1000,
            }
        )
        price = close
    return pd.DataFrame(rows)


def _valid_snapshot() -> dict:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    return {
        "decision_time": now.isoformat(),
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
            "current_as_of": now.isoformat(),
        },
        "structure_breaks": [],
        "fvgs": [],
        "liquidity_levels": [],
        "sweeps": [],
        "order_blocks": [],
        "inducements": [],
        "poi_grade_fvgs": [],
        "candle_count": 80,
        "last_close": now.isoformat(),
        "last_price": "100.0",
    }


def _cognitive_output() -> dict:
    return {
        "symbol": "BTCUSDT",
        "final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
        "final_action": "NO_SIGNAL",
        "watch_state": {
            "final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
            "final_action": "NO_SIGNAL",
            "direction": "bearish",
            "active_poi": None,
            "poi_selection": {
                "status": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
                "parent_scope_pois": [
                    {
                        "timeframe": "1h",
                        "kind": "supply",
                        "price_low": "1000",
                        "price_high": "1010",
                        "rejection_reason": "above protected high",
                    }
                ],
            },
        },
        "execution_readiness": {"state": "HTF_MODEL_FORMING", "confidence": 0.42},
        "inducement_continuation": {"state": "POSSIBLE_INDUCEMENT", "confidence": 0.48},
        "structure_hierarchy": {
            tf: {
                "external_bias": "bearish",
                "structure_phase": "retracement_inside_bearish_external_range",
                "depth_status": "sufficient_research_depth",
                "protected_high": "115",
                "protected_low": "90",
                "dealing_range": {
                    "range_high": "115",
                    "range_low": "90",
                    "equilibrium_50": "102.5",
                },
            }
            for tf in TIMEFRAMES
        },
        "truth_report": {"timeframe_summaries": []},
        "authority": {"live_execution": "disabled"},
    }


def test_story_chart_manifest_declares_official_clean_mode(tmp_path):
    cognitive = _cognitive_output()
    cognitive["perception_by_tf"] = {tf: _valid_snapshot() for tf in TIMEFRAMES}
    dfs = {tf: _df() for tf in TIMEFRAMES}

    manifest = render_v2_story_charts(
        timeframe_dfs=dfs,
        symbol="BTCUSDT",
        cognitive_result=cognitive,
        output_dir=tmp_path,
    )

    assert manifest["status"] == "PASS"
    assert manifest["mode"] == "story"
    assert manifest["story_mode_contract"]["raw_internal_events_hidden"] is True
    assert manifest["story_mode_contract"]["raw_detector_objects_hidden"] is True
    assert manifest["story_mode_contract"]["far_invalid_pois_note_only"] is True
    assert manifest["story_mode_contract"]["daily_shallow_blocks_ltf_poi_authority"] is True
