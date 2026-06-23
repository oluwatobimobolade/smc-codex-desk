"""Deterministic lifecycles for SMC chart annotations.

Renderers must show when an object became actionable and when it was resolved.
They must not invent a display duration such as ``30 bars`` or ``three days``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pandas as pd

from .models import AnalysisResult, StructureEvent, SwingPoint, TradePlan, Zone


@dataclass(frozen=True)
class ZoneLifecycle:
    activation_index: int
    end_index: int
    state: str
    is_active: bool


@dataclass(frozen=True)
class PlanLevel:
    label: str
    price: float


def _clamp_index(index: int | None, length: int) -> int:
    if length <= 0:
        return 0
    return max(0, min(int(index or 0), length - 1))


def _zone_value(zone: Zone | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(zone, dict):
        return zone.get(key, default)
    return getattr(zone, key, default)


def zone_visual_key(zone: Zone | dict[str, Any]) -> str:
    """Stable key shared by a case payload and its Pine overlay."""
    values = (
        _zone_value(zone, "kind"),
        _zone_value(zone, "direction"),
        _zone_value(zone, "label"),
        round(float(_zone_value(zone, "low")), 8),
        round(float(_zone_value(zone, "high")), 8),
        _zone_value(zone, "start_index"),
        _zone_value(zone, "end_index"),
    )
    return "|".join(str(value) for value in values)


def zone_display_confidence(analysis: AnalysisResult, df: pd.DataFrame, zone: Zone) -> str:
    """Shared salience grade for the PNG renderer and Pine snapshot."""
    from .perception_panel import HIGH_SIG, MED_SIG, _atr, _dealing_range, _zone_significance

    atr = _atr(df)
    dealing_range = _dealing_range(analysis, atr)
    score = _zone_significance(zone, atr, dealing_range)
    if score >= HIGH_SIG:
        return "high"
    if score >= MED_SIG:
        return "medium"
    return "low"


def event_display_confidence(analysis: AnalysisResult, df: pd.DataFrame, event: StructureEvent) -> str:
    """Internal structure can aid timing, but only swing/external marks headline a chart."""
    from .perception_panel import HIGH_SIG, MED_SIG, _atr, _dealing_range, _event_significance

    atr = _atr(df)
    dealing_range = _dealing_range(analysis, atr)
    score = _event_significance(event, df, atr, dealing_range)
    if score >= HIGH_SIG and event.structure_scope in {"swing", "external"}:
        return "high"
    if score >= MED_SIG:
        return "medium"
    return "low"


def _event_dedup_key(event: StructureEvent) -> tuple[Any, ...]:
    if event.label == "Liquidity Sweep":
        level = event.swept_level if event.swept_level is not None else event.price
        return (event.label, event.direction, round(float(level), 6))
    level = event.broken_level if event.broken_level is not None else event.price
    return ("structure", event.index, event.direction, round(float(level), 6))


def _event_priority(event: StructureEvent) -> tuple[int, int, int, int]:
    scope = {"external": 3, "swing": 2, "internal": 1, "unknown": 0}.get(event.structure_scope, 0)
    strength = {"strong": 2, "valid": 1, "weak": 0}.get(event.strength, 0)
    label = 2 if event.label == "CHoCH" else 1 if event.label == "BOS" else 0
    return (scope, strength, label, event.index)


def select_display_events(events: Sequence[StructureEvent]) -> list[StructureEvent]:
    """Collapse duplicate engine representations of the same visible break/sweep."""
    selected: dict[tuple[Any, ...], StructureEvent] = {}
    for event in events:
        key = _event_dedup_key(event)
        current = selected.get(key)
        if current is None or _event_priority(event) > _event_priority(current):
            selected[key] = event
    return sorted(selected.values(), key=lambda event: event.index)


def zone_activation_index(zone: Zone, length: int) -> int:
    """A zone becomes visible only after its confirming candle or final touch."""
    activation = zone.end_index if zone.end_index is not None else zone.start_index
    return _clamp_index(activation, length)


def _first_price_mitigation_index(df: pd.DataFrame, zone: Zone, activation: int) -> int | None:
    if zone.kind not in {"fvg", "order_block"}:
        return None
    for index in range(activation + 1, len(df)):
        low = float(df["low"].iloc[index])
        high = float(df["high"].iloc[index])
        if zone.direction == "bullish" and low <= zone.low:
            return index
        if zone.direction == "bearish" and high >= zone.high:
            return index
    return None


def _level_matches_zone(level: float, zone: Zone) -> bool:
    width = abs(zone.high - zone.low)
    tolerance = max(width * 0.6, abs(level) * 0.0001, 1e-9)
    return zone.low - tolerance <= level <= zone.high + tolerance


def _first_liquidity_sweep_index(
    zone: Zone,
    events: Iterable[StructureEvent],
    activation: int,
) -> int | None:
    for event in events:
        if event.label != "Liquidity Sweep" or event.index < activation:
            continue
        if event.direction != zone.direction:
            continue
        level = event.swept_level if event.swept_level is not None else event.price
        if _level_matches_zone(float(level), zone):
            return event.index
    return None


def zone_lifecycle(df: pd.DataFrame, zone: Zone, events: Sequence[StructureEvent]) -> ZoneLifecycle:
    """Return the exact data-window lifetime of a zone.

    Active FVGs/OBs continue only to the analysis decision candle. Liquidity
    pools end at the matching sweep. Fully mitigated zones end at the first
    candle that completes mitigation and are not active by default.
    """
    length = len(df)
    activation = zone_activation_index(zone, length)
    if length == 0:
        return ZoneLifecycle(activation_index=0, end_index=0, state="unavailable", is_active=False)

    if zone.kind == "liquidity":
        resolution = _first_liquidity_sweep_index(zone, events, activation)
        if resolution is not None:
            return ZoneLifecycle(activation, _clamp_index(resolution, length), "swept", False)
    else:
        resolution = _first_price_mitigation_index(df, zone, activation)
        if resolution is not None:
            return ZoneLifecycle(activation, resolution, "mitigated", False)

    if zone.status == "mitigated":
        # A compact/legacy payload can omit the resolving candle. Do not turn
        # that unknown history into a live-looking level.
        return ZoneLifecycle(activation, activation, "mitigated", False)
    return ZoneLifecycle(activation, length - 1, zone.status or "active", True)


def structure_origin_index(
    event: StructureEvent,
    swings: Sequence[SwingPoint],
    df: pd.DataFrame,
) -> int | None:
    """Find the protected swing that the BOS/CHoCH actually broke.

    If the source cannot be proven from stored swing data, the renderer shows
    the event marker without inventing a backward segment.
    """
    if event.label not in {"BOS", "CHoCH"} or event.broken_level is None:
        return None
    expected_kind = "high" if event.direction == "bullish" else "low"
    candidates = [
        swing
        for swing in swings
        if swing.kind == expected_kind and swing.index < event.index
    ]
    if not candidates:
        return None
    level = float(event.broken_level)
    best = min(candidates, key=lambda swing: (abs(swing.price - level), -swing.index))
    price_range = float(df["high"].max() - df["low"].min()) if not df.empty else 0.0
    tolerance = max(abs(level) * 0.0001, price_range * 0.002, 1e-9)
    if abs(best.price - level) > tolerance:
        return None
    return int(best.index)


def has_actionable_plan(plan: TradePlan) -> bool:
    return (
        plan.verdict in {"Execute", "Watch", "Watch Retrace"}
        and plan.entry_type != "no_trade"
        and plan.entry_low is not None
        and plan.entry_high is not None
    )


def plan_levels(plan: TradePlan) -> list[PlanLevel]:
    """Plan values only exist visually when there is a real entry geometry."""
    if not has_actionable_plan(plan):
        return []
    levels: list[PlanLevel] = []
    seen: set[float] = set()

    def add(label: str, value: float | None) -> None:
        if value is None:
            return
        price = round(float(value), 8)
        if price in seen:
            return
        seen.add(price)
        levels.append(PlanLevel(label=label, price=price))

    add("Execution SL", plan.invalidation)
    if plan.structural_invalidation != plan.invalidation:
        add("Structural invalidation", plan.structural_invalidation)
    for index, target in enumerate(plan.targets, start=1):
        add(f"Target {index}", target)
    return levels


def _timestamp_at(df: pd.DataFrame, index: int) -> str:
    return pd.Timestamp(df["timestamp"].iloc[index]).isoformat()


def build_visual_geometry_payload(analysis: AnalysisResult, df: pd.DataFrame) -> dict[str, Any]:
    """Persist exact x-coordinates for a case/TradingView snapshot.

    Case payloads only retain index-oriented engine objects. This compact block
    binds those indices to the closed-candle timestamps used for the decision.
    """
    zones: list[dict[str, Any]] = []
    for zone in analysis.zones:
        lifecycle = zone_lifecycle(df, zone, analysis.events)
        zones.append(
            {
                "key": zone_visual_key(zone),
                "activation_time": _timestamp_at(df, lifecycle.activation_index),
                "end_time": _timestamp_at(df, lifecycle.end_index),
                "state": lifecycle.state,
                "active": lifecycle.is_active,
                "display_confidence": zone_display_confidence(analysis, df, zone),
            }
        )

    structures: list[dict[str, Any]] = []
    display_events: list[dict[str, Any]] = []
    for event in select_display_events(analysis.events):
        display_events.append(
            {
                "event_index": int(event.index),
                "event_label": event.label,
                "direction": event.direction,
                "display_confidence": event_display_confidence(analysis, df, event),
            }
        )
        origin = structure_origin_index(event, analysis.swings, df)
        if origin is None:
            continue
        end = _clamp_index(event.index, len(df))
        structures.append(
            {
                "event_index": int(event.index),
                "event_label": event.label,
                "start_time": _timestamp_at(df, origin),
                "end_time": _timestamp_at(df, end),
                "price": float(event.broken_level),
            }
        )

    return {
        "schema_version": "1.0",
        "as_of": _timestamp_at(df, len(df) - 1),
        "zones": zones,
        "events": display_events,
        "structure_segments": structures,
        "plan": {"actionable": has_actionable_plan(analysis.trade_plan)},
    }
