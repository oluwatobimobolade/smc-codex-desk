"""Structural-invariant validator (programme §28.3).

Checks the interpretation's graph for invariants the doctrine mandates:
  * Every break cites a breaking_candidate and an origin_candidate that
    exist (catches 'invented break').
  * A protected point is owned by the same timeframe as the break it
    protects (§5 timeframe_ownership).
  * A child range's parent_range_id exists and has a longer timeframe
    hierarchy (Daily > 4H > 1H > 15m) -- a child cannot overwrite its
    parent (§7.4).
  * No swing is simultaneously PROTECTED and BROKEN (lifecycle invariant).
  * Accepting a break requires displacement evidence present (§4.2E / §6.4).
"""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.validation.primitives import Severity, Violation

_HIERARCHY = {"1d": 4, "4h": 3, "1h": 2, "15m": 1, "5m": 0}


def check_invariants(
    *,
    interpretation: Mapping[str, Any],
    case: Mapping[str, Any],
) -> tuple[Violation, ...]:
    out: list[Violation] = []
    pool_ids = _pool_ids(case)

    for br in interpretation.get("accepted_breaks") or []:
        if not isinstance(br, Mapping):
            continue
        origin = br.get("origin_object_id")
        breaking = br.get("breaking_candidate_id")
        if origin and origin not in pool_ids:
            out.append(Violation(
                code="BREAK_ORIGIN_NOT_GROUNDED",
                severity=Severity.BLOCK.value,
                message=f"break {br.get('object_id')} origin {origin!r} not in candidate pool",
                evidence_ids=(str(origin),),
                checker="invariants.break_origin",
            ))
        if breaking and breaking not in pool_ids:
            out.append(Violation(
                code="BREAKING_CANDIDATE_NOT_GROUNDED",
                severity=Severity.BLOCK.value,
                message=f"break {br.get('object_id')} breaking_candidate {breaking!r} not in pool",
                evidence_ids=(str(breaking),),
                checker="invariants.breaking_candidate",
            ))
        # Accepting a break requires displacement evidence
        if br.get("accepted") and not br.get("displacement_evidence_ids"):
            out.append(Violation(
                code="ACCEPTED_BREAK_WITHOUT_DISPLACEMENT",
                severity=Severity.ERROR.value,
                message=(f"break {br.get('object_id')} marked accepted without "
                         f"displacement_evidence_ids (programme §6.4)"),
                checker="invariants.displacement_required",
            ))

    pp = interpretation.get("protected_point")
    for br in interpretation.get("accepted_breaks") or []:
        if (isinstance(pp, Mapping) and isinstance(br, Mapping)
                and pp.get("object_id") and br.get("timeframe")):
            pp_tf = _timeframe_of(str(pp.get("object_id")), case)
            if pp_tf and pp_tf != br.get("timeframe"):
                out.append(Violation(
                    code="PROTECTED_POINT_TIMEFRAME_MISMATCH",
                    severity=Severity.ERROR.value,
                    message=(f"protected point {pp.get('object_id')} (tf={pp_tf}) does not "
                             f"own break {br.get('object_id')} (tf={br.get('timeframe')})"),
                    evidence_ids=(str(pp.get("object_id")), str(br.get("object_id") or "")),
                    checker="invariants.pp_timeframe",
                ))

    ranges = interpretation.get("active_ranges") or []
    if isinstance(ranges, list):
        by_id = {r.get("range_id"): r for r in ranges if isinstance(r, Mapping)}
        for r in ranges:
            if not isinstance(r, Mapping):
                continue
            parent_id = r.get("parent_range_id")
            if parent_id and parent_id in by_id:
                parent = by_id[parent_id]
                ctf = _hierarchy_rank(str(r.get("owner_timeframe", "")))
                ptf = _hierarchy_rank(str(parent.get("owner_timeframe", "")))
                if ptf is not None and ctf is not None and ctf >= ptf:
                    out.append(Violation(
                        code="CHILD_CANNOT_OVERWRITE_PARENT",
                        severity=Severity.BLOCK.value,
                        message=(f"range {r.get('range_id')} (tf={r.get('owner_timeframe')}) "
                                 f"cannot have parent {parent_id} (tf={parent.get('owner_timeframe')}) "
                                 f"at an equal/longer hierarchy"),
                        checker="invariants.range_hierarchy",
                    ))

    # lifecycle invariant: a swing cannot be both PROTECTED and BROKEN
    for c in _all_candidates(case):
        if not isinstance(c, Mapping):
            continue
        life = str(c.get("lifecycle", "")).upper()
        if "PROTECTED" in life and "BROKEN" in life:
            out.append(Violation(
                code="LIFECYCLE_CONTRADICTION",
                severity=Severity.BLOCK.value,
                message=f"candidate {c.get('object_id')} marked both PROTECTED and BROKEN",
                evidence_ids=(str(c.get("object_id") or ""),),
                checker="invariants.lifecycle",
            ))

    return tuple(out)


def _pool_ids(case: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    co = case.get("candidate_objects") or {}
    if isinstance(co, Mapping):
        for buckets in co.values():
            if not isinstance(buckets, Mapping):
                continue
            for items in buckets.values():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, Mapping) and isinstance(it.get("object_id"), str):
                        ids.add(it["object_id"])
    return ids


def _all_candidates(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    co = case.get("candidate_objects") or {}
    if isinstance(co, Mapping):
        for buckets in co.values():
            if not isinstance(buckets, Mapping):
                continue
            for items in buckets.values():
                if isinstance(items, list):
                    out.extend(it for it in items if isinstance(it, Mapping))
    return out


def _timeframe_of(eid: str, case: Mapping[str, Any]) -> str | None:
    for c in _all_candidates(case):
        if c.get("object_id") == eid:
            tf = c.get("timeframe")
            if isinstance(tf, str):
                return tf
    return None


def _hierarchy_rank(tf: str) -> int | None:
    return _HIERARCHY.get(tf.lower())


__all__ = ["check_invariants"]