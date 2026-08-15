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
from datetime import datetime
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

    # Lower-timeframe confirmation / explicit point-of-entry model
    poi_arrival_time: str | None = None
    confirmation_timeframe: str | None = None
    confirmation_sweep_id: str | None = None
    confirmation_break_id: str | None = None
    entry_model: str | None = None
    entry_price: float | None = None

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
            "confirmation": {
                "poi_arrival_time": self.poi_arrival_time,
                "timeframe": self.confirmation_timeframe,
                "sweep_id": self.confirmation_sweep_id,
                "break_id": self.confirmation_break_id,
                "entry_model": self.entry_model,
                "entry_price": self.entry_price,
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

    # The V1 graph can supply a provisional story, but an enforcement-ready
    # causal replay disagreement means that story is not coherent enough to
    # advance the trader state machine.  Do not let a REVIEW_REQUIRED episode
    # graph coexist with an ALIGNED_CONTINUATION market-state headline.
    causal_graph = evidence_pack.get("formal_causal_episode_graph")
    invariants = causal_graph.get("invariants") if isinstance(causal_graph, Mapping) else None
    causal_contract = causal_graph.get("authority_contract") if isinstance(causal_graph, Mapping) else None
    enforcement_ready = (
        isinstance(causal_contract, Mapping)
        and causal_contract.get("enforcement_ready") is True
        and isinstance(invariants, Mapping)
    )
    reconciliation_status = (
        str(invariants.get("status") or "") if enforcement_ready else "PASS"
    )
    # A disagreement at or above the context timeframe means the story itself is
    # unknown, so nothing downstream can be trusted. A disagreement only below it
    # means the *entry* is not available while the read stands -- which is the
    # whole point of the scoped gate introduced in WP-SMC-21.
    #
    # Treating both alike here quietly undid that fix: the state machine stopped
    # at NO_CONTEXT, so `select_primary_poi` never ran and the POI ranking was
    # dead code on every live run, even ones the validator passed.
    entry_timing_withheld = reconciliation_status == "ENTRY_TIMING_WITHHELD"
    if enforcement_ready and reconciliation_status not in {"PASS", "ENTRY_TIMING_WITHHELD"}:
        violations = tuple(
            str(value)
            for value in (invariants.get("narrative_violations") or invariants.get("violations") or [])
        )
        reasons.extend(["causal episode reconciliation required", *violations])
        return MarketState(
            **{
                **base,
                "bias": "unknown",
                "narrative_state": "RECONCILIATION_REQUIRED",
            },
            state=NO_CONTEXT,
            waiting_for=(
                "The canonical structure graph and stricter causal replay to agree "
                "before directional context can advance."
            ),
            invalidation=invalidation,
            reasons=tuple(reasons),
        )
    if entry_timing_withheld:
        reasons.append(
            "entry timing unreconciled below the context timeframe: "
            f"{list(invariants.get('entry_timing_violations') or [])}; "
            "context and POI mapping continue, entry authority is withheld"
        )

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
    poi_object_id = (
        str(primary_poi.get("object_id") or primary_poi.get("poi_id") or "")
        if isinstance(primary_poi, Mapping)
        else ""
    )
    if not isinstance(primary_poi, Mapping) or not poi_object_id:
        return MarketState(
            **base, state=ACCEPTED_DISPLACEMENT,
            waiting_for="A causally-owned POI aligned with context to be mapped.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    poi_low = _f(primary_poi.get("price_low"))
    poi_high = _f(primary_poi.get("price_high"))
    base = {
        **base,
        "primary_poi_id": poi_object_id,
        "primary_poi_low": poi_low,
        "primary_poi_high": poi_high,
        "alternate_poi_ids": tuple(str(x) for x in (primary_poi.get("alternates") or [])),
        "poi_arrival_time": _poi_arrival_time(primary_poi),
    }
    reasons.append(f"primary POI mapped: {base['primary_poi_id']}")

    if current_price is None or poi_low is None or poi_high is None:
        return MarketState(
            **base, state=POI_MAPPED,
            waiting_for="A current price against which POI proximity can be judged.",
            invalidation=invalidation, reasons=tuple(reasons),
        )

    # 5-8. Where is price relative to the POI, and has a complete lower-
    # timeframe confirmation sequence occurred after arrival?
    low, high = min(poi_low, poi_high), max(poi_low, poi_high)
    height = max(high - low, 1e-9)
    confirmation = _lower_timeframe_confirmation(
        evidence_pack,
        bias=bias,
        context_timeframe=str(base["context_timeframe"] or ""),
        arrival_time=base["poi_arrival_time"],
    )
    if confirmation.get("ready") and entry_timing_withheld:
        # Everything the setup needs is present, and the timing-timeframe breaks
        # it would rest on failed the stricter replay. The read advanced; the
        # trade does not. Promoting here would hand back exactly the entry
        # authority the scoped gate exists to withhold.
        reasons.append(
            "lower-timeframe confirmation is present but its timeframe failed V3 replay; "
            "entry authority withheld"
        )
        return MarketState(
            **base,
            state=LTF_CONFIRMATION_PENDING,
            waiting_for=(
                "The lower-timeframe structure this confirmation rests on to survive "
                "the stricter causal replay before any entry is considered."
            ),
            invalidation=invalidation,
            reasons=tuple(reasons),
        )
    if confirmation.get("ready"):
        reasons.append(
            "lower-timeframe liquidity event, displacement and aligned structural break completed after POI arrival"
        )
        return MarketState(
            **base,
            state=TRADE_PLAN_READY,
            confirmation_timeframe=confirmation.get("timeframe"),
            confirmation_sweep_id=confirmation.get("sweep_id"),
            confirmation_break_id=confirmation.get("break_id"),
            entry_model="ltf_confirmation_close",
            entry_price=_f(confirmation.get("entry_price")),
            waiting_for=(
                "Human review of the evidence-bound plan; execution remains disabled."
            ),
            invalidation=invalidation,
            reasons=tuple(reasons),
        )
    if low <= current_price <= high:
        reasons.append("price is inside the POI")
        if base["poi_arrival_time"]:
            waiting = confirmation.get("waiting_for") or (
                "A lower-timeframe liquidity event plus displacement and a structural break in the direction of context."
            )
            return MarketState(
                **base,
                state=LTF_CONFIRMATION_PENDING,
                confirmation_timeframe=confirmation.get("timeframe"),
                confirmation_sweep_id=confirmation.get("sweep_id"),
                confirmation_break_id=confirmation.get("break_id"),
                entry_model="ltf_confirmation_close",
                waiting_for=str(waiting),
                invalidation=invalidation,
                reasons=tuple(reasons),
            )
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


def _poi_arrival_time(primary_poi: Mapping[str, Any]) -> str | None:
    explicit = primary_poi.get("first_touch_time")
    if explicit:
        return str(explicit)
    for event in primary_poi.get("event_history") or []:
        if not isinstance(event, Mapping):
            continue
        if str(event.get("event_type") or "") == "OBJECT_FIRST_TOUCHED":
            timestamp = event.get("timestamp")
            return str(timestamp) if timestamp else None
    return None


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _lower_timeframe_confirmation(
    evidence_pack: Mapping[str, Any],
    *,
    bias: str,
    context_timeframe: str,
    arrival_time: str | None,
) -> dict[str, Any]:
    """Resolve sweep -> displacement break -> confirmation-close entry.

    No arrival timestamp means the ordering cannot be proved, so the sequence
    fails closed.  Only 15m/5m confirmation is accepted for the current Desk
    workflow; HTF structure cannot double as its own entry trigger.
    """
    arrived = _dt(arrival_time)
    if arrived is None:
        return {
            "ready": False,
            "waiting_for": "A recorded POI arrival before lower-timeframe confirmation can be evaluated.",
        }

    detector = evidence_pack.get("detector_candidates") or {}
    context_minutes = {"1d": 1440, "4h": 240, "1h": 60, "15m": 15, "5m": 5}.get(
        context_timeframe,
        1440,
    )
    candidates = [
        timeframe
        for timeframe in ("15m", "5m")
        if {"15m": 15, "5m": 5}[timeframe] < context_minutes
        and isinstance(detector.get(timeframe), Mapping)
    ]
    if not candidates:
        return {
            "ready": False,
            "waiting_for": "Closed 15m/5m evidence after POI arrival.",
        }

    wanted_side = "sell_side" if bias == "bullish" else "buy_side"
    for timeframe in candidates:
        payload = detector.get(timeframe) or {}
        levels = {
            str(item.get("object_id") or ""): str(
                item.get("side") or (item.get("evidence") or {}).get("side") or ""
            )
            for item in payload.get("liquidity_levels") or []
            if isinstance(item, Mapping)
        }
        sweeps: list[tuple[datetime, Mapping[str, Any]]] = []
        for sweep in payload.get("sweeps") or []:
            if not isinstance(sweep, Mapping):
                continue
            when = _dt(sweep.get("confirmed_at") or sweep.get("pivot_time"))
            if when is None or when < arrived:
                continue
            evidence = sweep.get("evidence") if isinstance(sweep.get("evidence"), Mapping) else {}
            level_id = str(
                evidence.get("swept_level_id")
                or sweep.get("swept_level_id")
                or sweep.get("swept_liquidity_id")
                or ""
            )
            side = str(sweep.get("side") or evidence.get("side") or levels.get(level_id) or "")
            direction = str(sweep.get("direction") or "").lower()
            if direction == bias or side == wanted_side:
                sweeps.append((when, sweep))
        if not sweeps:
            continue
        sweep_time, sweep = sorted(sweeps, key=lambda item: item[0])[0]
        sweep_id = str(sweep.get("object_id") or "")

        qualifying: list[tuple[datetime, Mapping[str, Any], float]] = []
        for brk in payload.get("structure_breaks") or []:
            if not isinstance(brk, Mapping):
                continue
            when = _dt(brk.get("confirmed_at"))
            evidence = brk.get("evidence") if isinstance(brk.get("evidence"), Mapping) else {}
            metadata = brk.get("metadata") if isinstance(brk.get("metadata"), Mapping) else {}
            displacement = _f(
                evidence.get("displacement_strength")
                or (metadata.get("displacement") or {}).get("score")
            )
            if (
                when is None
                or when < sweep_time
                or str(brk.get("direction") or "").lower() != bias
                or evidence.get("is_unconfirmed_probe") is True
                or displacement is None
                or displacement < 0.45
            ):
                continue
            broken_price = _f(evidence.get("broken_price"))
            penetration = _f(evidence.get("body_close_penetration"))
            if broken_price is None or penetration is None:
                continue
            entry_price = (
                broken_price + penetration
                if bias == "bullish"
                else broken_price - penetration
            )
            qualifying.append((when, brk, entry_price))

        if qualifying:
            _, brk, entry_price = sorted(qualifying, key=lambda item: item[0])[0]
            return {
                "ready": True,
                "timeframe": timeframe,
                "sweep_id": sweep_id,
                "break_id": str(brk.get("object_id") or ""),
                "entry_price": entry_price,
            }
        return {
            "ready": False,
            "timeframe": timeframe,
            "sweep_id": sweep_id,
            "waiting_for": (
                f"A {timeframe} displacement break in the {bias} direction after {sweep_id or 'the liquidity sweep'}."
            ),
        }

    return {
        "ready": False,
        "timeframe": candidates[0],
        "waiting_for": (
            f"A {candidates[0]} {wanted_side.replace('_', '-')} liquidity sweep after POI arrival."
        ),
    }


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
