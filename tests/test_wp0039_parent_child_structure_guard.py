from __future__ import annotations

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER, parse_ai_smc_decision
from smc_desk.perception.structure_narrative import build_structure_narrative, derive_strict_htf_bias


def _structure_break(object_id: str, direction: str, confirmed_at: str, scope: str, broken_price: float) -> dict:
    return {
        "object_id": object_id,
        "object_type": "structure_break",
        "break_type": "BOS",
        "direction": direction,
        "confirmed_at": confirmed_at,
        "structure_scope": scope,
        "price_low": broken_price - 10.0,
        "price_high": broken_price + 10.0,
        "evidence": {
            "structure_scope": scope,
            "broken_price": str(broken_price),
            "is_unconfirmed_probe": False,
        },
    }


def _parent_child_evidence_pack() -> dict:
    candidates = {
        "12h": {
            "structure_breaks": [
                _structure_break("12h_bearish_external_bos", "bearish", "2026-07-02T00:00:00Z", "external", 62272.07),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
        "1h": {
            "structure_breaks": [
                _structure_break("1h_bullish_external_choch", "bullish", "2026-07-02T12:00:00Z", "external", 61334.0),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
        "15m": {
            "structure_breaks": [
                _structure_break("15m_bullish_external_bos", "bullish", "2026-07-03T08:45:00Z", "external", 61850.0),
                _structure_break("15m_bearish_internal_choch", "bearish", "2026-07-03T09:00:00Z", "internal", 61612.0),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
    }
    return {
        "detector_candidates": candidates,
        "structure_narrative": build_structure_narrative(
            candidates,
            raw_bias={"12h": "bearish", "1h": "bullish", "15m": "bullish"},
        ),
    }


def _payload(*, direction: str, final_bias: str, thesis: str, evidence: list[str] | None = None) -> dict:
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "THESIS_ONLY",
        "setup_grade": "THESIS_ONLY",
        "direction": direction,
        "setup_model": "parent_child_context_review",
        "bias_summary": {
            "daily": "unknown",
            "4h": "unknown",
            "1h": "bullish",
            "final_bias": final_bias,
            "evidence": evidence or [],
        },
        "active_range": {
            "timeframe": "1h",
            "high": None,
            "low": None,
            "equilibrium": None,
            "price_location": "unknown",
            "source": None,
            "evidence": [],
        },
        "liquidity_story": {
            "obvious_liquidity": [],
            "swept_liquidity": [],
            "unswept_liquidity": [],
            "narrative": thesis,
        },
        "displacement_assessment": {
            "direction": "none",
            "quality": "none",
            "structure_broken": False,
            "evidence_object_ids": [],
            "summary": "No execution displacement promoted.",
        },
        "active_poi": {
            "poi_id": None,
            "timeframe": None,
            "kind": None,
            "direction": "unknown",
            "price_low": None,
            "price_high": None,
            "freshness": None,
            "evidence_object_ids": [],
            "summary": "No active POI.",
        },
        "entry_plan": {
            "entry_ready": False,
            "entry_timeframe": "15m",
            "refinement_timeframe": "5m",
            "entry_price": None,
            "entry_zone_low": None,
            "entry_zone_high": None,
            "signal_type": None,
            "required_confirmation": [],
            "evidence_object_ids": [],
            "summary": "No entry.",
        },
        "stop_loss_plan": {
            "stop_price": None,
            "structural_invalidation_price": None,
            "source": None,
            "buffer_notes": None,
            "evidence_object_ids": [],
            "summary": "No stop.",
        },
        "target_plan": {
            "targets": [],
            "model_completion_liquidity_id": None,
            "summary": "No target.",
        },
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "No RR."},
        "invalidation": {
            "invalidation_price": None,
            "condition": "No executable invalidation.",
            "source": None,
            "evidence_object_ids": [],
        },
        "annotation_plan": {
            "chart_template": "context_chart",
            "show_trade_box": False,
            "labels": [{"text": thesis, "kind": "context", "timeframe": "12h"}],
            "levels": [],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {
            "active_range_check": "not_applicable",
            "poi_check": "not_applicable",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [],
            "remaining_uncertainties": [],
        },
        "final_thesis": thesis,
    }


def test_12h_parent_conflict_forces_mixed_bias() -> None:
    assert derive_strict_htf_bias({"12h": "bearish", "1h": "bullish"}) == "mixed"


def test_structure_narrative_names_parent_child_conflict() -> None:
    pack = _parent_child_evidence_pack()
    parent_child = pack["structure_narrative"]["parent_child_context"]
    assert parent_child["status"] == "PARENT_CHILD_CONFLICT"
    assert parent_child["parent_timeframe"] == "12h"
    assert parent_child["parent_bias"] == "bearish"
    assert parent_child["child_timeframe"] == "1h"
    assert parent_child["child_bias"] == "bullish"
    assert "pullback/recovery" in parent_child["thesis_sentence"]


def test_validator_rejects_clean_bullish_summary_when_12h_parent_is_bearish() -> None:
    decision = parse_ai_smc_decision(
        _payload(
            direction="bullish",
            final_bias="bullish",
            thesis="BTC is bullish after the 1H break.",
        )
    )
    result = validate_ai_smc_decision(decision, _parent_child_evidence_pack())
    codes = {issue.code for issue in result.issues}
    assert result.status == "REVIEW_REQUIRED"
    assert "parent_child_conflict_direction_not_mixed" in codes
    assert "parent_child_conflict_not_acknowledged" in codes


def test_validator_accepts_explicit_parent_child_mixed_thesis() -> None:
    thesis = (
        "12h bearish parent structure while 1h bullish child recovery/pullback trades inside parent context; "
        "therefore BTCUSDT is mixed and thesis-only until one side confirms."
    )
    decision = parse_ai_smc_decision(
        _payload(
            direction="mixed",
            final_bias="mixed",
            thesis=thesis,
            evidence=[thesis],
        )
    )
    result = validate_ai_smc_decision(decision, _parent_child_evidence_pack())
    assert result.status == "VALIDATED"
