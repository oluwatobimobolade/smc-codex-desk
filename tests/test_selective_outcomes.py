from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from smc_desk.evaluation.selective_outcomes import (
    OutcomeEvent,
    ShadowDecisionEvent,
    append_selective_ledger_event,
    build_selective_outcome_report,
    read_selective_ledger,
)


NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _decision(case_id: str, decision: str, uncertainty: float | None, prediction: str | None, reasons=None):
    return ShadowDecisionEvent(
        case_id=case_id, symbol="ETHUSDT", decision_time=NOW, horizon="24_bars",
        decision=decision, uncertainty_score=uncertainty, shadow_prediction=prediction,
        refusal_reasons=list(reasons or []), source_hashes={"data": case_id * 8},
    )


def _outcome(case_id: str, correct: bool | None, favorable: bool, state="RESOLVED"):
    return OutcomeEvent(
        case_id=case_id, resolved_at=NOW + timedelta(days=1), state=state,
        shadow_prediction_correct=correct, favorable_opportunity=favorable,
        outcome_definition="touch_target_before_invalidation_within_24_bars",
    )


def test_ledger_is_hash_chained_and_duplicate_safe(tmp_path: Path):
    ledger = tmp_path / "selective.jsonl"
    append_selective_ledger_event(ledger, _decision("a", "ACCEPT", 0.1, "BULLISH"))
    append_selective_ledger_event(ledger, _outcome("a", True, True))
    events = read_selective_ledger(ledger)
    assert len(events) == 2
    assert events[1]["previous_entry_sha256"] == events[0]["entry_sha256"]
    with pytest.raises(ValueError, match="Duplicate"):
        append_selective_ledger_event(ledger, _decision("a", "REFUSE", 0.7, "BULLISH", ["late_entry"]))


def test_ledger_tampering_fails_closed(tmp_path: Path):
    ledger = tmp_path / "selective.jsonl"
    append_selective_ledger_event(ledger, _decision("a", "ACCEPT", 0.1, "BULLISH"))
    text = ledger.read_text(encoding="utf-8").replace('"ACCEPT"', '"REFUSE"')
    ledger.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="hash-chain failure"):
        read_selective_ledger(ledger)


def test_report_measures_error_and_false_omission_separately():
    events = [
        _decision("a", "ACCEPT", 0.1, "BULLISH").model_dump(mode="json"),
        _outcome("a", True, True).model_dump(mode="json"),
        _decision("b", "ACCEPT", 0.2, "BEARISH").model_dump(mode="json"),
        _outcome("b", False, False).model_dump(mode="json"),
        _decision("c", "REFUSE", 0.7, "BULLISH", ["poi_ambiguous"]).model_dump(mode="json"),
        _outcome("c", True, True).model_dump(mode="json"),
        _decision("d", "REFUSE", 0.8, "BEARISH", ["poi_ambiguous", "regime_boundary"]).model_dump(mode="json"),
        _outcome("d", False, False).model_dump(mode="json"),
        _decision("e", "DATA_FAILED", None, None).model_dump(mode="json"),
    ]
    report = build_selective_outcome_report(events)
    assert report["metrics"]["coverage"] == 0.5
    assert report["metrics"]["selective_error"] == 0.5
    assert report["metrics"]["false_omission_rate"] == 0.5
    assert report["metrics"]["missed_favorable_outcome_rate"] == 0.5
    assert report["metrics"]["data_failure_rate"] == 0.2
    assert report["metrics"]["area_under_risk_coverage_curve"] is not None
    assert report["refusal_reason_distribution"] == {"poi_ambiguous": 2, "regime_boundary": 1}
    assert report["authority_contract"]["signal_allowed"] is False


def test_refusal_requires_a_reason_and_unresolved_stays_unscored():
    with pytest.raises(ValueError, match="REFUSE requires"):
        _decision("a", "REFUSE", 0.5, "NEUTRAL")
    decision = _decision("z", "REFUSE", 0.9, "NEUTRAL", ["no_confirmation"])
    report = build_selective_outcome_report([decision.model_dump(mode="json")])
    assert report["unresolved_case_ids"] == ["z"]
    assert report["metrics"]["false_omission_rate"] is None


# -- runs become measurable decisions -----------------------------------------

from datetime import datetime, timezone  # noqa: E402

from smc_desk.evaluation.selective_outcomes import (  # noqa: E402
    build_shadow_decision_from_run,
    _reconciliation_uncertainty,
)

DECIDED_AT = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)


def _build(**kwargs):
    base = dict(
        case_id="BTCUSDT:2026-08-14T18:00:00+00:00",
        symbol="BTCUSDT",
        decision_time=DECIDED_AT,
        horizon="next_20_bars_15m",
        official_state="REVIEW_REQUIRED",
    )
    base.update(kwargs)
    return build_shadow_decision_from_run(**base)


def test_a_refusal_still_records_the_read_it_would_have_taken():
    """Without this, "the system was right to stay out" can never be scored.

    A refusal with no shadow prediction is unfalsifiable: no later outcome can
    contradict it, so refusing always looks free.
    """
    event = _build(
        hard_issue_codes=["causal_episode_graph_reconciliation_required"],
        narrative_context={"is_coherent": True, "context_bias": "bearish"},
        invariants={"checks": [{"passed": True}, {"passed": False}]},
    )
    assert event.decision == "REFUSE"
    assert event.shadow_prediction == "BEARISH"
    assert event.refusal_reasons == ["causal_episode_graph_reconciliation_required"]
    assert event.uncertainty_score == 0.5


def test_refusal_without_stated_reasons_is_still_given_one():
    """The schema forbids a reasonless REFUSE; the adapter must not crash on it."""
    event = _build(official_state="WATCH_ONLY", invariants={"checks": [{"passed": True}]})
    assert event.decision == "REFUSE"
    assert event.refusal_reasons == ["official_state_watch_only"]


def test_trade_plan_ready_is_the_only_accept():
    event = _build(
        official_state="TRADE_PLAN_READY",
        narrative_context={"is_coherent": True, "context_bias": "bullish"},
        invariants={"checks": [{"passed": True}]},
    )
    assert event.decision == "ACCEPT"
    assert event.shadow_prediction == "BULLISH"
    assert event.refusal_reasons == []


def test_data_failure_is_not_a_refusal():
    """A run that could not read the market made no judgement to score."""
    event = _build(data_failed=True)
    assert event.decision == "DATA_FAILED"
    assert event.uncertainty_score is None
    assert event.shadow_prediction is None


def test_incoherent_narrative_yields_neutral_not_a_guessed_side():
    event = _build(
        narrative_context={"is_coherent": False, "context_bias": "bearish"},
        invariants={"checks": [{"passed": False}]},
    )
    assert event.shadow_prediction == "NEUTRAL"


def test_absent_reconciliation_evidence_is_maximum_uncertainty_not_zero():
    """Missing evidence must never read as confidence."""
    assert _reconciliation_uncertainty({}) is None
    assert _build(invariants={}).uncertainty_score == 1.0


def test_uncertainty_is_the_measured_disagreement_fraction():
    assert _reconciliation_uncertainty({"checks": [{"passed": True}] * 4}) == 0.0
    assert _reconciliation_uncertainty({"checks": [{"passed": False}] * 3}) == 1.0
