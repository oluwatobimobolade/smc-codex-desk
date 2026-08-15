"""The HH / HL / LH / LL sequence a reader uses to check the structure.

Two pieces of this repository were built and then never called by anything that
draws. `significance.rank_by_significance` decides which objects matter, and
`smc_visual_grammar.swing_label` names a swing against its predecessor. Neither
had a single consumer outside its own tests, so the charts carried the current
episode and nothing else -- a BOS tag floating in three weeks of bare candles,
with no way for a reader to see the structure it broke.

This module joins them. It takes the graded swings for one timeframe, selects
the chart-sized set of the most significant, and labels that sequence.

Why selection has to come before labelling
------------------------------------------
Labelling every detected swing would be worse than labelling none. On live
BTCUSDT the 4h carries 411 confirmed swings across the context window -- roughly
one per bar. HH/HL on that is not structure, it is a description of noise, and
it is exactly the over-annotation the significance layer was written to stop.

Selecting first also makes the labels *mean* something. A trader reading "HH"
is comparing against the previous swing high they consider structural, not
against whatever local wiggle happened to come before. So the comparison here
runs against the previous *selected* swing on the same side, which is the
sequence actually drawn on the chart. Any other choice would print labels that
contradict what the reader can see.

Authority: descriptive. Selection can only narrow what is drawn; it never
invents a swing the detector did not confirm, and creates no trade authority.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from smc_desk.perception.significance import (
    DEFAULT_DISPLAY_LIMIT,
    SignificanceScore,
    select_for_display,
)
from smc_desk.rendering.smc_visual_grammar import swing_label

# A swing high is the top of a bearish turn; a swing low the bottom of a bullish
# one. The detector's `direction` follows that convention.
_HIGH_SIDE = "bearish"
_LOW_SIDE = "bullish"


def _price_of(anchor: Any) -> float | None:
    for attribute in ("exact_price", "price_high", "price_low"):
        value = getattr(anchor, attribute, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def select_skeleton_swings(
    anchors: Sequence[Any],
    scores_by_id: Mapping[str, SignificanceScore],
    *,
    limit: int = DEFAULT_DISPLAY_LIMIT,
    minimum_grade: str = "intermediate",
) -> list[Any]:
    """The most significant swings, alternating sides, in chart order.

    Anchors with no significance score are dropped rather than assumed
    significant: an ungraded object is unproven, and this layer must never widen
    what a reader sees.

    **Sides must alternate.** Ranking on prominence alone is the obvious
    implementation and it produces an unreadable chart: on live BTCUSDT the six
    strongest 4h swings were all lows, so every label came out ``LL`` and the
    sequence described nothing. Structure *is* the alternation of highs and
    lows -- a reader checks HH against the previous high, HL against the
    previous low -- so the skeleton takes the strongest swing on each side in
    turn. Prominence still decides which high and which low; it does not get to
    decide that a chart has no highs on it.
    """
    by_id = {str(getattr(a, "object_id", "") or ""): a for a in anchors}
    graded = [scores_by_id[oid] for oid in by_id if oid in scores_by_id]
    ranked = select_for_display(graded, limit=None, minimum_grade=minimum_grade)

    queues: dict[str, list[Any]] = {_HIGH_SIDE: [], _LOW_SIDE: []}
    for score in ranked:
        anchor = by_id.get(score.object_id)
        side = str(getattr(anchor, "direction", "") or "").lower()
        if anchor is not None and side in queues:
            queues[side].append(anchor)

    selected: list[Any] = []
    side = _HIGH_SIDE
    while len(selected) < limit and (queues[_HIGH_SIDE] or queues[_LOW_SIDE]):
        # Take from the requested side when it still has candidates, otherwise
        # fall through so a one-sided market still gets a skeleton.
        source = side if queues[side] else (_LOW_SIDE if side == _HIGH_SIDE else _HIGH_SIDE)
        if not queues[source]:
            break
        selected.append(queues[source].pop(0))
        side = _LOW_SIDE if side == _HIGH_SIDE else _HIGH_SIDE

    # Ranking returns strongest-first; a labelled sequence has to read left to
    # right, so restore chart order before comparing neighbours.
    selected.sort(key=lambda a: (getattr(a, "end_index", 0) or 0, str(getattr(a, "object_id", ""))))
    return selected


def build_swing_skeleton(
    anchors: Sequence[Any],
    scores_by_id: Mapping[str, SignificanceScore],
    *,
    timeframe: str,
    limit: int = DEFAULT_DISPLAY_LIMIT,
    minimum_grade: str = "intermediate",
) -> list[dict[str, Any]]:
    """Return labelled swing markers for one timeframe, in chart order."""
    selected = select_skeleton_swings(
        anchors, scores_by_id, limit=limit, minimum_grade=minimum_grade
    )

    previous_price: dict[str, float] = {}
    objects: list[dict[str, Any]] = []
    for anchor in selected:
        price = _price_of(anchor)
        if price is None:
            continue
        side = str(getattr(anchor, "direction", "") or "").lower()
        if side not in (_HIGH_SIDE, _LOW_SIDE):
            continue

        earlier = previous_price.get(side)
        # No predecessor means no comparison to make, so `swing_label` returns
        # "" rather than guessing an HH or LL. That is the right contract, but
        # an empty label is not a drawable mark: the renderer falls back to the
        # object kind and stamps "SWING_HIGH" across the chart, which is both
        # ugly and louder than the real structure labels beside it.
        #
        # A bare "H" or "L" is the honest middle. It names what the mark is
        # without claiming a relationship to a swing that is not on the chart.
        is_higher = None if earlier is None else price > earlier
        label = swing_label(side, is_higher=is_higher) or (
            "H" if side == _HIGH_SIDE else "L"
        )
        previous_price[side] = price

        score = scores_by_id.get(str(getattr(anchor, "object_id", "") or ""))
        objects.append(
            {
                "object_type": "swing_marker",
                "semantic_object_id": f"{getattr(anchor, 'object_id', '')}:native_swing_marker",
                "timeframe": timeframe,
                "label": label,
                "reason": (
                    f"{score.grade if score else 'graded'} swing selected as structural "
                    "context; labelled against the previous drawn swing on this side."
                ),
                "kind": "swing_high" if side == _HIGH_SIDE else "swing_low",
                "direction": side,
                "price": price,
                "start_index": getattr(anchor, "start_index", None),
                "end_index": getattr(anchor, "end_index", None),
                "start_time": None,
                "end_time": None,
                "line_style": "dotted",
                "significance_grade": score.grade if score else None,
                "prominence_atr": round(score.atr_multiple, 4) if score else None,
                "evidence_object_ids": [str(getattr(anchor, "object_id", "") or "")],
                "importance": 3,
            }
        )
    return objects


__all__ = ["build_swing_skeleton", "select_skeleton_swings"]
