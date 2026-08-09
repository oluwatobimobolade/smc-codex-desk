"""Multi-timeframe narrative hierarchy (observe-only, additive).

The formal graph currently resolves multi-timeframe bias by unanimity::

    aligned_bias = aligned[0] if len(set(aligned)) == 1 else "mixed"

Any disagreement between 1d / 4h / 1h collapses to ``mixed``, which forces
``THESIS_ONLY``. That inverts how Smart Money Concepts actually reads a chart.

Timeframes disagreeing is not a contradiction — *a retracement is defined by
the child disagreeing with its parent*. Full alignment across every timeframe
only occurs mid-impulse, which is precisely when the entry has already gone.
So a unanimity rule abstains during exactly the conditions a trader waits for,
and accepts only when it is too late.

This module reads the same evidence hierarchically instead of democratically:

* the highest available context timeframe owns **bias**;
* a disagreeing child is classified as a **retracement inside** that bias,
  not as a vote against it;
* a child only threatens the parent when it body-closes beyond the parent's
  protected level — which is the existing, already-correct graph rule;
* the read then asks the question a trader asks first: **where is price being
  drawn to?**

Authority: observe-only. This module produces a reading, never a signal. It
does not promote, does not size, and does not create trade authority. It sits
beside ``parent_child_context`` rather than replacing it, so the existing
refusal contract is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

DIRECTIONS = {"bullish", "bearish"}

# Highest timeframe first: the first entry with a resolved bias owns context.
CONTEXT_PRIORITY = ("1d", "12h", "4h", "1h")
EXECUTION_TIMEFRAMES = ("15m", "5m")

# Narrative states, in the order a trader would name them.
ALIGNED_CONTINUATION = "ALIGNED_CONTINUATION"
RETRACEMENT_WITHIN_PARENT = "RETRACEMENT_WITHIN_PARENT"
PULLBACK_ENDING = "PULLBACK_ENDING"
PARENT_INVALIDATION_PENDING = "PARENT_INVALIDATION_PENDING"
RANGE_BOUND = "RANGE_BOUND"
INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


@dataclass(frozen=True)
class LiquidityDraw:
    """Where price is being drawn, and what it would take to get there."""

    direction: str = "unknown"
    target_price: float | None = None
    target_kind: str = "unknown"      # range_extreme | unswept_liquidity | protected_level
    target_object_id: str | None = None
    distance: float | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "target_price": self.target_price,
            "target_kind": self.target_kind,
            "target_object_id": self.target_object_id,
            "distance": self.distance,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class NarrativeRead:
    """One coherent multi-timeframe story."""

    state: str
    context_timeframe: str | None
    context_bias: str
    retracing_timeframes: tuple[str, ...] = ()
    confirming_timeframes: tuple[str, ...] = ()
    invalidating_timeframes: tuple[str, ...] = ()
    price_location: str = "unknown"
    draw: LiquidityDraw = field(default_factory=LiquidityDraw)
    expectation: str = ""
    invalidation_note: str = ""
    sentence: str = ""
    evidence_ids: tuple[str, ...] = ()
    schema: str = "mtf_narrative_read_v1"

    @property
    def is_coherent(self) -> bool:
        """True when the read tells a directional story a trader could act on.

        Deliberately excludes RANGE_BOUND and INSUFFICIENT_CONTEXT: those are
        honest non-reads, not stories.
        """
        return self.state in {
            ALIGNED_CONTINUATION,
            RETRACEMENT_WITHIN_PARENT,
            PULLBACK_ENDING,
        } and self.context_bias in DIRECTIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "state": self.state,
            "context_timeframe": self.context_timeframe,
            "context_bias": self.context_bias,
            "retracing_timeframes": list(self.retracing_timeframes),
            "confirming_timeframes": list(self.confirming_timeframes),
            "invalidating_timeframes": list(self.invalidating_timeframes),
            "price_location": self.price_location,
            "draw": self.draw.to_dict(),
            "expectation": self.expectation,
            "invalidation_note": self.invalidation_note,
            "sentence": self.sentence,
            "evidence_ids": list(self.evidence_ids),
            "is_coherent": self.is_coherent,
            "authority": "observe_only_narrative_read",
            "signal_allowed": False,
        }


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bias(node: Mapping[str, Any]) -> str:
    bias = str(node.get("external_bias") or "").lower()
    return bias if bias in DIRECTIONS else "unknown"


def _opposite(direction: str) -> str:
    return "bearish" if direction == "bullish" else "bullish"


def _protected_price(node: Mapping[str, Any], side: str) -> float | None:
    point = node.get(f"protected_{side}")
    if isinstance(point, Mapping):
        return _f(point.get("price"))
    return _f(point)


def _child_body_closed_beyond_parent(
    parent: Mapping[str, Any], child: Mapping[str, Any], child_bias: str
) -> bool:
    """Has the child body-closed beyond the parent's protected level?

    Only a *verified* protective level may retire a parent. When a timeframe
    node has no explicit protected price, the graph falls back to the broken
    swing price for both sides, so ``protected_high`` and ``protected_low``
    can be the same number sitting on the wrong side of the market. Trusting
    that would manufacture parent invalidations out of ordinary pullbacks.

    Doctrine says a child cannot flip its parent, so an unverifiable level
    resolves in the parent's favour: no invalidation.
    """
    side = "high" if child_bias == "bullish" else "low"
    level = _protected_price(parent, side)
    if level is None:
        return False
    if not _is_protective_level(parent, level, side):
        return False
    event = child.get("latest_external_break")
    if not isinstance(event, Mapping):
        return False
    body_close = _f(event.get("body_close_price"))
    if body_close is None:
        return False
    return body_close > level if child_bias == "bullish" else body_close < level


def _is_protective_level(parent: Mapping[str, Any], level: float, side: str) -> bool:
    """True when ``level`` can actually act as the parent's invalidation point.

    A protected high must sit above the parent's own break price, and a
    protected low below it. Degenerate levels — both sides resolving to the
    same derived number — fail this test and are treated as unverifiable.
    """
    opposite = _protected_price(parent, "low" if side == "high" else "high")
    if opposite is not None and opposite == level:
        return False
    event = parent.get("latest_external_break")
    if not isinstance(event, Mapping):
        return True
    reference = _f(event.get("broken_price"))
    if reference is None:
        return True
    return level > reference if side == "high" else level < reference


def resolve_liquidity_draw(
    *,
    context_bias: str,
    active_range: Mapping[str, Any] | None,
    current_price: float | None,
    liquidity_levels: Sequence[Mapping[str, Any]] = (),
    swept_object_ids: Sequence[str] = (),
) -> LiquidityDraw:
    """Answer 'where is price being drawn to?'.

    Preference order, matching how a trader reasons:

    1. the nearest **unswept** liquidity pool in the direction of context bias;
    2. otherwise the range extreme on that side.

    Liquidity already consumed cannot be a draw — it is spent.
    """
    if context_bias not in DIRECTIONS:
        return LiquidityDraw(rationale="No directional context; no draw can be named.")

    seeking_high = context_bias == "bullish"

    # Prefer the ranked liquidity model: it weighs what KIND of level this is
    # and which timeframe drew it, so a prior daily high outranks a 15m equal
    # high sitting closer to price. Proximity alone is only a tie-break.
    ranked = _ranked_draw(
        context_bias=context_bias,
        active_range=active_range,
        current_price=current_price,
        liquidity_levels=liquidity_levels,
        swept_object_ids=swept_object_ids,
    )
    if ranked is not None:
        return ranked
    candidates: list[tuple[float, str, str]] = []
    swept_ids = {str(value) for value in swept_object_ids}
    for level in liquidity_levels or ():
        if not isinstance(level, Mapping):
            continue
        status = str(level.get("activity_status") or level.get("lifecycle") or "active").lower()
        object_id = str(level.get("object_id") or level.get("liquidity_id") or "")
        if status in {"consumed", "swept", "terminal", "mitigated"} or object_id in swept_ids:
            continue
        price = _f(level.get("price")) or _f(level.get("price_high") if seeking_high else level.get("price_low"))
        if price is None or current_price is None:
            continue
        if seeking_high and price <= current_price:
            continue
        if not seeking_high and price >= current_price:
            continue
        candidates.append((abs(price - current_price), object_id, str(price)))

    if candidates:
        candidates.sort()
        distance, object_id, price_text = candidates[0]
        price = float(price_text)
        return LiquidityDraw(
            direction=context_bias,
            target_price=price,
            target_kind="unswept_liquidity",
            target_object_id=object_id or None,
            distance=distance,
            rationale=(
                f"Nearest unswept {'buy-side' if seeking_high else 'sell-side'} liquidity "
                f"at {price:g} sits in the direction of {context_bias} context."
            ),
        )

    if isinstance(active_range, Mapping):
        extreme = _f(active_range.get("high") if seeking_high else active_range.get("low"))
        if extreme is not None:
            distance = abs(extreme - current_price) if current_price is not None else None
            return LiquidityDraw(
                direction=context_bias,
                target_price=extreme,
                target_kind="range_extreme",
                target_object_id=str(active_range.get("range_id") or "") or None,
                distance=distance,
                rationale=(
                    f"No unswept pool recorded; the {'upper' if seeking_high else 'lower'} "
                    f"range extreme at {extreme:g} is the standing draw."
                ),
            )

    return LiquidityDraw(
        direction=context_bias,
        rationale="Context bias is known but no unswept pool or range extreme is available to name a draw.",
    )


def _ranked_draw(
    *,
    context_bias: str,
    active_range: Mapping[str, Any] | None,
    current_price: float | None,
    liquidity_levels: Sequence[Mapping[str, Any]],
    swept_object_ids: Sequence[str] = (),
) -> LiquidityDraw | None:
    """Resolve the draw through the ranked liquidity model, or None."""
    if not liquidity_levels or current_price is None:
        return None
    try:
        from smc_desk.perception.liquidity_model import build_liquidity_map, resolve_draw

        liquidity_map = build_liquidity_map(
            liquidity_levels=liquidity_levels,
            current_price=current_price,
            range_high=_f((active_range or {}).get("high")),
            range_low=_f((active_range or {}).get("low")),
            swept_object_ids=swept_object_ids,
        )
        pool = resolve_draw(liquidity_map, context_bias=context_bias)
    except Exception:  # noqa: BLE001 -- fall back to the simple rule below
        return None
    if pool is None:
        return None
    return LiquidityDraw(
        direction=context_bias,
        target_price=pool.price,
        target_kind=pool.kind,
        target_object_id=pool.object_id or None,
        distance=pool.distance,
        rationale=(
            f"Highest-ranked unswept {'buy-side' if context_bias == 'bullish' else 'sell-side'} "
            f"liquidity: {pool.kind} on {pool.timeframe} ({pool.scope} scope, "
            f"importance {pool.importance:.2f})."
        ),
    )


def read_narrative(
    *,
    timeframes: Mapping[str, Any],
    active_range: Mapping[str, Any] | None = None,
    current_price: float | None = None,
    liquidity_levels: Sequence[Mapping[str, Any]] = (),
    swept_object_ids: Sequence[str] = (),
) -> NarrativeRead:
    """Build the hierarchical read. Never returns 'mixed'.

    Every combination of timeframe biases resolves to a *named* market state.
    Where the old vote produced ``mixed`` and stopped, this produces
    ``RETRACEMENT_WITHIN_PARENT`` or ``PULLBACK_ENDING`` and continues.
    """
    nodes = {
        tf: node
        for tf, node in (timeframes or {}).items()
        if isinstance(node, Mapping)
    }
    context_tf: str | None = None
    context_bias = "unknown"
    for tf in CONTEXT_PRIORITY:
        node = nodes.get(tf)
        if node is not None and _bias(node) in DIRECTIONS:
            context_tf = tf
            context_bias = _bias(node)
            break

    price_location = "unknown"
    if isinstance(active_range, Mapping):
        price_location = str(active_range.get("price_location") or "unknown")
        if current_price is None:
            current_price = _f(active_range.get("current_price"))

    if context_tf is None:
        return NarrativeRead(
            state=INSUFFICIENT_CONTEXT,
            context_timeframe=None,
            context_bias="unknown",
            price_location=price_location,
            sentence="No context timeframe has a resolved external bias; the market cannot be read yet.",
        )

    context_node = nodes[context_tf]
    parent_index = CONTEXT_PRIORITY.index(context_tf)
    children = [
        tf for tf in CONTEXT_PRIORITY[parent_index + 1:] + EXECUTION_TIMEFRAMES
        if tf in nodes
    ]

    confirming: list[str] = []
    retracing: list[str] = []
    invalidating: list[str] = []
    evidence: list[str] = []

    protected_side = "low" if context_bias == "bullish" else "high"
    protected_level = _protected_price(context_node, protected_side)
    parent_break = context_node.get("latest_external_break")
    if isinstance(parent_break, Mapping) and parent_break.get("object_id"):
        evidence.append(str(parent_break["object_id"]))

    for tf in children:
        node = nodes[tf]
        child_bias = _bias(node)
        if child_bias not in DIRECTIONS:
            continue
        if child_bias == context_bias:
            confirming.append(tf)
            continue
        if _child_body_closed_beyond_parent(context_node, node, child_bias):
            invalidating.append(tf)
        else:
            retracing.append(tf)
        event = node.get("latest_external_break")
        if isinstance(event, Mapping) and event.get("object_id"):
            evidence.append(str(event["object_id"]))

    draw = resolve_liquidity_draw(
        context_bias=context_bias,
        active_range=active_range,
        current_price=current_price,
        liquidity_levels=liquidity_levels,
        swept_object_ids=swept_object_ids,
    )

    # State resolution, in trader priority order.
    if invalidating:
        state = PARENT_INVALIDATION_PENDING
        expectation = (
            f"{'/'.join(invalidating)} has body-closed beyond the {context_tf} protected "
            f"{protected_side}. Treat the {context_bias} context as under threat and wait for "
            "the parent to re-map rather than fading the break."
        )
        sentence = (
            f"{context_tf} {context_bias} context is being challenged: "
            f"{'/'.join(invalidating)} closed beyond its protected {protected_side}."
        )
    elif retracing and _lowest(retracing) and _has_flipped_back(nodes, retracing, context_bias):
        state = PULLBACK_ENDING
        expectation = (
            f"The {'/'.join(retracing)} pullback against {context_tf} {context_bias} context has "
            f"begun to turn back with the parent. This is the window where {context_bias} "
            "continuation setups form."
        )
        sentence = (
            f"{context_tf} is {context_bias}; the counter-trend move on {'/'.join(retracing)} "
            f"is rolling over back in line with the parent."
        )
    elif retracing:
        state = RETRACEMENT_WITHIN_PARENT
        expectation = (
            f"The {'/'.join(retracing)} move against {context_tf} {context_bias} context is a "
            "retracement inside the parent leg, not a reversal. Watch for it to exhaust into a "
            f"{context_bias} POI, and require lower-timeframe confirmation before acting."
        )
        sentence = (
            f"{context_tf} remains {context_bias}; {'/'.join(retracing)} is retracing inside that leg."
        )
    elif confirming:
        state = ALIGNED_CONTINUATION
        expectation = (
            f"{context_tf} and {'/'.join(confirming)} agree on {context_bias}. Alignment this "
            "complete usually means the impulse is already underway, so chasing is the main risk; "
            "wait for a retracement to a POI."
        )
        sentence = f"{context_tf} and {'/'.join(confirming)} are aligned {context_bias}."
    else:
        state = RANGE_BOUND
        expectation = (
            f"{context_tf} carries a {context_bias} bias but no child timeframe confirms or "
            "retraces against it; treat this as range behaviour until structure resolves."
        )
        sentence = f"{context_tf} is {context_bias} with no corroborating child structure."

    invalidation_note = (
        f"The {context_bias} read fails if price body-closes beyond the {context_tf} protected "
        f"{protected_side}"
        + (f" at {protected_level:g}." if protected_level is not None else ".")
    )

    return NarrativeRead(
        state=state,
        context_timeframe=context_tf,
        context_bias=context_bias,
        retracing_timeframes=tuple(retracing),
        confirming_timeframes=tuple(confirming),
        invalidating_timeframes=tuple(invalidating),
        price_location=price_location,
        draw=draw,
        expectation=expectation,
        invalidation_note=invalidation_note,
        sentence=sentence,
        evidence_ids=tuple(dict.fromkeys(evidence)),
    )


def _lowest(timeframes: Sequence[str]) -> str | None:
    order = CONTEXT_PRIORITY + EXECUTION_TIMEFRAMES
    ranked = [tf for tf in order if tf in timeframes]
    return ranked[-1] if ranked else None


def _has_flipped_back(
    nodes: Mapping[str, Any], retracing: Sequence[str], context_bias: str
) -> bool:
    """True when the fastest retracing timeframe has turned back toward the parent.

    A pullback is 'ending' when the lowest timeframe still counted as retracing
    shows an internal state pointing back at the parent bias — the earliest
    honest evidence that the counter-move is losing control.
    """
    lowest = _lowest(retracing)
    if lowest is None:
        return False
    node = nodes.get(lowest)
    if not isinstance(node, Mapping):
        return False
    internal_state = str(node.get("internal_state") or "").lower()
    return internal_state.startswith(context_bias)


def select_primary_poi(
    *,
    narrative: NarrativeRead,
    poi_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Choose ONE primary POI from the narrative instead of hedging.

    The current thesis offers a bullish *and* a bearish POI as "conditional
    route-map POIs" because a vote gives no basis to choose. A narrative does:
    the primary POI is the one aligned with context bias, sitting on the
    correct side of equilibrium, nearest to price in the retracement path.
    Everything else is returned as the explicit alternate.
    """
    if not narrative.is_coherent or not poi_candidates:
        return None
    wanted = narrative.context_bias
    aligned = [
        poi for poi in poi_candidates
        if isinstance(poi, Mapping)
        and str(poi.get("direction") or poi.get("bias") or "").lower() == wanted
        and str(poi.get("lifecycle") or "fresh").lower() not in {"invalidated", "terminal", "consumed"}
    ]
    if not aligned:
        return None

    def distance(poi: Mapping[str, Any]) -> float:
        low = _f(poi.get("price_low"))
        high = _f(poi.get("price_high"))
        if low is None or high is None:
            return float("inf")
        midpoint = (low + high) / 2.0
        target = narrative.draw.target_price
        if target is None:
            return abs(midpoint)
        return abs(midpoint - target)

    aligned.sort(key=distance)
    primary = dict(aligned[0])
    primary["selection_reason"] = (
        f"Aligned with {narrative.context_timeframe} {wanted} context and closest to the "
        f"{narrative.draw.target_kind} draw; chosen over {len(aligned) - 1} alternate(s)."
    )
    primary["alternates"] = [
        str(poi.get("object_id") or "") for poi in aligned[1:] if poi.get("object_id")
    ]
    return primary


__all__ = [
    "ALIGNED_CONTINUATION",
    "CONTEXT_PRIORITY",
    "INSUFFICIENT_CONTEXT",
    "PARENT_INVALIDATION_PENDING",
    "PULLBACK_ENDING",
    "RANGE_BOUND",
    "RETRACEMENT_WITHIN_PARENT",
    "LiquidityDraw",
    "NarrativeRead",
    "read_narrative",
    "resolve_liquidity_draw",
    "select_primary_poi",
]
