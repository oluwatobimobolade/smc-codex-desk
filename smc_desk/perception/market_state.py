"""Market state and the trader confirmation sequence (observe-only).

Two gaps this closes.

**The system had no memory.** Every run re-derived the chart from zero, so it
could not say what had changed since the last look, what it was still waiting
for, or which liquidity had been taken while it was not watching. A trader
does not re-read the market from scratch each candle; they carry a running
picture and update it.

**The system answered in one shot.** It produced a verdict per run instead of
moving through the states a trader actually occupies -- mapping context,
noticing a liquidity event, seeing displacement, marking a POI, waiting for
price to arrive, waiting for confirmation. The existing ``state_machine.py``
had usable states but was never wired to anything.

The sequence here is the one a disciplined trader follows:

    MAP_CONTEXT
      -> LIQUIDITY_EVENT_IDENTIFIED
      -> ACCEPTED_DISPLACEMENT
      -> POI_MAPPED
      -> PRICE_APPROACHING_POI
      -> PRICE_AT_POI
      -> LTF_CONFIRMATION_PENDING
      -> TRADE_PLAN_READY | INVALIDATED | EXPIRED

Every state names two things explicitly: **what we are waiting for** and
**what would invalidate the idea**. A state that cannot answer both is not a
state a trader would sit in.

Authority: observe-only. Reaching ``TRADE_PLAN_READY`` means the evidence
sequence is complete -- it is not a signal, not a size, and not permission to
execute. ``signal_allowed`` stays false at every state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

MAP_CONTEXT = "MAP_CONTEXT"
LIQUIDITY_EVENT_IDENTIFIED = "LIQUIDITY_EVENT_IDENTIFIED"
ACCEPTED_DISPLACEMENT = "ACCEPTED_DISPLACEMENT"
POI_MAPPED = "POI_MAPPED"
PRICE_APPROACHING_POI = "PRICE_APPROACHING_POI"
PRICE_AT_POI = "PRICE_AT_POI"
LTF_CONFIRMATION_PENDING = "LTF_CONFIRMATION_PENDING"
TRADE_PLAN_READY = "TRADE_PLAN_READY"
INVALIDATED = "INVALIDATED"
NO_CONTEXT = "NO_CONTEXT"

# Progress order. Terminal states sit outside it.
SEQUENCE = (
    NO_CONTEXT,
    MAP_CONTEXT,
    LIQUIDITY_EVENT_IDENTIFIED,
    ACCEPTED_DISPLACEMENT,
    POI_MAPPED,
    PRICE_APPROACHING_POI,
    PRICE_AT_POI,
    LTF_CONFIRMATION_PENDING,
    TRADE_PLAN_READY,
)
_RANK = {name: index for index, name in enumerate(SEQUENCE)}

# Price is "approaching" a POI when it sits within this multiple of the zone's
# own height, and "at" it once inside the zone.
APPROACH_ZONE_MULTIPLE = 2.0


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MarketState:
    """The running picture a trader carries between looks."""

    symbol: str = ""
    decision_time: str = ""
    state: str = NO_CONTEXT

    # Context
    context_timeframe: str | None = None
    bias: str = "unknown"
    narrative_state: str | None = None
    price_location: str = "unknown"
    current_price: float | None = None

    # Structure
    range_high: float | None = None
    range_low: float | None = None
    equilibrium: float | None = None
    protected_high: float | None = None
    protected_low: float | None = None

    # Liquidity
    draw_price: float | None = None
    draw_kind: str | None = None
    swept_liquidity_ids: tuple[str, ...] = ()
    unswept_liquidity_ids: tuple[str, ...] = ()

    # POI
    primary_poi_id: str | None = None
    primary_poi_low: float | None = None
    primary_poi_high: float | None = None
    alternate_poi_ids: tuple[str, ...] = ()

    # The two questions every state must answer
    waiting_for: str = ""
    invalidation: str = ""

    reasons: tuple[str, ...] = ()
    schema: str = "market_state_v1"

    @property
    def rank(self) -> int:
        return _RANK.get(self.state, -1)

    @property
    def is_terminal(self) -> bool:
        return self.state == INVALIDATED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "symbol": self.symbol,
            "decision_time": self.decision_time,
            "state": self.state,
            "context": {
                "timeframe": self.context_timeframe,
                "bias": self.bias,
                "narrative_state": self.narrative_state,
                "price_location": self.price_location,
                "current_price": self.current_price,
            },
            "structure": {
                "range_high": self.range_high,
                "range_low": self.range_low,
                "equilibrium": self.equilibrium,
                "protected_high": self.protected_high,
                "protected_low": self.protected_low,
            },
            "liquidity": {
                "draw_price": self.draw_price,
                "draw_kind": self.draw_kind,
                "swept_ids": list(self.swept_liquidity_ids),
                "unswept_ids": list(self.unswept_liquidity_ids),
            },
            "poi": {
                "primary_id": self.primary_poi_id,
                "primary_low": self.primary_poi_low,
                "primary_high": self.primary_poi_high,
                "alternates": list(self.alternate_poi_ids),
            },
            "waiting_for": self.waiting_for,
            "invalidation": self.invalidation,
            "reasons": list(self.reasons),
            "authority": "observe_only_market_state",
            "signal_allowed": False,
        }


@dataclass(frozen=True)
class StateTransition:
    """What changed between two looks at the same market."""

    previous_state: str
    current_state: str
    advanced: bool
    regressed: bool
    newly_swept_liquidity: tuple[str, ...] = ()
    poi_changed: bool = False
    bias_changed: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_state": self.previous_state,
            "current_state": self.current_state,
            "advanced": self.advanced,
            "regressed": self.regressed,
            "newly_swept_liquidity": list(self.newly_swept_liquidity),
            "poi_changed": self.poi_changed,
            "bias_changed": self.bias_changed,
            "notes": list(self.notes),
        }


def build_market_state(
    *,
    evidence_pack: Mapping[str, Any],
    primary_poi: Mapping[str, Any] | None = None,
) -> MarketState:
    """Derive the current state deterministically from certified evidence."""
    graph = evidence_pack.get("formal_structure_graph")
    if not isinstance(graph, Mapping):
        return MarketState(
            state=NO_CONTEXT,
            waiting_for="A formal structure graph before anything can be read.",
            invalidation="Not applicable without context.",
            reasons=("no formal structure graph in evidence pack",),
        )

    narrative = graph.get("narrative_context") if isinstance(graph.get("narrative_context"), Mapping) else {}
    active_range = graph.get("active_range") if isinstance(graph.get("active_range"), Mapping) else {}
    symbol = str(evidence_pack.get("symbol") or graph.get("symbol") or "")
    decision_time = str(graph.get("decision_time") or "")

    bias = str(narrative.get("context_bias") or "unknown")
    coherent = bool(narrative.get("is_coherent"))
    current_price = _f(active_range.get("current_price"))
    draw = narrative.get("draw") if isinstance(narrative.get("draw"), Mapping) else {}

    liquidity_map = _liquidity_map(evidence_pack, active_range, current_price)
    swept = tuple(p.object_id for p in liquidity_map.swept) if liquidity_map else ()
    unswept = tuple(p.object_id for p in liquidity_map.unswept) if liquidity_map else ()

    protected_high, protected_low = _protected_levels(graph, narrative)

    base = {
        "symbol": symbol,
        "decision_time": decision_time,
        "context_timeframe": narrative.get("context_timeframe"),
        "bias": bias,
        "narrative_state": narrative.get("state"),
        "price_location": str(active_range.get("price_location") or "unknown"),
        "current_price": current_price,
        "range_high": _f(active_range.get("high")),
        "range_low": _f(active_range.get("low")),
        "equilibrium": _f(active_range.get("equilibrium")),
        "protected_high": protected_high,
        "protected_low": protected_low,
        "draw_price": _f(draw.get("target_price")),
        "draw_kind": str(draw.get("target_kind") or "") or None,
        "swept_liquidity_ids": swept,
        "unswept_liquidity_ids": unswept,
    }

    invalidation = str(narrative.get("invalidation_note") or "") or "No invalidation level resolved."
    reasons: list[str] = []

    # 1. Context must exist and hold together before anything else counts.
    if not coherent or bias not in {"bullish", "bearish"}:
        reasons.append(f"narrative is {narrative.get('state') or 'unresolved'}; no directional context to build on")
        return MarketState(
            **base, state=NO_CONTEXT,
            waiting_for="A coherent higher-timeframe read before any setup can be mapped.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    if narrative.get("state") == "PARENT_INVALIDATION_PENDING":
        reasons.append("child structure has closed beyond the parent protected level")
        return MarketState(
            **base, state=INVALIDATED,
            waiting_for="The parent timeframe to re-map before this context is usable again.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    reasons.append(f"{base['context_timeframe']} {bias} context established")

    # 2. A named draw means the liquidity picture is readable.
    if base["draw_price"] is None:
        return MarketState(
            **base, state=MAP_CONTEXT,
            waiting_for="A resolvable draw on liquidity in the direction of context.",
            invalidation=invalidation, reasons=tuple(reasons),
        )
    reasons.append(f"draw on liquidity resolved: {base['draw_kind']} at {base['draw_price']:g}")

    # 3. Displacement: a significant confirmed break on the context timeframe.
    if not _has_significant_displacement(evidence_pack, str(base["context_timeframe"] or "")):
        return MarketState(
            **base, state=LIQUIDITY_EVENT_IDENTIFIED,
            waiting_for="Displacement -- a confirmed structural break carrying real energy.",
            invalidation=invalidation, reasons=tuple(reasons),
        )
    reasons.append("significant displacement present on the context timeframe")

    # 4. A primary POI must be selected before price behaviour matters.
    if not isinstance(primary_poi, Mapping) or not primary_poi.get("object_id"):
        return MarketState(
            **base, state=ACCEPTED_DISPLACEMENT,
            waiting_for="A causally-owned POI aligned with context to be mapped.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    poi_low = _f(primary_poi.get("price_low"))
    poi_high = _f(primary_poi.get("price_high"))
    base = {
        **base,
        "primary_poi_id": str(primary_poi.get("object_id")),
        "primary_poi_low": poi_low,
        "primary_poi_high": poi_high,
        "alternate_poi_ids": tuple(str(x) for x in (primary_poi.get("alternates") or [])),
    }
    reasons.append(f"primary POI mapped: {base['primary_poi_id']}")

    if current_price is None or poi_low is None or poi_high is None:
        return MarketState(
            **base, state=POI_MAPPED,
            waiting_for="A current price against which POI proximity can be judged.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    # 5-6. Where is price relative to the POI?
    low, high = min(poi_low, poi_high), max(poi_low, poi_high)
    height = max(high - low, 1e-9)
    if low <= current_price <= high:
        reasons.append("price is inside the POI")
        return MarketState(
            **base, state=PRICE_AT_POI,
            waiting_for=(
                "A lower-timeframe liquidity event plus displacement and a structural "
                "break in the direction of context."
            ),
            invalidation=invalidation, reasons=tuple(reasons),
        )

    distance = low - current_price if current_price < low else current_price - high
    if distance <= height * APPROACH_ZONE_MULTIPLE:
        reasons.append(f"price is {distance:g} from the POI (within {APPROACH_ZONE_MULTIPLE}x zone height)")
        return MarketState(
            **base, state=PRICE_APPROACHING_POI,
            waiting_for="Price to reach the POI. No entry is considered before arrival.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    reasons.append(f"price is {distance:g} away from the POI -- too far to act on")
    return MarketState(
        **base, state=POI_MAPPED,
        waiting_for="Price to travel toward the mapped POI.",
        invalidation=invalidation, reasons=tuple(reasons),
    )


def diff_states(previous: MarketState | None, current: MarketState) -> StateTransition:
    """What changed since the last look. This is the memory."""
    if previous is None:
        return StateTransition(
            previous_state="", current_state=current.state,
            advanced=True, regressed=False,
            notes=("first observation; no prior state to compare",),
        )

    notes: list[str] = []
    newly_swept = tuple(
        x for x in current.swept_liquidity_ids if x not in set(previous.swept_liquidity_ids)
    )
    if newly_swept:
        notes.append(f"liquidity taken since last look: {', '.join(newly_swept)}")

    bias_changed = previous.bias != current.bias
    if bias_changed:
        notes.append(f"context bias changed {previous.bias} -> {current.bias}")

    poi_changed = previous.primary_poi_id != current.primary_poi_id
    if poi_changed:
        notes.append(f"primary POI changed {previous.primary_poi_id} -> {current.primary_poi_id}")

    advanced = current.rank > previous.rank
    regressed = 0 <= current.rank < previous.rank
    if advanced:
        notes.append(f"advanced {previous.state} -> {current.state}")
    elif regressed:
        notes.append(f"regressed {previous.state} -> {current.state}")
    elif current.state == previous.state:
        notes.append(f"still {current.state}: {current.waiting_for}")

    return StateTransition(
        previous_state=previous.state, current_state=current.state,
        advanced=advanced, regressed=regressed,
        newly_swept_liquidity=newly_swept, poi_changed=poi_changed,
        bias_changed=bias_changed, notes=tuple(notes),
    )


def _liquidity_map(
    evidence_pack: Mapping[str, Any],
    active_range: Mapping[str, Any],
    current_price: float | None,
):
    try:
        from smc_desk.perception.liquidity_model import (
            build_liquidity_map,
            collect_liquidity_evidence,
        )

        levels, swept_ids = collect_liquidity_evidence(
            evidence_pack.get("detector_candidates") or {}
        )
        if not levels:
            return None
        return build_liquidity_map(
            liquidity_levels=levels, current_price=current_price,
            range_high=_f(active_range.get("high")), range_low=_f(active_range.get("low")),
            swept_object_ids=swept_ids,
        )
    except Exception:  # noqa: BLE001 -- descriptive layer, never fatal
        return None


def _protected_levels(
    graph: Mapping[str, Any], narrative: Mapping[str, Any]
) -> tuple[float | None, float | None]:
    timeframe = str(narrative.get("context_timeframe") or "")
    node = (graph.get("timeframes") or {}).get(timeframe)
    if not isinstance(node, Mapping):
        return None, None

    def level(key: str) -> float | None:
        point = node.get(key)
        if isinstance(point, Mapping):
            return _f(point.get("price"))
        return _f(point)

    return level("protected_high"), level("protected_low")


def _has_significant_displacement(evidence_pack: Mapping[str, Any], timeframe: str) -> bool:
    """True when the context timeframe carries a graded-significant break."""
    report = evidence_pack.get("structural_significance")
    if isinstance(report, Mapping):
        node = (report.get("timeframes") or {}).get(timeframe)
        if isinstance(node, Mapping) and node.get("major_object_ids"):
            return True
        if isinstance(node, Mapping) and node.get("tradeable_object_ids"):
            return True
    return False


__all__ = [
    "ACCEPTED_DISPLACEMENT",
    "APPROACH_ZONE_MULTIPLE",
    "INVALIDATED",
    "LIQUIDITY_EVENT_IDENTIFIED",
    "LTF_CONFIRMATION_PENDING",
    "MAP_CONTEXT",
    "NO_CONTEXT",
    "POI_MAPPED",
    "PRICE_APPROACHING_POI",
    "PRICE_AT_POI",
    "SEQUENCE",
    "TRADE_PLAN_READY",
    "MarketState",
    "StateTransition",
    "build_market_state",
    "diff_states",
]
