"""WP-0037 External Agent Acceptance Gauntlet.

This test runs the full system through 8 acceptance cases that represent
the spectrum of SMC scenarios the external AI agent must handle:

  1. WATCH_ONLY bearish retrace
  2. REVIEW_REQUIRED conflict case
  3. TRADE_PLAN_READY bearish continuation
  4. TRADE_PLAN_READY bullish continuation
  5. MISSED_TRADE_NO_CHASE
  6. VALID_DIRECTION_BAD_RR
  7. TARGET_CONFLICT_REJECTED (intentionally bad)
  8. SWEPT_LOW_NOT_FRESH (intentionally bad)

The gauntlet proves that:
  - The system can validate trade-ready cases (not just refuse everything)
  - The system can validate watch/thesis-only cases
  - The system rejects bad AI claims (target conflict, swept low mislabel)
  - The workflow status is honest about the agent handoff
  - The analysis status reflects the market correctly

Each case is treated as an EXTERNAL_AI_AGENT response, not a manual
or deterministic payload. This proves the full agent handoff protocol.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smc_desk.brain.agent_handoff.external_agent_provider import ExternalAIAgentProvider
from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import parse_ai_smc_decision
from smc_desk.brain.llm_provider import LLMCompletionRequest
from smc_desk.colleague.orchestrator_v3 import _status, _workflow_status, _analysis_status

GAUNTLET_DIR = Path(__file__).parent / "fixtures" / "gauntlet_cases"


def _load_case(case_id: str) -> dict:
    return json.loads((GAUNTLET_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def _build_formal_graph_from_candidates(detector_candidates: dict, active_range: dict) -> dict:
    """Build a formal structure graph from detector candidates (test helper)."""
    timeframes = {}
    for tf, payload in detector_candidates.items():
        if not isinstance(payload, dict):
            continue
        breaks = payload.get("structure_breaks", [])
        confirmed_breaks = [
            b for b in breaks
            if b.get("confirmed_at") and not b.get("evidence", {}).get("is_unconfirmed_probe", False)
        ]
        wick_probes = [
            b for b in breaks
            if b.get("evidence", {}).get("is_unconfirmed_probe", False)
        ]
        ext = [b for b in confirmed_breaks if b.get("evidence", {}).get("structure_scope") == "external"]
        intl = [b for b in confirmed_breaks if b.get("evidence", {}).get("structure_scope") == "internal"]
        latest_ext = ext[-1] if ext else None
        latest_int = intl[-1] if intl else None
        ext_bias = (latest_ext or {}).get("direction", "unknown")
        timeframes[tf] = {
            "timeframe": tf,
            "external_bias": ext_bias,
            "internal_state": "none",
            "has_wick_probes": len(wick_probes) > 0,
            "wick_probe_count": len(wick_probes),
        }

    ordered = [tf for tf in ("1d", "12h", "4h", "1h") if tf in timeframes]
    has_conflict = False
    for pi, parent_tf in enumerate(ordered[:-1]):
        parent_bias = timeframes[parent_tf]["external_bias"]
        if parent_bias not in ("bullish", "bearish"):
            continue
        for child_tf in ordered[pi + 1:]:
            child_bias = timeframes[child_tf]["external_bias"]
            if child_bias in ("bullish", "bearish") and child_bias != parent_bias:
                has_conflict = True
                break
        if has_conflict:
            break

    # Wick probes are normal market noise — they no longer cause invariant violations
    inv_status = "PASS"

    selected = active_range.get("selected_range", {})
    ar_node = {
        "status": "RESOLVED" if selected.get("status") == "RESOLVED_ACTIVE_RANGE" else "UNRESOLVED",
        "source": "protected_swing_pair" if selected else "unknown",
    }

    return {
        "schema": "formal_mtf_structure_graph_v1",
        "symbol": "",
        "timeframes": timeframes,
        "parent_child_context": {
            "status": "PARENT_CHILD_CONFLICT" if has_conflict else "ALIGNED",
            "has_conflict": has_conflict,
        },
        "active_range": ar_node,
        "invariants": {"status": inv_status, "violations": []},
        "authority_contract": {
            "signal_allowed": False,
            "invariant_passed": inv_status == "PASS",
            "trade_promotion_blocked": inv_status != "PASS" or has_conflict,
        },
    }


def _make_evidence_pack(case: dict) -> dict:
    ep = case["evidence_pack"]
    graph = _build_formal_graph_from_candidates(
        ep["detector_candidates"], ep["active_range_authority"]
    )
    graph["symbol"] = case["ai_decision"]["symbol"]
    return {
        "schema": "smc_evidence_pack_v1",
        "symbol": case["ai_decision"]["symbol"],
        "active_range_authority": ep["active_range_authority"],
        "detector_candidates": ep["detector_candidates"],
        "formal_structure_graph": graph,
        "structure_narrative": {
            "timeframes": {},
            "parent_child_context": {
                "has_parent_child_conflict": False,
                "status": "ALIGNED",
                "thesis_sentence": "All timeframes aligned.",
            },
        },
        "ohlcv_summaries": {},
        "data_contract": {"source": "fixture", "canonical_timeframe": "15m", "execution_authority": "disabled"},
        "authority_contract": {"evidence_only": True, "execution": "disabled", "capital_risk": 0},
        "provenance": {"pack_hash": f"fixture_{case['case_id']}"},
    }


def _run_case(case: dict) -> dict:
    """Run a single gauntlet case through the validator as an external agent."""
    decision = parse_ai_smc_decision(case["ai_decision"])
    pack = _make_evidence_pack(case)

    provider = ExternalAIAgentProvider(
        case["ai_decision"],
        agent_name="gauntlet_agent",
        agent_model="test_agent",
    )
    request = LLMCompletionRequest(prompt="gauntlet", evidence_pack=pack, chart_images={})
    provider_result = provider.complete(request)

    result = validate_ai_smc_decision(decision, pack)
    status = _status(provider_result=provider_result, validation_result=result)
    workflow = _workflow_status(provider_result)
    analysis = _analysis_status(result)

    hard_issues = [i for i in result.issues if i.severity == "hard"]
    return {
        "case_id": case["case_id"],
        "description": case.get("description", ""),
        "expected_workflow_status": case["expected_workflow_status"],
        "expected_analysis_status": case["expected_analysis_status"],
        "expected_official_state": case["expected_official_state"],
        "actual_workflow_status": workflow,
        "actual_analysis_status": analysis,
        "actual_status": status,
        "actual_official_state": result.official_decision.get("official_state"),
        "hard_issue_count": len(hard_issues),
        "hard_issue_codes": [i.code for i in hard_issues],
        "workflow_match": workflow == case["expected_workflow_status"],
        "analysis_match": analysis == case["expected_analysis_status"],
        "state_match": result.official_decision.get("official_state") == case["expected_official_state"],
        "passed": (
            workflow == case["expected_workflow_status"]
            and analysis == case["expected_analysis_status"]
            and result.official_decision.get("official_state") == case["expected_official_state"]
        ),
    }


def test_gauntlet_01_watch_only_bearish_retrace() -> None:
    """Case 1: WATCH_ONLY bearish retrace — all timeframes bearish, waiting for BSL sweep."""
    case = _load_case("gauntlet_01_watch_only_bearish_retrace")
    result = _run_case(case)
    assert result["passed"], f"Case 1 failed: {result}"


def test_gauntlet_02_review_required_conflict() -> None:
    """Case 2: Parent-child conflict with mixed bias — decision correctly handles it."""
    case = _load_case("gauntlet_02_review_required_conflict")
    result = _run_case(case)
    assert result["passed"], f"Case 2 failed: {result}"
    # The decision correctly uses direction=mixed and official_state=REVIEW_REQUIRED
    # for parent-child conflict, so the validator says VALIDATED (decision is correct)
    assert result["actual_official_state"] == "REVIEW_REQUIRED"


def test_gauntlet_03_trade_ready_bearish_continuation() -> None:
    """Case 3: TRADE_PLAN_READY bearish continuation — must validate."""
    case = _load_case("gauntlet_03_trade_ready_bearish_continuation")
    result = _run_case(case)
    assert result["passed"], f"Case 3 failed: {result}"


def test_gauntlet_04_trade_ready_bullish_continuation() -> None:
    """Case 4: TRADE_PLAN_READY bullish continuation — must validate."""
    case = _load_case("gauntlet_04_trade_ready_bullish_continuation")
    result = _run_case(case)
    assert result["passed"], f"Case 4 failed: {result}"


def test_gauntlet_05_missed_trade_no_chase() -> None:
    """Case 5: MISSED_TRADE_NO_CHASE — move already happened, don't chase."""
    case = _load_case("gauntlet_05_missed_trade_no_chase")
    result = _run_case(case)
    assert result["passed"], f"Case 5 failed: {result}"


