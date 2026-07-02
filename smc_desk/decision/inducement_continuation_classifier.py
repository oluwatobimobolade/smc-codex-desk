"""Classify whether the current SMC move is inducement, continuation, or chase risk."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class InducementContinuationAssessment:
    state: str
    direction: str
    confidence: float
    continuation_confirmed_if: list[str] = field(default_factory=list)
    inducement_confirmed_if: list[str] = field(default_factory=list)
    do_not_chase_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "continuation_confirmed_if": list(self.continuation_confirmed_if),
            "inducement_confirmed_if": list(self.inducement_confirmed_if),
            "do_not_chase_reason": self.do_not_chase_reason,
            "evidence": dict(self.evidence),
        }


def classify_inducement_continuation(
    *,
    perception_by_tf: Mapping[str, Mapping[str, Any]],
    liquidity_sequence_by_tf: Mapping[str, Mapping[str, Any]],
    watch_state: Mapping[str, Any] | None,
    structure_hierarchy: Mapping[str, Mapping[str, Any]] | None = None,
) -> InducementContinuationAssessment:
    watch_state = watch_state or {}
    direction = str(watch_state.get("direction") or "neutral")
    if direction not in {"bullish", "bearish"}:
        return InducementContinuationAssessment(
            state="MOVE_NOT_STARTED",
            direction="neutral",
            confidence=0.1,
            evidence={"reason": "No usable directional model."},
        )

    execution_tf = perception_by_tf.get("15m") or {}
    setup_tf = perception_by_tf.get("1h") or execution_tf
    liq = liquidity_sequence_by_tf.get("15m") or liquidity_sequence_by_tf.get("1h") or {}
    active_poi = watch_state.get("active_poi") if isinstance(watch_state, Mapping) else None
    breaks = list(execution_tf.get("structure_breaks", []) or [])
    same_direction_breaks = [item for item in breaks if _direction(item.get("direction")) == direction]
    zones = _same_direction_zones(execution_tf, direction)
    last_price = _last_price(execution_tf) or _last_price(setup_tf)
    range_low, range_high = _range_bounds(structure_hierarchy or {}, preferred_tf="15m")
    near_target_liquidity = _near_target_liquidity(direction, last_price, range_low, range_high)
    buy_taken = bool(liq.get("buy_side_liquidity_taken"))
    sell_taken = bool(liq.get("sell_side_liquidity_taken"))
    has_directional_raid = buy_taken if direction == "bearish" else sell_taken
    has_opposite_side_taken = sell_taken if direction == "bearish" else buy_taken
    displaced = bool(same_direction_breaks)
    has_new_zone = bool(zones)

    continuation_if = _continuation_conditions(direction, zones, active_poi)
    inducement_if = _inducement_conditions(direction, zones, active_poi)
    evidence = {
        "has_directional_liquidity_raid": has_directional_raid,
        "opposite_side_liquidity_already_taken": has_opposite_side_taken,
        "same_direction_15m_break_count": len(same_direction_breaks),
        "same_direction_zone_count": len(zones),
        "active_poi_id": active_poi.get("poi_id") if isinstance(active_poi, Mapping) else None,
        "last_price": None if last_price is None else str(last_price),
        "near_target_liquidity": near_target_liquidity,
    }

    if has_directional_raid and displaced and has_new_zone and active_poi and str(active_poi.get("price_relation")) == "inside_poi":
        return InducementContinuationAssessment(
            state="CONTINUATION_CONFIRMED",
            direction=direction,
            confidence=0.78,
            continuation_confirmed_if=continuation_if,
            inducement_confirmed_if=inducement_if,
            evidence=evidence,
        )
    if displaced and has_new_zone and near_target_liquidity:
        return InducementContinuationAssessment(
            state="MOVE_STARTED_NOT_CHASEABLE",
            direction=direction,
            confidence=0.68,
            continuation_confirmed_if=continuation_if,
            inducement_confirmed_if=inducement_if,
            do_not_chase_reason="Price has already displaced toward the next liquidity pool; wait for retrace into the new LTF zone.",
            evidence=evidence,
        )
    if has_directional_raid and displaced and has_new_zone:
        return InducementContinuationAssessment(
            state="EARLY_CONTINUATION_CONFIRMATION",
            direction=direction,
            confidence=0.64,
            continuation_confirmed_if=continuation_if,
            inducement_confirmed_if=inducement_if,
            do_not_chase_reason="Shift exists, but continuation needs a retest/rejection instead of a chase entry.",
            evidence=evidence,
        )
    if displaced and not active_poi:
        return InducementContinuationAssessment(
            state="POSSIBLE_INDUCEMENT",
            direction=direction,
            confidence=0.48,
            continuation_confirmed_if=continuation_if,
            inducement_confirmed_if=inducement_if,
            do_not_chase_reason="Displacement exists without a certified active POI; wait for the market to prove whether this is continuation or inducement.",
            evidence=evidence,
        )
    return InducementContinuationAssessment(
        state="MOVE_NOT_STARTED",
        direction=direction,
        confidence=0.35,
        continuation_confirmed_if=continuation_if,
        inducement_confirmed_if=inducement_if,
        evidence=evidence,
    )


def _same_direction_zones(snapshot: Mapping[str, Any], direction: str) -> list[Mapping[str, Any]]:
    zones: list[Mapping[str, Any]] = []
    for key in ("order_blocks", "fvgs"):
        for item in snapshot.get(key, []) or []:
            if _direction(item.get("direction")) != direction:
                continue
            terminal = str(item.get("terminal_reason", "none")).lower()
            mitigation = str(item.get("mitigation_status", "")).lower()
            if terminal not in {"", "none"} or mitigation == "full":
                continue
            zones.append(item)
    return zones


def _continuation_conditions(
    direction: str,
    zones: list[Mapping[str, Any]],
    active_poi: Mapping[str, Any] | None = None,
) -> list[str]:
    zone_phrase = _zone_phrase(direction, zones, active_poi)
    if direction == "bearish":
        return [
            f"price retests {zone_phrase}",
            "price rejects from that supply",
            "price breaks the next sell-side liquidity after rejection",
        ]
    return [
        f"price retests {zone_phrase}",
        "price rejects from that demand",
        "price breaks the next buy-side liquidity after rejection",
    ]


def _inducement_conditions(
    direction: str,
    zones: list[Mapping[str, Any]],
    active_poi: Mapping[str, Any] | None = None,
) -> list[str]:
    zone_phrase = _zone_phrase(direction, zones, active_poi)
    if direction == "bearish":
        return [
            f"price reclaims above {zone_phrase}",
            "price holds above the reclaimed supply",
            "price expands back toward buy-side liquidity",
        ]
    return [
        f"price reclaims below {zone_phrase}",
        "price holds below the reclaimed demand",
        "price expands back toward sell-side liquidity",
    ]


def _zone_phrase(
    direction: str,
    zones: list[Mapping[str, Any]],
    active_poi: Mapping[str, Any] | None = None,
) -> str:
    active_phrase = _active_poi_phrase(active_poi)
    if active_phrase:
        return active_phrase
    if not zones:
        return f"new LTF {_side_name(direction)} zone"
    zone = zones[-1]
    return f"{zone.get('price_low')}-{zone.get('price_high')} {_side_name(direction)}"


def _active_poi_phrase(active_poi: Mapping[str, Any] | None) -> str | None:
    if not isinstance(active_poi, Mapping):
        return None
    if active_poi.get("validity_status") not in {None, "", "VALID_ACTIVE_SETUP_POI"}:
        return None
    low = active_poi.get("price_low")
    high = active_poi.get("price_high")
    if low in {None, ""} or high in {None, ""}:
        return None
    timeframe = str(active_poi.get("timeframe") or "").strip()
    kind = str(active_poi.get("kind") or _side_name(str(active_poi.get("direction") or "neutral"))).strip()
    prefix = f"active {timeframe} " if timeframe else "active "
    return f"{prefix}{kind} {low}-{high}"


def _side_name(direction: str) -> str:
    return "supply" if direction == "bearish" else "demand"


def _last_price(snapshot: Mapping[str, Any]) -> Decimal | None:
    value = snapshot.get("last_price")
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _range_bounds(hierarchy: Mapping[str, Mapping[str, Any]], *, preferred_tf: str) -> tuple[Decimal | None, Decimal | None]:
    item = hierarchy.get(preferred_tf) or hierarchy.get("1h") or {}
    dr = item.get("dealing_range") or {}
    try:
        low = Decimal(str(dr.get("range_low") or item.get("external_range_low")))
        high = Decimal(str(dr.get("range_high") or item.get("external_range_high")))
        return low, high
    except Exception:
        return None, None


def _near_target_liquidity(direction: str, price: Decimal | None, range_low: Decimal | None, range_high: Decimal | None) -> bool:
    if price is None or range_low is None or range_high is None or range_high <= range_low:
        return False
    span = range_high - range_low
    if direction == "bearish":
        return price <= range_low + span * Decimal("0.18")
    return price >= range_high - span * Decimal("0.18")


def _direction(value: Any) -> str:
    return str(getattr(value, "value", value)).lower()
