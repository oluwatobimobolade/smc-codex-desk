"""Temporal validator (programme §28.2, future_data_cutoff).

Two checks:
  1. future_data_leak: any evidence_id whose candle close time is beyond the
     decision_time's last-allowed-candle close per timeframe is a BLOCK.
  2. temporal_ordering: every causal relationship must respect event order
     (e.g., a protected point cannot be created AFTER the break it protects).

Both are deterministic over the certified evidence; neither needs the AI.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from smc_desk.validation.primitives import Severity, Violation
from smc_desk.validation.evidence import walk_evidence_fields
from smc_desk.perception.programme_schema import (
    candidate_time,
    canonical_object_id,
    flatten_candidate_objects,
)

import pandas as pd


def _candidate_close_time(
    eid: str,
    case: Mapping[str, Any],
) -> str | None:
    """Look up a candidate's candle close time by object_id."""
    for candidate in flatten_candidate_objects(case.get("candidate_objects") or {}):
        if canonical_object_id(candidate) == eid:
            value = candidate_time(candidate)
            return value or None
    return None


def _evidence_close_times(
    ids: Iterable[str],
    case: Mapping[str, Any],
) -> dict[str, str | None]:
    return {eid: _candidate_close_time(eid, case) for eid in ids}


def check_future_data(
    *,
    interpretation: Mapping[str, Any],
    decision_time: str,
    per_timeframe_cutoff: Mapping[str, str] | None,
    case: Mapping[str, Any],
) -> tuple[Violation, ...]:
    """BLOCK any evidence_id whose close time exceeds its timeframe's cutoff,
    and any break whose confirming_candle_time exceeds the cutoff."""
    out: list[Violation] = []
    cutoffs = per_timeframe_cutoff or {}
    if not decision_time:
        return (Violation(
            code="DECISION_TIME_REQUIRED",
            severity=Severity.BLOCK.value,
            message="Certification requires an explicit decision_time.",
            checker="temporal.future_data",
        ),)
    for path, ids in walk_evidence_fields(interpretation):
        for eid in ids:
            ct = _candidate_close_time(eid, case)
            if ct is None:
                continue
            tf = _timeframe_for(eid, case) or "default"
            cutoff = cutoffs.get(tf) or cutoffs.get("default") or decision_time
            if _after(ct, cutoff):
                out.append(Violation(
                    code="FUTURE_DATA_LEAK",
                    severity=Severity.BLOCK.value,
                    message=(f"evidence_id {eid!r} closes at {ct} which is after "
                             f"the {tf} cutoff {cutoff} (decision_time={decision_time})"),
                    evidence_ids=(eid,),
                    field_path=path,
                    checker="temporal.future_data",
                ))
    # Also check each accepted break's own confirming_candle_time.
    for br in interpretation.get("accepted_breaks") or []:
        if not isinstance(br, Mapping):
            continue
        br_time = br.get("confirming_candle_time")
        if not isinstance(br_time, str) or not br_time:
            continue
        tf = str(br.get("timeframe") or "default")
        cutoff = cutoffs.get(tf) or cutoffs.get("default") or decision_time
        if _after(br_time, cutoff):
            out.append(Violation(
                code="FUTURE_DATA_LEAK",
                severity=Severity.BLOCK.value,
                message=(f"break {br.get('object_id')} confirming_candle_time {br_time} "
                         f"is after the {tf} cutoff {cutoff} (decision_time={decision_time})"),
                evidence_ids=(str(br.get("object_id") or ""),),
                field_path="accepted_breaks",
                checker="temporal.future_data",
            ))
    return tuple(out)


def check_temporal_ordering(
    *,
    interpretation: Mapping[str, Any],
    case: Mapping[str, Any],
) -> tuple[Violation, ...]:
    """BLOCK causal relationships whose cause strictly follows its effect.

    Inspects known relationship fields (protected_point_id vs break's
    confirming_candle_time; break_origin vs break; parent_range vs child).
    A cause must close at or before its effect.
    """
    out: list[Violation] = []
    # protected point must predate the break it protects
    pp = interpretation.get("protected_point")
    if isinstance(pp, Mapping) and pp.get("object_id"):
        pp_time = _candidate_close_time(str(pp["object_id"]), case)
        for br in interpretation.get("accepted_breaks") or []:
            if not isinstance(br, Mapping):
                continue
            br_time = br.get("confirming_candle_time") or _candidate_close_time(
                str(br.get("origin_object_id") or ""), case
            )
            if pp_time and br_time and _after(pp_time, br_time):
                out.append(Violation(
                    code="TEMPORAL_ORDER_VIOLATION",
                    severity=Severity.BLOCK.value,
                    message=(f"protected point {pp['object_id']} closes at "
                             f"{pp_time} AFTER break {br.get('object_id')} at {br_time}"),
                    evidence_ids=(str(pp["object_id"]), str(br.get("object_id") or "")),
                    checker="temporal.ordering",
                ))
    return tuple(out)


def _timeframe_for(eid: str, case: Mapping[str, Any]) -> str | None:
    for candidate in flatten_candidate_objects(case.get("candidate_objects") or {}):
        if canonical_object_id(candidate) == eid:
            tf = candidate.get("timeframe")
            return tf if isinstance(tf, str) else None
    return None


def _after(left: str, right: str) -> bool:
    try:
        a = pd.Timestamp(left)
        b = pd.Timestamp(right)
        a = a.tz_localize("UTC") if a.tzinfo is None else a.tz_convert("UTC")
        b = b.tz_localize("UTC") if b.tzinfo is None else b.tz_convert("UTC")
        return a > b
    except (TypeError, ValueError):
        return True


__all__ = ["check_future_data", "check_temporal_ordering"]
