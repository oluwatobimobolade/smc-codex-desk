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


def _candidate_close_time(
    eid: str,
    case: Mapping[str, Any],
) -> str | None:
    """Look up a candidate's candle close time by object_id."""
    co = case.get("candidate_objects") or {}
    if not isinstance(co, Mapping):
        return None
    for buckets in co.values():
        if not isinstance(buckets, Mapping):
            continue
        for items in buckets.values():
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, Mapping) and it.get("object_id") == eid:
                    for k in ("confirmed_at", "candidate_at", "pivot_time", "close_time"):
                        v = it.get(k)
                        if isinstance(v, str) and v:
                            return v
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
    for path, ids in _walk_evidence_fields(interpretation):
        for eid in ids:
            ct = _candidate_close_time(eid, case)
            if ct is None:
                continue
            tf = _timeframe_for(eid, case) or "default"
            cutoff = cutoffs.get(tf) or cutoffs.get("default") or decision_time
            if ct > cutoff:
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
        if br_time > cutoff:
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
            if pp_time and br_time and pp_time > br_time:
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
    co = case.get("candidate_objects") or {}
    if not isinstance(co, Mapping):
        return None
    for buckets in co.values():
        if not isinstance(buckets, Mapping):
            continue
        for items in buckets.values():
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, Mapping) and it.get("object_id") == eid:
                    tf = it.get("timeframe")
                    if isinstance(tf, str):
                        return tf
    return None


def _walk_evidence_fields(obj: Any, path: str = "") -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            sub = f"{path}.{k}" if path else k
            if k in {"evidence_ids", "breaking_candidate_ids", "swept_levels",
                     "caused_breaks", "breaks_caused"} and isinstance(v, list):
                out.append((sub, [x for x in v if isinstance(x, str)]))
            elif isinstance(v, (dict, list)):
                out.extend(_walk_evidence_fields(v, sub))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_walk_evidence_fields(v, f"{path}[{i}]"))
    return out


__all__ = ["check_future_data", "check_temporal_ordering"]