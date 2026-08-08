"""Tests for the deterministic validators (step 7, programme §28).

Pins:
  * A clean, fully-grounded interpretation is certified.
  * An evidence_id not in the candidate pool is an ERROR (abstain).
  * A break citing a future confirming_candle_time is a BLOCK (not certified).
  * A temporal-order violation (protected point closes after the break it
    protects) is a BLOCK.
  * The child-cannot-overwrite-parent invariant is a BLOCK.
  * A protected+broken lifecycle contradiction is a BLOCK.
  * An accepted break without displacement evidence is an ERROR.
  * A narrative with a price/time claim and no nearby evidence is a BLOCK.
  * abstention_requested flips certified off and abstained on.
"""
from __future__ import annotations

import pytest

from smc_desk.validation import certify_interpretation, validate_interpretation
from smc_desk.validation.evidence import check_evidence_grounding, collect_pool_ids
from smc_desk.validation.invariants import check_invariants
from smc_desk.validation.narrative import check_narrative_grounding
from smc_desk.validation.temporal import check_future_data, check_temporal_ordering


def _case():
    return {
        "candidate_objects": {
            "15m": {"swings": [
                {"object_id": "c1", "confirmed_at": "2026-01-05T12:00:00Z", "timeframe": "15m", "pivot_price": 100.0, "lifecycle": "CANDIDATE"},
                {"object_id": "s10", "confirmed_at": "2026-01-05T08:00:00Z", "timeframe": "15m", "pivot_price": 99.0, "lifecycle": "STRUCTURAL"},
                {"object_id": "pp1", "confirmed_at": "2026-01-05T07:00:00Z", "timeframe": "15m", "pivot_price": 98.0, "lifecycle": "PROTECTED"},
            ]},
        },
        "formal_structure_graph": {},
    }


def _interp():
    return {
        "accepted_breaks": [
            {"object_id": "br1", "timeframe": "15m", "direction": "bullish",
             "origin_object_id": "s10",
             "breaking_candidate_id": "c1", "accepted": True,
             "displacement_evidence_ids": ["c1"], "confirming_candle_time": "2026-01-05T12:00:00Z"},
        ],
        "protected_point": {"object_id": "pp1", "timeframe": "15m"},
        "summary": "bullish break accepted",
    }


def test_clean_interpretation_is_certified():
    res = certify_interpretation(_interp(), _case(), decision_time="2026-01-05T13:00:00Z")
    assert res["certified"] is True
    assert res["abstained"] is False
    assert res["summary"]["blocks"] == 0
    assert res["summary"]["errors"] == 0


def test_unknown_evidence_id_is_error_and_abstains():
    interp = {**_interp(), "extra": {"evidence_ids": ["ghost_id"]}}
    res = certify_interpretation(interp, _case(), decision_time="2026-01-05T13:00:00Z")
    assert res["certified"] is False
    assert res["abstained"] is True
    assert res["summary"]["errors"] >= 1
    assert any(v["code"] == "EVIDENCE_ID_NOT_GROUNDED" for v in res["violations"])


def test_future_confirming_time_is_block():
    interp = _interp()
    interp = {**interp, "accepted_breaks": [
        {**interp["accepted_breaks"][0], "confirming_candle_time": "2026-01-05T14:00:00Z"},
    ]}
    res = certify_interpretation(
        interp, _case(), decision_time="2026-01-05T13:00:00Z",
        per_timeframe_cutoff={"15m": "2026-01-05T13:00:00Z"},
    )
    assert res["certified"] is False
    assert any(v["code"] == "FUTURE_DATA_LEAK" for v in res["violations"])


def test_temporal_order_violation_is_block():
    # protected point closes AFTER the break it protects
    case = _case()
    case = {**case, "candidate_objects": {"15m": {"swings": [
        {"object_id": "pp1", "confirmed_at": "2026-01-05T15:00:00Z", "timeframe": "15m", "pivot_price": 98.0, "lifecycle": "PROTECTED"},
        {"object_id": "s10", "confirmed_at": "2026-01-05T08:00:00Z", "timeframe": "15m", "pivot_price": 99.0, "lifecycle": "STRUCTURAL"},
        {"object_id": "c1", "confirmed_at": "2026-01-05T12:00:00Z", "timeframe": "15m", "pivot_price": 100.0, "lifecycle": "CANDIDATE"},
    ]}}}
    res = certify_interpretation(_interp(), case, decision_time="2026-01-05T16:00:00Z")
    assert any(v["code"] == "TEMPORAL_ORDER_VIOLATION" for v in res["violations"])
    assert res["certified"] is False


