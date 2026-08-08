"""Narrative-driven annotation selection (observe-only).

Chooses *what* to draw from the hierarchical market read, in the order a
trader marks a chart:

1. the dealing range, because location comes before everything;
2. the controlling structure that established the current context, ranked by
   significance rather than recency;
3. the primary POI in the path of the draw.

This module only ever emits **evidence ids plus an object type**. Every price
and timestamp is still resolved by
``smc_desk.brain.structure_lab.annotation_bridge``, so nothing here can move
or invent chart geometry. It creates no signal and no trade authority.

Two selection rules exist because rendering exposed them on real data:

* **Scope de-duplication.** An external break and its internal counterpart
  frequently share a price and timestamp. Drawing both stacks two labels on
  one line and hides the more important one. External structure wins; the
  internal twin is dropped.
* **Price separation.** Two marks closer together than a fraction of ATR are
  visually one mark. The weaker is dropped rather than rendered underneath.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from smc_desk.perception.significance import grade_timeframe, rank_by_significance

# Marks closer than this multiple of ATR collide visually on a rendered chart.
MIN_LABEL_SEPARATION_ATR = 0.35

# Deliberately below the schema's 12-object ceiling. A professional context
# chart carries a handful of marks; the budget is a fence, not a target.
DEFAULT_STRUCTURE_LIMIT = 3
DEFAULT_CLUTTER_BUDGET = 8


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def plan_narrative_annotations(
    *,
    evidence_pack: Mapping[str, Any],
    structure_limit: int = DEFAULT_STRUCTURE_LIMIT,
    clutter_budget: int = DEFAULT_CLUTTER_BUDGET,
) -> dict[str, Any]:
    """Build a semantic annotation plan from the graph's narrative read.

    Returns the ``{clutter_budget, selections}`` payload the annotation bridge
    expects, plus a ``rationale`` describing why each object was chosen.
    """
    graph = evidence_pack.get("formal_structure_graph")
    if not isinstance(graph, Mapping):
        return _empty("no formal structure graph in evidence pack")

    narrative = graph.get("narrative_context")
    if not isinstance(narrative, Mapping):
        return _empty("graph carries no narrative context")

    timeframe = str(narrative.get("context_timeframe") or "")
    if not timeframe:
        return _empty(str(narrative.get("sentence") or "no resolved context timeframe"))

    selections: list[dict[str, Any]] = []
    rationale: list[str] = [f"Context timeframe {timeframe} {narrative.get('context_bias')}."]

    active_range = graph.get("active_range")
    if isinstance(active_range, Mapping) and active_range.get("range_id"):
        selections.append({
            "semantic_object_id": str(active_range["range_id"]),
            "timeframe": str(active_range.get("timeframe") or timeframe),
            "object_type": "range_zone",
            "label": f"{str(active_range.get('timeframe') or timeframe).upper()} Dealing Range",
            "reason": "Active range establishing premium/discount location.",
        })
        rationale.append(
            f"Range drawn first: price is in {active_range.get('price_location')}."
        )

    selections.extend(
        _structure_selections(
            evidence_pack=evidence_pack,
            timeframe=timeframe,
            limit=structure_limit,
            rationale=rationale,
        )
    )

    return {
        "clutter_budget": clutter_budget,
        "selections": selections[:clutter_budget],
        "rationale": rationale,
        "narrative_state": narrative.get("state"),
        "authority": "observe_only_narrative_selection",
        "signal_allowed": False,
    }


def _structure_selections(
    *,
    evidence_pack: Mapping[str, Any],
    timeframe: str,
    limit: int,
    rationale: list[str],
) -> list[dict[str, Any]]:
    payload = (evidence_pack.get("detector_candidates") or {}).get(timeframe)
    candles = (evidence_pack.get("ohlcv_windows") or {}).get(timeframe)
    if not isinstance(payload, Mapping) or not isinstance(candles, list) or not candles:
        rationale.append(f"No candidates or window for {timeframe}; structure omitted.")
        return []

    breaks = [
        b for b in (payload.get("structure_breaks") or [])
        if isinstance(b, Mapping)
        and b.get("confirmed_at")
        and not ((b.get("evidence") or {}).get("is_unconfirmed_probe"))
    ]
    if not breaks:
        rationale.append(f"No confirmed {timeframe} structure to draw.")
        return []

    summary = grade_timeframe(candles=candles, swings=[], structure_breaks=breaks)
    ranked = rank_by_significance(summary.scores, minimum_grade="intermediate")
    by_id = {str(b.get("object_id")): b for b in breaks}
    atr = summary.atr or 0.0

    chosen: list[dict[str, Any]] = []
    used_prices: list[float] = []
    for score in ranked:
        if len(chosen) >= limit:
            break
        brk = by_id.get(score.object_id)
        if not isinstance(brk, Mapping):
            continue
        scope = str(brk.get("structure_scope") or (brk.get("evidence") or {}).get("structure_scope") or "external")
        price = _f((brk.get("evidence") or {}).get("broken_price"))
        if price is None:
            continue
        # External structure owns the story; an internal twin sitting on the
        # same level would stack a second label on one line and hide it.
        if scope != "external" and any(abs(price - p) <= max(atr * MIN_LABEL_SEPARATION_ATR, 1e-9) for p in used_prices):
            rationale.append(
                f"Dropped internal {brk.get('break_type')} at {price:g}: duplicates external structure."
            )
            continue
        if any(abs(price - p) <= max(atr * MIN_LABEL_SEPARATION_ATR, 1e-9) for p in used_prices):
            rationale.append(f"Dropped {brk.get('break_type')} at {price:g}: too close to a stronger mark.")
            continue
        used_prices.append(price)
        label_scope = "" if scope == "external" else " Internal"
        chosen.append({
            "semantic_object_id": score.object_id,
            "timeframe": timeframe,
            "object_type": "structure_segment",
            "label": f"{timeframe.upper()}{label_scope} {brk.get('break_type') or 'BOS'}",
            "reason": f"Significant structure: {score.atr_multiple:.2f}x ATR displacement beyond the level.",
        })
        rationale.append(
            f"Drew {brk.get('break_type')} at {price:g} ({score.atr_multiple:.2f}x ATR, {score.grade})."
        )
    return chosen


def _empty(reason: str) -> dict[str, Any]:
    return {
        "clutter_budget": DEFAULT_CLUTTER_BUDGET,
        "selections": [],
        "rationale": [reason],
        "narrative_state": None,
        "authority": "observe_only_narrative_selection",
        "signal_allowed": False,
    }


__all__ = [
    "DEFAULT_CLUTTER_BUDGET",
    "DEFAULT_STRUCTURE_LIMIT",
    "MIN_LABEL_SEPARATION_ATR",
    "plan_narrative_annotations",
]