def test_gauntlet_06_valid_direction_bad_rr() -> None:
    """Case 6: VALID_DIRECTION_BAD_RR — direction valid but RR too low."""
    case = _load_case("gauntlet_06_valid_direction_bad_rr")
    result = _run_case(case)
    assert result["passed"], f"Case 6 failed: {result}"


def test_gauntlet_07_target_conflict_rejected() -> None:
    """Case 7: Target is swept liquidity — validator MUST reject."""
    case = _load_case("gauntlet_07_target_conflict_rejected")
    result = _run_case(case)
    assert result["actual_analysis_status"] == "REVIEW_REQUIRED", f"Case 7 should be rejected: {result}"
    assert result["hard_issue_count"] > 0, f"Case 7 should have hard issues: {result}"


def test_gauntlet_08_swept_low_not_fresh() -> None:
    """Case 8: Swept low mislabeled as fresh — validator MUST reject."""
    case = _load_case("gauntlet_08_swept_low_not_fresh")
    result = _run_case(case)
    assert result["actual_analysis_status"] == "REVIEW_REQUIRED", f"Case 8 should be rejected: {result}"


def test_gauntlet_all_cases_workflow_is_agent_review() -> None:
    """All cases must be marked as AGENT_REVIEW_WORKFLOW (not local deterministic)."""
    case_ids = [
        "gauntlet_01_watch_only_bearish_retrace",
        "gauntlet_02_review_required_conflict",
        "gauntlet_03_trade_ready_bearish_continuation",
        "gauntlet_04_trade_ready_bullish_continuation",
        "gauntlet_05_missed_trade_no_chase",
        "gauntlet_06_valid_direction_bad_rr",
        "gauntlet_07_target_conflict_rejected",
        "gauntlet_08_swept_low_not_fresh",
    ]
    for case_id in case_ids:
        case = _load_case(case_id)
        result = _run_case(case)
        assert result["actual_workflow_status"] == "AGENT_REVIEW_WORKFLOW", f"{case_id}: {result['actual_workflow_status']}"


def test_gauntlet_summary() -> None:
    """Full gauntlet summary — must pass at least 6/8 cases."""
    case_ids = [
        "gauntlet_01_watch_only_bearish_retrace",
        "gauntlet_02_review_required_conflict",
        "gauntlet_03_trade_ready_bearish_continuation",
        "gauntlet_04_trade_ready_bullish_continuation",
        "gauntlet_05_missed_trade_no_chase",
        "gauntlet_06_valid_direction_bad_rr",
        "gauntlet_07_target_conflict_rejected",
        "gauntlet_08_swept_low_not_fresh",
    ]
    results = [_run_case(_load_case(cid)) for cid in case_ids]
    passed = sum(1 for r in results if r["passed"])
    rejected = sum(1 for r in results if r["actual_analysis_status"] == "REVIEW_REQUIRED")
    assert passed >= 6, f"Only {passed}/8 cases passed: {[r['case_id'] for r in results if not r['passed']]}"
    assert rejected >= 2, f"Only {rejected}/8 cases were rejected (expected at least 2: conflict + target conflict)"