def test_child_cannot_overwrite_parent_is_block():
    interp = {**_interp(), "active_ranges": [
        {"range_id": "child", "owner_timeframe": "4h", "parent_range_id": "parent"},
        {"range_id": "parent", "owner_timeframe": "4h"},   # same hierarchy as child -> block
    ]}
    res = certify_interpretation(interp, _case(), decision_time="2026-01-05T13:00:00Z")
    assert any(v["code"] == "CHILD_CANNOT_OVERWRITE_PARENT" for v in res["violations"])


def test_protected_and_broken_lifecycle_is_block():
    case = {**_case(), "candidate_objects": {"15m": {"swings": [
        {"object_id": "c1", "confirmed_at": "2026-01-05T12:00:00Z", "timeframe": "15m", "pivot_price": 100.0, "lifecycle": "PROTECTED BROKEN"},
        {"object_id": "s10", "confirmed_at": "2026-01-05T08:00:00Z", "timeframe": "15m", "pivot_price": 99.0, "lifecycle": "STRUCTURAL"},
    ]}}}
    res = certify_interpretation(_interp(), case, decision_time="2026-01-05T13:00:00Z")
    assert any(v["code"] == "LIFECYCLE_CONTRADICTION" for v in res["violations"])


def test_accepted_break_without_displacement_is_error():
    interp = {**_interp(), "accepted_breaks": [
        {**_interp()["accepted_breaks"][0], "displacement_evidence_ids": []},
    ]}
    res = certify_interpretation(interp, _case(), decision_time="2026-01-05T13:00:00Z")
    assert any(v["code"] == "ACCEPTED_BREAK_WITHOUT_DISPLACEMENT" for v in res["violations"])
    assert res["certified"] is False


def test_narrative_naked_claim_is_block():
    interp = {**_interp(), "narrative": "price reached 1234.5678 without grounding"}
    res = certify_interpretation(interp, _case(), decision_time="2026-01-05T13:00:00Z")
    assert any(v["code"] == "NARRATIVE_NAKED_CLAIM" for v in res["violations"])
    assert res["certified"] is False


def test_abstention_requested_flips_flags():
    res = certify_interpretation(_interp(), _case(), decision_time="2026-01-05T13:00:00Z", abstention_requested=True)
    assert res["certified"] is False
    assert res["abstained"] is True


def test_pool_ids_collected_from_case_and_graph():
    case = _case()
    graph = {"active_range": {"range_id": "r1", "high_object_id": "s10"}}
    ids = collect_pool_ids(case, graph)
    assert {"c1", "s10", "pp1", "r1"} <= ids


def test_validation_result_blocks_and_errors():
    res = validate_interpretation(
        interpretation={**_interp(), "narrative": "price 1234.5678 ungrounded"},
        case=_case(), decision_time="2026-01-05T13:00:00Z",
    )
    assert len(res.blocks) >= 1
    assert res.certified is False


def test_empty_interpretation_fails_closed():
    res = certify_interpretation({}, _case(), decision_time="2026-01-05T13:00:00Z")
    codes = {violation["code"] for violation in res["violations"]}
    assert res["certified"] is False
    assert {"EMPTY_INTERPRETATION", "INTERPRETATION_STRUCTURE_REQUIRED", "INTERPRETATION_HAS_NO_EVIDENCE"} <= codes


def test_real_role_evidence_fields_cannot_hide_ghost_ids():
    interpretation = {
        "structure_claims": [{
            "claim_type": "continuation",
            "timeframe": "15m",
            "evidence_ids": ["c1"],
        }],
        "active_leg_evidence_ids": ["ghost"],
    }
    res = certify_interpretation(interpretation, _case(), decision_time="2026-01-05T13:00:00Z")
    assert res["certified"] is False
    assert any(v["code"] == "EVIDENCE_ID_NOT_GROUNDED" and "ghost" in v["evidence_ids"] for v in res["violations"])


@pytest.mark.parametrize("claim", ["XRP rejected 0.5234", "EURUSD rejected 1.0835", "level 99"])
def test_low_price_and_integer_narrative_claims_require_local_evidence(claim):
    interpretation = {**_interp(), "unscoped_comment": claim}
    res = certify_interpretation(interpretation, _case(), decision_time="2026-01-05T13:00:00Z")
    assert res["certified"] is False
    assert any(v["code"] == "NARRATIVE_NAKED_CLAIM" for v in res["violations"])
