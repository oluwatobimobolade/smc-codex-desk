from __future__ import annotations

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER, parse_ai_smc_decision
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.decision.active_range_resolver import resolve_active_range_authority


def _range_df() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=180, freq="1h", tz="UTC")
    rows = []
    for i, ts in enumerate(timestamps):
        base = 100.0 + (i % 7) * 0.08
        rows.append(
            {
                "timestamp": ts,
                "open": base,
                "high": base + 0.7,
                "low": base - 0.7,
                "close": base + 0.05,
                "volume": 1000 + i,
            }
        )
    rows[5]["high"] = 180.0
    rows[6]["low"] = 40.0
    rows[145]["high"] = 112.0
    rows[146]["close"] = 108.0
    rows[165]["low"] = 96.0
    rows[166]["close"] = 100.0
    rows[-1]["close"] = 100.5
    return pd.DataFrame(rows)


def _decision_payload() -> dict:
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "WATCH_ONLY",
        "setup_grade": "C",
        "direction": "bearish",
        "setup_model": "observe_only_context_watch",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": []},
        "active_range": {
            "timeframe": "1h",
            "high": 112.0,
            "low": 96.0,
            "equilibrium": 104.0,
            "price_location": "discount",
            "source": "protected_swing_pair",
            "range_id": "range1",
            "protected_high": 112.0,
            "protected_low": 96.0,
            "width_atr": 8.0,
            "max_allowed_width_atr": 24.0,
            "evidence_object_ids": ["h1", "l1"],
            "evidence": ["Active range selected from recent alternating swing structure."],
        },
        "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": "Watch only."},
        "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": "None."},
        "active_poi": {"poi_id": None, "timeframe": None, "kind": None, "direction": "unknown", "price_low": None, "price_high": None, "freshness": None, "evidence_object_ids": [], "summary": "No POI."},
        "entry_plan": {"entry_ready": False, "entry_timeframe": "15m", "refinement_timeframe": "5m", "entry_price": None, "entry_zone_low": None, "entry_zone_high": None, "signal_type": None, "required_confirmation": [], "evidence_object_ids": [], "summary": "No entry."},
        "stop_loss_plan": {"stop_price": None, "structural_invalidation_price": None, "source": None, "buffer_notes": None, "evidence_object_ids": [], "summary": "No stop."},
        "target_plan": {"targets": [], "model_completion_liquidity_id": None, "summary": "No target."},
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "No RR."},
        "invalidation": {"invalidation_price": 112.0, "condition": "Watch invalidation only.", "source": "range_high", "evidence_object_ids": []},
        "annotation_plan": {"chart_template": "watch_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": REASONING_ORDER},
        "self_review": {
            "active_range_check": "passed",
            "poi_check": "not_applicable",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [],
            "remaining_uncertainties": [],
        },
        "final_thesis": "Watch only.",
    }


def test_active_range_resolver_ignores_dataset_extremes():
    df = _range_df()
    authority = resolve_active_range_authority(symbol="BTCUSDT", timeframe_dfs={"1h": df})
    selected = authority["selected_range"]
    assert authority["status"] == "RESOLVED_ACTIVE_RANGE"
    assert selected["range_high"] < 130.0
    assert selected["range_low"] > 80.0
    assert selected["not_source"] == "ohlcv_summary_high_low"


def test_active_range_uses_latest_execution_price_to_invalidate_htf_range():
    htf = _range_df().rename(columns={})
    htf["timestamp"] = pd.date_range("2026-01-01", periods=len(htf), freq="4h", tz="UTC")
    htf.iloc[-1, htf.columns.get_loc("close")] = 100.5
    ltf = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-31 00:00", tz="UTC")],
            "open": [114.0],
            "high": [115.5],
            "low": [113.5],
            "close": [115.0],
            "volume": [1000],
        }
    )
    authority = resolve_active_range_authority(
        symbol="BTCUSDT",
        timeframe_dfs={"15m": ltf, "4h": htf},
        preferred_timeframes=("4h",),
    )
    assert authority["status"] == "RANGE_UNRESOLVED_REVIEW_REQUIRED"
    assert authority["selected_range"] is None
    assert authority["rejected_ranges"][0]["current_price"] == 115.0
    assert authority["rejected_ranges"][0]["status"] in {
        "REJECTED_NO_BRACKETING_SWING_PAIR",
        "REJECTED_RANGE_TOO_WIDE",
    }


def test_active_range_never_uses_one_outside_candle_as_both_swing_legs():
    timestamps = pd.date_range("2026-01-01", periods=40, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 40,
            "high": [100.4] * 40,
            "low": [99.6] * 40,
            "close": [100.0] * 40,
            "volume": [1000] * 40,
        }
    )
    df.loc[20, "high"] = 110.0
    df.loc[20, "low"] = 90.0

    authority = resolve_active_range_authority(
        symbol="EURJPY",
        timeframe_dfs={"1h": df},
        preferred_timeframes=("1h",),
    )

    assert authority["status"] == "RANGE_UNRESOLVED_REVIEW_REQUIRED"
    assert authority["selected_range"] is None
    recent = authority["rejected_ranges"][0]["recent_pivots"]
    assert {pivot["index"] for pivot in recent} == {20}


def test_evidence_pack_carries_active_range_authority():
    df = _range_df()
    pack = build_smc_evidence_pack(symbol="BTCUSDT", timeframe_dfs={"1h": df})
    assert pack["active_range_authority"]["schema"] == "active_range_authority_v1"
    assert pack["active_range_authority"]["selected_range"]["source"] == "protected_swing_pair"


def test_validator_rejects_ohlcv_summary_active_range_source():
    payload = _decision_payload()
    payload["active_range"]["source"] = "ohlcv_summary_high_low"
    payload["active_range"]["evidence"] = ["1h OHLCV summary from evidence pack"]
    decision = parse_ai_smc_decision(payload)
    result = validate_ai_smc_decision(decision, {"detector_candidates": {}})
    assert result.status == "REVIEW_REQUIRED"
    assert any(issue.code == "active_range_summary_source_forbidden" for issue in result.issues)


def test_validator_rejects_range_that_disagrees_with_authority():
    payload = _decision_payload()
    decision = parse_ai_smc_decision(payload)
    result = validate_ai_smc_decision(
        decision,
        {
            "detector_candidates": {},
            "active_range_authority": {
                "schema": "active_range_authority_v1",
                "status": "RESOLVED_ACTIVE_RANGE",
                "selected_range": {
                    "status": "RESOLVED_ACTIVE_RANGE",
                    "timeframe": "1h",
                    "range_high": 108.0,
                    "range_low": 98.0,
                    "width_atr": 7.0,
                    "max_width_atr": 24.0,
                },
            },
        },
    )
    assert result.status == "REVIEW_REQUIRED"
    assert any(issue.code == "active_range_mismatch_authority" for issue in result.issues)


def test_validator_rejects_failed_ai_self_review():
    payload = _decision_payload()
    payload["self_review"]["active_range_check"] = "failed"
    decision = parse_ai_smc_decision(payload)
    result = validate_ai_smc_decision(decision, {"detector_candidates": {}})
    assert result.status == "REVIEW_REQUIRED"
    assert any(issue.code == "ai_self_review_failed" for issue in result.issues)
