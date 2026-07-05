"""Compact structure narrative for AI-facing market summaries.

The raw detector output can be correct while a compressed label such as
``1h: bearish`` is wrong. This module preserves the trader-relevant distinction:
external structure, internal pullback, and raw OHLC drift are separate facts.

When a formal structure graph is present in the caller's context, this module
delegates the parent-child analysis to the graph rather than recomputing it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


DIRECTIONS = {"bullish", "bearish"}
STRUCTURE_TIMEFRAME_ORDER = ("1d", "12h", "4h", "1h", "15m", "5m")
CONTEXT_TIMEFRAMES = {"1d", "12h", "4h", "1h"}


def prefer_formal_graph_override(
    structure_narrative: dict[str, Any],
    formal_graph: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """When a formal graph is present, override the narrative's parent-child context."""
    if not isinstance(formal_graph, Mapping) or not formal_graph:
        return structure_narrative
    pc = formal_graph.get("parent_child_context")
    if not isinstance(pc, Mapping):
        return structure_narrative
    result = dict(structure_narrative)
    result["parent_child_context"] = dict(pc)
    result["parent_child_context"]["source"] = "formal_structure_graph"
    return result


def build_structure_narrative(
    detector_candidates: Mapping[str, Any],
    *,
    raw_bias: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize each timeframe without collapsing structure into one raw label."""
    raw_bias = raw_bias or {}
    timeframes: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    evidence: list[str] = []

    for timeframe, payload in detector_candidates.items():
        if not isinstance(payload, Mapping):
            continue
        breaks = _confirmed_breaks(payload.get("structure_breaks", []) or [])
        latest_external = _latest_break(breaks, scope="external")
        latest_internal = _latest_break(breaks, scope="internal")
        external_bias = _direction(latest_external) if latest_external else None
        internal_direction = _direction(latest_internal) if latest_internal else None
        internal_after_external = bool(
            latest_external
            and latest_internal
            and _event_time(latest_internal) is not None
            and _event_time(latest_external) is not None
            and _event_time(latest_internal) >= _event_time(latest_external)
        )

        label = raw_bias.get(timeframe, "unknown")
        vote_bias = raw_bias.get(timeframe, "unknown")
        internal_state = "none"
        notes: list[str] = []

        if external_bias in DIRECTIONS:
            vote_bias = external_bias
            label = external_bias
            if internal_direction in DIRECTIONS and internal_after_external and internal_direction != external_bias:
                internal_state = f"{internal_direction}_internal_pullback"
                label = f"{external_bias}_external_{internal_direction}_internal_pullback"
                notes.append(
                    f"{timeframe}: latest external structure is {external_bias}, "
                    f"but latest internal break is {internal_direction}; treat as pullback, not full bias flip."
                )
            elif internal_direction in DIRECTIONS and internal_after_external:
                internal_state = f"{external_bias}_internal_continuation"

        raw = raw_bias.get(timeframe)
        if raw in DIRECTIONS and vote_bias in DIRECTIONS and raw != vote_bias:
            conflict = {
                "timeframe": timeframe,
                "raw_summary_bias": raw,
                "structure_vote_bias": vote_bias,
                "severity": "warning",
                "reason": "Raw OHLC drift conflicts with confirmed structure sequence.",
            }
            conflicts.append(conflict)
            notes.append(
                f"{timeframe}: raw summary bias {raw} conflicts with confirmed structure vote {vote_bias}."
            )

        if notes:
            evidence.extend(notes)

        timeframes[timeframe] = {
            "label": label,
            "vote_bias": vote_bias if vote_bias in DIRECTIONS else raw_bias.get(timeframe, "unknown"),
            "external_bias": external_bias or "unknown",
            "internal_state": internal_state,
            "latest_external_break_id": None if latest_external is None else latest_external.get("object_id"),
            "latest_internal_break_id": None if latest_internal is None else latest_internal.get("object_id"),
            "latest_external_confirmed_at": None if latest_external is None else latest_external.get("confirmed_at"),
            "latest_internal_confirmed_at": None if latest_internal is None else latest_internal.get("confirmed_at"),
            "notes": notes,
        }

    narrative = {
        "schema": "structure_narrative_v1",
        "timeframes": timeframes,
        "conflicts": conflicts,
        "evidence": evidence,
        "rule": "External structure controls the timeframe story; opposite internal CHoCH/BOS is pullback until protected structure breaks.",
    }
    narrative["parent_child_context"] = build_parent_child_context(narrative)
    if narrative["parent_child_context"].get("status") == "PARENT_CHILD_CONFLICT":
        narrative["evidence"].append(str(narrative["parent_child_context"]["thesis_sentence"]))
    return narrative


def derive_strict_htf_bias(
    vote_bias: Mapping[str, str],
    *,
    fallback_bias: Mapping[str, str] | None = None,
) -> str:
    """Use the house-rule HTF consensus instead of majority voting.

    4H and 1H must agree. Daily must agree or be neutral/mixed/unknown.
    If structure votes are unavailable, fall back to the provided raw summary
    labels with the same strict consensus rule.
    """
    fallback_bias = fallback_bias or {}

    def vote(tf: str) -> str:
        value = vote_bias.get(tf)
        if value not in DIRECTIONS:
            value = fallback_bias.get(tf, "unknown")
        return value if value in DIRECTIONS else "unknown"

    daily = vote("1d")
    if daily == "unknown":
        daily = vote("12h")
    four_hour = vote("4h")
    one_hour = vote("1h")
    if four_hour in DIRECTIONS and one_hour in DIRECTIONS and four_hour == one_hour:
        if daily in DIRECTIONS and daily != one_hour:
            return "mixed"
        return one_hour
    if four_hour in DIRECTIONS and one_hour in DIRECTIONS and four_hour != one_hour:
        return "mixed"
    if one_hour in DIRECTIONS and four_hour == "unknown":
        if daily in DIRECTIONS and daily != one_hour:
            return "mixed"
        return one_hour
    if four_hour in DIRECTIONS and one_hour == "unknown":
        if daily in DIRECTIONS and daily != four_hour:
            return "mixed"
        return four_hour
    return "mixed"


def build_parent_child_context(structure_narrative: Mapping[str, Any]) -> dict[str, Any]:
    """Describe top-down conflicts without flattening either side.

    A common SMC failure is saying "bullish" because the 1H/15m broke up while
    the 12H/Daily parent remains bearish, or saying "bearish" while ignoring the
    valid child recovery. This context names that relationship explicitly so the
    downstream thesis has to say what a trader would say: parent direction first,
    child pullback/recovery second.
    """
    raw_timeframes = structure_narrative.get("timeframes") if isinstance(structure_narrative, Mapping) else {}
    if not isinstance(raw_timeframes, Mapping):
        raw_timeframes = {}
    ordered = [tf for tf in STRUCTURE_TIMEFRAME_ORDER if isinstance(raw_timeframes.get(tf), Mapping)]
    context_ordered = [tf for tf in ordered if tf in CONTEXT_TIMEFRAMES]
    if len(context_ordered) < 2:
        return {
            "schema": "parent_child_structure_context_v1",
            "status": "INSUFFICIENT_CONTEXT",
            "has_parent_child_conflict": False,
            "thesis_sentence": "Insufficient parent-child timeframe context.",
            "evidence": [],
        }

    timeframe_votes = {
        tf: _vote(raw_timeframes[tf])
        for tf in ordered
        if isinstance(raw_timeframes.get(tf), Mapping)
    }
    conflicts: list[dict[str, Any]] = []
    for parent_index, parent_tf in enumerate(context_ordered[:-1]):
        parent_bias = timeframe_votes.get(parent_tf)
        if parent_bias not in DIRECTIONS:
            continue
        for child_tf in context_ordered[parent_index + 1:]:
            child_bias = timeframe_votes.get(child_tf)
            if child_bias in DIRECTIONS and child_bias != parent_bias:
                conflicts.append(
                    {
                        "parent_timeframe": parent_tf,
                        "parent_bias": parent_bias,
                        "child_timeframe": child_tf,
                        "child_bias": child_bias,
                    }
                )

    internal_pullbacks = []
    for tf, item in raw_timeframes.items():
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "")
        if "_external_" in label and "_internal_pullback" in label:
            internal_pullbacks.append(
                {
                    "timeframe": str(tf),
                    "label": label,
                    "external_bias": str(item.get("external_bias") or "unknown"),
                    "internal_state": str(item.get("internal_state") or "unknown"),
                }
            )

    if conflicts:
        primary = conflicts[0]
        parent_tf = str(primary["parent_timeframe"])
        parent_bias = str(primary["parent_bias"])
        child_tf = str(primary["child_timeframe"])
        child_bias = str(primary["child_bias"])
        child_phrase = "recovery" if child_bias == "bullish" else "selloff"
        thesis_sentence = (
            f"{parent_tf} remains {parent_bias} parent structure while {child_tf} is "
            f"{child_bias} child {child_phrase}; treat the child move as a pullback/recovery "
            "inside parent context until the parent protected structure breaks."
        )
        return {
            "schema": "parent_child_structure_context_v1",
            "status": "PARENT_CHILD_CONFLICT",
            "has_parent_child_conflict": True,
            "parent_timeframe": parent_tf,
            "parent_bias": parent_bias,
            "child_timeframe": child_tf,
            "child_bias": child_bias,
            "child_phase": child_phrase,
            "required_final_bias": "mixed",
            "required_trade_state": "THESIS_ONLY_OR_REVIEW",
            "thesis_sentence": thesis_sentence,
            "conflicts": conflicts,
            "internal_pullbacks": internal_pullbacks,
            "evidence": [
                thesis_sentence,
                "Do not call the market clean bullish or clean bearish while parent and child context timeframes conflict.",
            ],
        }

    aligned_biases = [timeframe_votes.get(tf) for tf in context_ordered if timeframe_votes.get(tf) in DIRECTIONS]
    aligned_bias = aligned_biases[0] if aligned_biases and len(set(aligned_biases)) == 1 else "mixed"
    thesis_sentence = (
        f"Context timeframes are aligned {aligned_bias}."
        if aligned_bias in DIRECTIONS
        else "Context timeframes are not in a clean parent-child conflict, but alignment is incomplete."
    )
    return {
        "schema": "parent_child_structure_context_v1",
        "status": "ALIGNED" if aligned_bias in DIRECTIONS else "INCOMPLETE_ALIGNMENT",
        "has_parent_child_conflict": False,
        "aligned_bias": aligned_bias,
        "internal_pullbacks": internal_pullbacks,
        "thesis_sentence": thesis_sentence,
        "evidence": [thesis_sentence],
    }


def _confirmed_breaks(raw_breaks: list[Any]) -> list[Mapping[str, Any]]:
    confirmed: list[Mapping[str, Any]] = []
    for item in raw_breaks:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(payload, Mapping):
            continue
        evidence = payload.get("evidence") or {}
        if payload.get("confirmed_at") and not evidence.get("is_unconfirmed_probe"):
            confirmed.append(payload)
    return sorted(confirmed, key=lambda item: str(item.get("confirmed_at") or item.get("candidate_at") or ""))


def _latest_break(breaks: list[Mapping[str, Any]], *, scope: str) -> Mapping[str, Any] | None:
    matches = [item for item in breaks if _scope(item) == scope]
    return matches[-1] if matches else None


def _scope(item: Mapping[str, Any]) -> str:
    evidence = item.get("evidence") or {}
    value = str(item.get("structure_scope") or evidence.get("structure_scope") or "")
    if value in {"external", "internal"}:
        return value
    return "internal" if evidence.get("is_internal") else "external"


def _direction(item: Mapping[str, Any] | None) -> str | None:
    if item is None:
        return None
    direction = str(item.get("direction", "")).lower()
    return direction if direction in DIRECTIONS else None


def _vote(timeframe_item: Mapping[str, Any]) -> str:
    value = str(timeframe_item.get("vote_bias") or timeframe_item.get("external_bias") or "").lower()
    return value if value in DIRECTIONS else "unknown"


def _event_time(item: Mapping[str, Any]) -> datetime | None:
    raw = item.get("confirmed_at") or item.get("candidate_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
