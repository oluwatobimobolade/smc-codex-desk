"""Deterministic validator orchestrator (programme §28).

Run the four validators, aggregate violations, and produce the certified /
abstained flag. The orchestrator is the single entry the structure-lab
runtime calls.

Rules (programme §28):
  * Any BLOCK violation -> certified = False.
  * Any ERROR violation -> abstained = True (the system is safer refusing).
  * No violations -> certified = True and abstained = False.
  * The abstention rule (doctrine §17) also flips to abstained=True when
    confidence_axis == contradicted or insufficient_context -- the
    orchestrator accepts that as a flag the caller may pass in.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from smc_desk.validation import evidence, invariants, narrative, temporal
from smc_desk.validation.primitives import Severity, ValidatorResult, Violation


def validate_interpretation(
    *,
    interpretation: Mapping[str, Any],
    case: Mapping[str, Any],
    decision_time: str,
    per_timeframe_cutoff: Mapping[str, str] | None | None = None,
    abstention_requested: bool = False,
    candidate_overrides: set[str] | None = None,
) -> ValidatorResult:
    """Run all four validators. Returns aggregated result."""
    graph = case.get("formal_structure_graph") or {}
    admissible = evidence.collect_pool_ids(case, graph)
    if candidate_overrides:
        admissible |= candidate_overrides

    violations: list[Violation] = []

    ev = evidence.check_evidence_grounding(
        interpretation=interpretation, admissible_ids=admissible,
    )
    violations.extend(ev)

    fu = temporal.check_future_data(
        interpretation=interpretation, decision_time=decision_time,
        per_timeframe_cutoff=per_timeframe_cutoff or {}, case=case,
    )
    violations.extend(fu)

    to = temporal.check_temporal_ordering(
        interpretation=interpretation, case=case,
    )
    violations.extend(to)

    inv = invariants.check_invariants(
        interpretation=interpretation, case=case,
    )
    violations.extend(inv)

    nar = narrative.check_narrative_grounding(interpretation)
    violations.extend(nar)

    blocks = tuple(v for v in violations if v.severity == Severity.BLOCK.value)
    errors = tuple(v for v in violations if v.severity == Severity.ERROR.value)

    certified = (len(blocks) == 0) and (len(errors) == 0) and (not abstention_requested)
    abstained = abstention_requested or (len(errors) > 0) or (len(blocks) > 0)

    return ValidatorResult(
        violations=tuple(violations),
        certified=certified,
        abstained=abstained,
        checked=("evidence", "temporal.future_data", "temporal.ordering", "invariants", "narrative"),
        summary={
            "blocks": len(blocks),
            "errors": len(errors),
            "warns": sum(1 for v in violations if v.severity == Severity.WARN.value),
            "infos": sum(1 for v in violations if v.severity == Severity.INFO.value),
            "admissible_evidence_ids": len(admissible),
            "candidate_overrides": len(candidate_overrides or ()),
        },
    )


def certify_interpretation(
    interpretation: Mapping[str, Any],
    case: Mapping[str, Any],
    *,
    decision_time: str,
    per_timeframe_cutoff: Mapping[str, str] | None = None,
    abstention_requested: bool = False,
    candidate_overrides: set[str] | None = None,
) -> dict[str, Any]:
    """One-line helper returning a JSON-serialisable certification envelope."""
    result = validate_interpretation(
        interpretation=interpretation, case=case,
        decision_time=decision_time,
        per_timeframe_cutoff=per_timeframe_cutoff,
        abstention_requested=abstention_requested,
        candidate_overrides=candidate_overrides,
    )
    return {
        "schema": "certification_envelope_v1",
        "certified": result.certified,
        "abstained": result.abstained,
        "checked": list(result.checked),
        "summary": dict(result.summary),
        "violations": [v.to_dict() for v in result.violations],
    }


__all__ = ["certify_interpretation", "validate_interpretation"]
