"""Liquidity model: classify, rank, and resolve the draw (observe-only).

The detector answers "where are the equal highs and lows?". A trader asks a
different set of questions, in this order:

    Where has price come from?
    What liquidity has already been taken?
    What remains untouched?
    Which of it makes structural sense as the next target?

The existing `liquidity.py` handles detection: equal-level clustering within a
tolerance, sweep events, single-swing levels. What it does not do is say which
pool *matters*. Every level arrives with equal standing, so anything consuming
it either drowns or picks the nearest, which is why the draw-on-liquidity in
the narrative layer began life as "closest unswept pool".

This module supplies the missing judgement:

* **Classification** — what kind of liquidity is this? An equal-highs cluster
  is not the same object as a prior daily high, and neither is inducement.
* **Scope** — internal (inside the dealing range) or external (beyond it).
  External liquidity is what a completed leg reaches for; internal liquidity
  is what gets taken on the way.
* **State** — swept or unswept, and how recently. Swept liquidity is spent:
  it cannot be a draw, though it remains part of the story of where price
  has been.
* **Importance** — a deterministic score combining touch count, timeframe,
  scope, freshness and structural role.

Authority: observe-only and descriptive. Ranking never promotes an object,
never creates a signal, and never invents a level the detector did not emit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# Liquidity kinds, ordered by how much weight a trader typically gives them.
KIND_WEIGHTS: dict[str, float] = {
    "prior_week_high": 1.00,
    "prior_week_low": 1.00,
    "prior_day_high": 0.85,
    "prior_day_low": 0.85,
    "equal_highs": 0.75,
    "equal_lows": 0.75,
    "range_extreme": 0.70,
    "session_high": 0.55,
    "session_low": 0.55,
    "swing_high": 0.40,
    "swing_low": 0.40,
    "inducement": 0.30,
    "unknown": 0.20,
}

TIMEFRAME_WEIGHTS: dict[str, float] = {
    "1d": 1.00, "12h": 0.85, "4h": 0.70, "1h": 0.55, "15m": 0.35, "5m": 0.20,
}

# An external pool sits beyond the dealing range: it is what a completed leg
# reaches for. Internal liquidity is taken on the way and rarely ends a move.
SCOPE_WEIGHTS: dict[str, float] = {"external": 1.0, "internal": 0.55, "unknown": 0.5}

SWEPT_STATES = {"consumed", "swept", "terminal", "mitigated", "taken"}


@dataclass(frozen=True)
class LiquidityPool:
    """One classified, scored liquidity reference."""

    object_id: str
    price: float
    side: str                 # buy_side (above) | sell_side (below)
    kind: str
    timeframe: str
    scope: str                # internal | external | unknown
    swept: bool
    touch_count: int = 1
    importance: float = 0.0
    distance: float | None = None
    reasons: tuple[str, ...] = ()

    @property
    def is_available_draw(self) -> bool:
        """Only unswept liquidity can be a target. Swept liquidity is spent."""
        return not self.swept

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "price": self.price,
            "side": self.side,
            "kind": self.kind,
            "timeframe": self.timeframe,
            "scope": self.scope,
            "swept": self.swept,
            "touch_count": self.touch_count,
            "importance": round(self.importance, 4),
            "distance": self.distance,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class LiquidityMap:
    """The full picture: what is taken, what remains, what is being sought."""

    pools: tuple[LiquidityPool, ...] = ()
    current_price: float | None = None
    range_high: float | None = None
    range_low: float | None = None
    schema: str = "liquidity_map_v1"

    @property
    def unswept(self) -> tuple[LiquidityPool, ...]:
        return tuple(p for p in self.pools if p.is_available_draw)

    @property
    def swept(self) -> tuple[LiquidityPool, ...]:
        return tuple(p for p in self.pools if p.swept)

    def above(self) -> tuple[LiquidityPool, ...]:
        if self.current_price is None:
            return ()
        return tuple(p for p in self.unswept if p.price > self.current_price)

    def below(self) -> tuple[LiquidityPool, ...]:
        if self.current_price is None:
            return ()
        return tuple(p for p in self.unswept if p.price < self.current_price)

    def ranked(self, side: str | None = None) -> list[LiquidityPool]:
        """Unswept pools, most important first. Ties break on proximity."""
        pools = [p for p in self.unswept if side is None or p.side == side]
        pools.sort(key=lambda p: (-p.importance, p.distance if p.distance is not None else 0.0, p.object_id))
        return pools

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "current_price": self.current_price,
            "range_high": self.range_high,
            "range_low": self.range_low,
            "counts": {
                "total": len(self.pools),
                "unswept": len(self.unswept),
                "swept": len(self.swept),
            },
            "pools": [p.to_dict() for p in self.pools],
            "authority": "observe_only_descriptive",
            "signal_allowed": False,
        }


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evidence(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("evidence")
    return value if isinstance(value, Mapping) else {}


def collect_liquidity_evidence(
    detector_candidates: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], tuple[str, ...]]:
    """Collect levels and the level ids consumed by real sweep objects.

    The detector deliberately emits sweeps as separate objects. Consumers must
    join ``sweep.evidence.swept_level_id`` back to the referenced level rather
    than waiting for the level's lifecycle field to be mutated.
    """
    levels: list[Mapping[str, Any]] = []
    swept_ids: list[str] = []
    for payload in (detector_candidates or {}).values():
        if not isinstance(payload, Mapping):
            continue
        found = payload.get("liquidity_levels")
        if isinstance(found, Sequence) and not isinstance(found, (str, bytes)):
            levels.extend(value for value in found if isinstance(value, Mapping))
        sweeps = payload.get("sweeps")
        if not isinstance(sweeps, Sequence) or isinstance(sweeps, (str, bytes)):
            continue
        for sweep in sweeps:
            if not isinstance(sweep, Mapping):
                continue
            swept_id = sweep.get("swept_level_id") or _evidence(sweep).get("swept_level_id")
            if swept_id is not None and str(swept_id) not in swept_ids:
                swept_ids.append(str(swept_id))
    return levels, tuple(swept_ids)


def classify_kind(record: Mapping[str, Any]) -> str:
    """Name the liquidity type from whatever the detector recorded."""
    evidence = _evidence(record)
    explicit = str(
        record.get("kind")
        or record.get("liquidity_kind")
        or evidence.get("level_kind")
        or ""
    ).lower()
    if explicit in KIND_WEIGHTS:
        return explicit
    # Labels arrive human-written ("Prior Week High") and ids machine-written
    # ("prior_week_high"); normalise both to one token form before matching.
    label = f"{record.get('label', '')} {record.get('object_id', '')} {explicit}".lower()
    label = label.replace(" ", "_").replace("-", "_")
    for candidate in (
        "prior_week_high", "prior_week_low", "prior_day_high", "prior_day_low",
        "equal_highs", "equal_lows", "session_high", "session_low", "inducement",
    ):
        if candidate in label:
            return candidate
    constituents = record.get("constituent_swing_ids") or evidence.get("constituent_swing_ids") or []
    touches = int(record.get("touch_count") or evidence.get("touch_count") or len(constituents) or 0)
    if touches >= 2:
        side = str(record.get("side") or evidence.get("side") or "").lower()
        return "equal_highs" if "buy" in side or "high" in label else "equal_lows"
    return "unknown"


def classify_scope(price: float, range_high: float | None, range_low: float | None) -> str:
    """External liquidity sits beyond the dealing range; internal sits inside."""
    if range_high is None or range_low is None or range_high <= range_low:
        return "unknown"
    if price > range_high or price < range_low:
        return "external"
    return "internal"


def score_importance(
    *,
    kind: str,
    timeframe: str,
    scope: str,
    touch_count: int,
    swept: bool,
    reasons: list[str],
) -> float:
    """Deterministic importance in [0, 1].

    Weighted so that *what kind of level it is* and *which timeframe drew it*
    dominate, because those are the two things a trader checks first. Touch
    count refines rather than decides: a triple-tapped 15m equal high is still
    not a prior daily high.
    """
    if swept:
        reasons.append("already swept: spent, cannot be a draw")
        return 0.0

    kind_w = KIND_WEIGHTS.get(kind, KIND_WEIGHTS["unknown"])
    tf_w = TIMEFRAME_WEIGHTS.get(timeframe, 0.3)
    scope_w = SCOPE_WEIGHTS.get(scope, SCOPE_WEIGHTS["unknown"])
    # Two touches is the meaningful step; beyond four adds little.
    touch_w = min(1.0, 0.6 + 0.2 * max(0, min(touch_count, 4) - 1))

    score = (kind_w * 0.40) + (tf_w * 0.30) + (scope_w * 0.20) + (touch_w * 0.10)
    reasons.append(f"{kind} on {timeframe} ({scope} scope, {touch_count} touch(es))")
    return round(min(1.0, score), 6)


def build_liquidity_map(
    *,
    liquidity_levels: Iterable[Mapping[str, Any]],
    current_price: float | None = None,
    range_high: float | None = None,
    range_low: float | None = None,
    swept_object_ids: Sequence[str] = (),
) -> LiquidityMap:
    """Classify, score and assemble every detected level into one map."""
    swept_ids = {str(x) for x in swept_object_ids}
    pools: list[LiquidityPool] = []

    for record in liquidity_levels or ():
        if not isinstance(record, Mapping):
            continue
        object_id = str(
            record.get("object_id") or record.get("liquidity_id") or ""
        )
        if not object_id:
            continue
        price = _f(record.get("price"))
        if price is None:
            low, high = _f(record.get("price_low")), _f(record.get("price_high"))
            if low is not None and high is not None:
                price = (low + high) / 2.0
        if price is None:
            continue

        evidence = _evidence(record)
        status = str(
            record.get("activity_status")
            or record.get("lifecycle")
            or evidence.get("activity_status")
            or "active"
        ).lower()
        swept = status in SWEPT_STATES or object_id in swept_ids

        side = str(record.get("side") or evidence.get("side") or "").lower()
        if side not in {"buy_side", "sell_side"}:
            side = "buy_side" if (current_price is not None and price > current_price) else "sell_side"

        kind = classify_kind(record)
        scope = classify_scope(price, range_high, range_low)
        touches = int(
            record.get("touch_count")
            or evidence.get("touch_count")
            or len(record.get("constituent_swing_ids") or evidence.get("constituent_swing_ids") or [])
            or 1
        )
        timeframe = str(record.get("timeframe") or "unknown")

        reasons: list[str] = []
        importance = score_importance(
            kind=kind, timeframe=timeframe, scope=scope,
            touch_count=touches, swept=swept, reasons=reasons,
        )
        pools.append(LiquidityPool(
            object_id=object_id, price=price, side=side, kind=kind,
            timeframe=timeframe, scope=scope, swept=swept, touch_count=touches,
            importance=importance,
            distance=abs(price - current_price) if current_price is not None else None,
            reasons=tuple(reasons),
        ))

    return LiquidityMap(
        pools=tuple(pools), current_price=current_price,
        range_high=range_high, range_low=range_low,
    )


def resolve_draw(
    liquidity_map: LiquidityMap,
    *,
    context_bias: str,
) -> LiquidityPool | None:
    """The most important unswept pool in the direction of context bias.

    This replaces "nearest unswept pool". Nearest is a tie-break, not a
    reason: a trader steps over a minor internal pool to reach a prior daily
    high, and the ranking has to reflect that.
    """
    if context_bias not in {"bullish", "bearish"}:
        return None
    side = "buy_side" if context_bias == "bullish" else "sell_side"
    ranked = liquidity_map.ranked(side=side)
    if liquidity_map.current_price is not None:
        ranked = [
            p for p in ranked
            if (p.price > liquidity_map.current_price) == (context_bias == "bullish")
        ]
    return ranked[0] if ranked else None


__all__ = [
    "KIND_WEIGHTS",
    "SCOPE_WEIGHTS",
    "TIMEFRAME_WEIGHTS",
    "LiquidityMap",
    "LiquidityPool",
    "build_liquidity_map",
    "classify_kind",
    "classify_scope",
    "collect_liquidity_evidence",
    "resolve_draw",
    "score_importance",
]
