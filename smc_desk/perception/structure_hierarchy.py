"""Professional SMC structure hierarchy.

Raw detector events answer "what broke?" This layer answers the trader question:
did external bias really change, or is price only retracing internally inside an
active dealing range?
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from smc_desk.perception.dealing_range import DealingRange, build_dealing_range
from smc_desk.perception.displacement import DisplacementProfile, score_break_displacement


MIN_RESEARCH_DEPTH = {"15m": 1500, "1h": 1000, "4h": 500, "1d": 365}


@dataclass(frozen=True)
class StructureHierarchy:
    timeframe: str
    external_bias: str
    external_range_high: str | None
    external_range_low: str | None
    protected_high: str | None
    protected_low: str | None
    internal_state: str
    structure_phase: str
    bias_can_flip: bool
    latest_external_break_id: str | None
    latest_internal_break_id: str | None
    depth_status: str
    evidence: dict[str, Any]
    dealing_range: DealingRange | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "external_bias": self.external_bias,
            "external_range_high": self.external_range_high,
            "external_range_low": self.external_range_low,
            "protected_high": self.protected_high,
            "protected_low": self.protected_low,
            "internal_state": self.internal_state,
            "structure_phase": self.structure_phase,
            "bias_can_flip": self.bias_can_flip,
            "latest_external_break_id": self.latest_external_break_id,
            "latest_internal_break_id": self.latest_internal_break_id,
            "depth_status": self.depth_status,
            "dealing_range": None if self.dealing_range is None else self.dealing_range.to_dict(),
            "evidence": self.evidence,
        }


_TF_ORDER = ["1d", "4h", "1h", "15m", "5m", "1m"]


def build_mtf_structure_hierarchy(
    perception_by_tf: Mapping[str, Mapping[str, Any]],
    *,
    current_prices: Mapping[str, Decimal | str | float] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build hierarchies HTF -> LTF so each child is reconciled against its parent.

    Cross-timeframe subordination: a child's opposing break may only flip the child's
    external bias if it breaks the PARENT's protected level by confirmed body close.
    Otherwise it is recorded as an internal retracement and the child stays aligned to
    the parent leg. Output preserves the caller's key order.
    """
    prices = current_prices or {}
    ordered = sorted(perception_by_tf.keys(), key=lambda tf: _TF_ORDER.index(tf) if tf in _TF_ORDER else 99)
    built: dict[str, StructureHierarchy] = {}
    parent_context: dict[str, Any] | None = None
    for timeframe in ordered:
        hierarchy = build_structure_hierarchy(
            timeframe=timeframe,
            snapshot=perception_by_tf[timeframe],
            current_price=prices.get(timeframe),
            parent_context=parent_context,
        )
        built[timeframe] = hierarchy
        parent_context = {
            "timeframe": timeframe,
            "external_bias": hierarchy.external_bias,
            "protected_high": hierarchy.protected_high,
            "protected_low": hierarchy.protected_low,
            "external_range_high": hierarchy.external_range_high,
            "external_range_low": hierarchy.external_range_low,
            "latest_external_break_confirmed_at": hierarchy.evidence.get("latest_external_break_confirmed_at"),
        }
    return {timeframe: built[timeframe].to_dict() for timeframe in perception_by_tf if timeframe in built}


def build_structure_hierarchy(
    *,
    timeframe: str,
    snapshot: Mapping[str, Any],
    current_price: Decimal | str | float | None = None,
    parent_context: Mapping[str, Any] | None = None,
) -> StructureHierarchy:
    breaks = _confirmed_breaks(snapshot.get("structure_breaks", []) or [])
    fvgs = snapshot.get("fvgs", []) or []
    structure_state = snapshot.get("structure_state", {}) or {}
    parent_bias, parent_ceiling, parent_floor = _parent_levels(parent_context)
    parent_since = _parse_dt((parent_context or {}).get("latest_external_break_confirmed_at"))
    # A child inherits its parent's leg by default. An opposing internal break cannot flip
    # the child unless that break also breaches the parent's protected level (subordination).
    external_bias = parent_bias or "neutral"
    latest_external_break: Mapping[str, Any] | None = None
    latest_internal_break: Mapping[str, Any] | None = None
    last_strong_break: Mapping[str, Any] | None = None
    last_opposite_non_flip: Mapping[str, Any] | None = None
    last_profile: DisplacementProfile | None = None

    for brk in breaks:
        break_time = _parse_dt(brk.get("confirmed_at") or brk.get("candidate_at"))
        if parent_since and break_time and break_time < parent_since:
            continue
        profile = score_break_displacement(brk, fvgs=fvgs)
        direction = _direction(brk)
        scope = _break_scope(brk)
        if scope == "internal":
            latest_internal_break = brk
            if external_bias in {"bullish", "bearish"} and direction != external_bias:
                last_opposite_non_flip = brk
            last_profile = profile
            continue
        if external_bias == "neutral" and profile.break_quality in {"moderate", "strong"}:
            external_bias = direction
            latest_external_break = brk
            if profile.valid_for_bias_flip:
                last_strong_break = brk
        elif direction == external_bias:
            latest_external_break = brk
            if profile.valid_for_bias_flip:
                last_strong_break = brk
        elif profile.valid_for_bias_flip and _breaks_parent_protection(
            brk, direction, parent_ceiling, parent_floor, parent_context
        ):
            external_bias = direction
            latest_external_break = brk
            last_strong_break = brk
            last_opposite_non_flip = None
        else:
            # Opposing break that does NOT breach the parent leg: an internal retracement.
            latest_internal_break = brk
            last_opposite_non_flip = brk
        last_profile = profile

    if external_bias == "neutral":
        fallback = structure_state.get("current_direction")
        external_bias = fallback if fallback in {"bullish", "bearish"} else "neutral"

    internal_state = _internal_state(external_bias, last_opposite_non_flip)
    phase = _structure_phase(external_bias, internal_state)
    protected_high, protected_low = _protected_prices(snapshot, structure_state)
    price = current_price if current_price is not None else _price_from_snapshot(snapshot)
    if price is not None:
        dealing_range = build_dealing_range(
            timeframe=timeframe,
            snapshot=snapshot,
            current_price=price,
            protected_high=protected_high,
            protected_low=protected_low,
            parent_context=parent_context,
        )
    else:
        dealing_range = None
    external_range_high = str(dealing_range.range_high) if dealing_range else protected_high
    external_range_low = str(dealing_range.range_low) if dealing_range else protected_low
    depth_status = _depth_status(timeframe, snapshot)
    evidence = {
        "raw_current_direction": structure_state.get("current_direction"),
        "confirmed_break_count": len(breaks),
        "last_strong_break_id": None if last_strong_break is None else last_strong_break.get("object_id"),
        "last_non_flip_break_id": None if last_opposite_non_flip is None else last_opposite_non_flip.get("object_id"),
        "latest_external_break_confirmed_at": None if latest_external_break is None else latest_external_break.get("confirmed_at"),
        "latest_internal_break_confirmed_at": None if latest_internal_break is None else latest_internal_break.get("confirmed_at"),
        "last_break_quality": None if last_profile is None else last_profile.to_dict(),
        "parent_timeframe": None if not parent_context else parent_context.get("timeframe"),
        "parent_external_bias": parent_bias,
        "subordinated_to_parent": bool(parent_bias) and last_opposite_non_flip is not None,
        "house_rule": "external bias flips only on strong body-close displacement beyond the parent's protected level",
    }
    return StructureHierarchy(
        timeframe=timeframe,
        external_bias=external_bias,
        external_range_high=external_range_high,
        external_range_low=external_range_low,
        protected_high=protected_high,
        protected_low=protected_low,
        internal_state=internal_state,
        structure_phase=phase,
        bias_can_flip=bool(last_profile and last_profile.valid_for_bias_flip),
        latest_external_break_id=None if latest_external_break is None else latest_external_break.get("object_id"),
        latest_internal_break_id=None if latest_internal_break is None else latest_internal_break.get("object_id"),
        depth_status=depth_status,
        evidence=evidence,
        dealing_range=dealing_range,
    )


def hierarchy_timeframe_signals(hierarchy_by_tf: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = {}
    for timeframe, hierarchy in hierarchy_by_tf.items():
        direction = str(hierarchy.get("external_bias", "neutral"))
        confidence = 0.0
        is_internal_retracement = "retracement" in str(hierarchy.get("structure_phase", ""))
        if direction in {"bullish", "bearish"}:
            quality = ((hierarchy.get("evidence") or {}).get("last_break_quality") or {}).get("break_quality")
            confidence = 0.82 if quality == "strong" else 0.70 if quality == "moderate" else 0.58
            if hierarchy.get("internal_state") not in {"none", f"{direction}_continuation"}:
                confidence -= 0.12
        signals[timeframe] = {
            "direction": direction,
            "confidence": max(confidence, 0.0),
            "is_internal_retracement": is_internal_retracement,
        }
    return signals


def _confirmed_breaks(raw_breaks: list[Any]) -> list[Mapping[str, Any]]:
    confirmed = []
    for brk in raw_breaks:
        payload = brk if isinstance(brk, Mapping) else brk.model_dump(mode="json")
        if payload.get("confirmed_at") and not ((payload.get("evidence") or {}).get("is_unconfirmed_probe")):
            confirmed.append(payload)
    return sorted(confirmed, key=lambda item: str(item.get("confirmed_at") or item.get("candidate_at")))


def _direction(brk: Mapping[str, Any]) -> str:
    return str(brk.get("direction", "neutral")).lower()


def _break_scope(brk: Mapping[str, Any]) -> str:
    evidence = brk.get("evidence") or {}
    scope = str(brk.get("structure_scope") or evidence.get("structure_scope") or "")
    if scope in {"external", "internal"}:
        return scope
    return "internal" if evidence.get("is_internal") else "external"


def _parent_levels(parent_context: Mapping[str, Any] | None) -> tuple[str | None, Decimal | None, Decimal | None]:
    if not parent_context:
        return None, None, None
    bias = str(parent_context.get("external_bias", "neutral"))
    bias = bias if bias in {"bullish", "bearish"} else None
    ceiling_raw = parent_context.get("protected_high") or parent_context.get("external_range_high")
    floor_raw = parent_context.get("protected_low") or parent_context.get("external_range_low")
    ceiling = Decimal(str(ceiling_raw)) if ceiling_raw is not None else None
    floor = Decimal(str(floor_raw)) if floor_raw is not None else None
    return bias, ceiling, floor


def _break_close(brk: Mapping[str, Any], direction: str) -> Decimal | None:
    """Reconstruct the break candle's body close from the stored penetration evidence.

    ``body_close_penetration`` is signed relative to the broken level: for a bullish break
    it is ``close - broken_price``; for a bearish break ``broken_price - close``.
    """
    evidence = brk.get("evidence") or {}
    broken = evidence.get("broken_price")
    penetration = evidence.get("body_close_penetration")
    if broken is not None and penetration is not None:
        broken_d = Decimal(str(broken))
        pen_d = Decimal(str(penetration))
        return broken_d + pen_d if direction == "bullish" else broken_d - pen_d
    fallback = brk.get("price_high") if direction == "bullish" else brk.get("price_low")
    return Decimal(str(fallback)) if fallback is not None else None


def _breaks_parent_protection(
    brk: Mapping[str, Any],
    direction: str,
    parent_ceiling: Decimal | None,
    parent_floor: Decimal | None,
    parent_context: Mapping[str, Any] | None,
) -> bool:
    """A child may flip against its parent leg only by a confirmed body close beyond the
    parent's protected level. With no parent leg (top timeframe or neutral parent) the child
    is unconstrained, preserving the historical per-timeframe behaviour."""
    if not parent_context:
        return True
    parent_bias = str(parent_context.get("external_bias", "neutral"))
    if parent_bias not in {"bullish", "bearish"}:
        return True
    close = _break_close(brk, direction)
    if direction == "bullish":
        return parent_ceiling is None or (close is not None and close > parent_ceiling)
    if direction == "bearish":
        return parent_floor is None or (close is not None and close < parent_floor)
    return True


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _internal_state(external_bias: str, opposite_break: Mapping[str, Any] | None) -> str:
    if opposite_break is None:
        return "none" if external_bias == "neutral" else f"{external_bias}_continuation"
    direction = _direction(opposite_break)
    if external_bias == "bearish" and direction == "bullish":
        return "bullish_retracement"
    if external_bias == "bullish" and direction == "bearish":
        return "bearish_retracement"
    return f"{direction}_internal_shift"


def _structure_phase(external_bias: str, internal_state: str) -> str:
    if external_bias == "bearish" and internal_state == "bullish_retracement":
        return "retracement_inside_bearish_external_range"
    if external_bias == "bullish" and internal_state == "bearish_retracement":
        return "pullback_inside_bullish_external_range"
    if external_bias in {"bullish", "bearish"}:
        return f"{external_bias}_external_continuation"
    return "unclassified"


def _protected_prices(snapshot: Mapping[str, Any], structure_state: Mapping[str, Any]) -> tuple[str | None, str | None]:
    swings = []
    for group in (snapshot.get("swings", {}) or {}).values():
        swings.extend(group or [])
    by_id = {item.get("object_id"): item for item in swings}
    high = by_id.get(structure_state.get("last_confirmed_external_high") or structure_state.get("protected_high_id"))
    low = by_id.get(structure_state.get("last_confirmed_external_low") or structure_state.get("protected_low_id"))
    return (
        None if high is None else str(high.get("price_high")),
        None if low is None else str(low.get("price_low")),
    )


def _price_from_snapshot(snapshot: Mapping[str, Any]) -> str | None:
    for brk in reversed(snapshot.get("structure_breaks", []) or []):
        if brk.get("price_low") is not None and brk.get("price_high") is not None:
            return str((Decimal(str(brk["price_low"])) + Decimal(str(brk["price_high"]))) / Decimal("2"))
    return None


def _depth_status(timeframe: str, snapshot: Mapping[str, Any]) -> str:
    count = int(snapshot.get("candle_count") or snapshot.get("visible_candle_count") or 0)
    minimum = MIN_RESEARCH_DEPTH.get(timeframe)
    if not minimum or count == 0:
        return "depth_not_reported"
    return "sufficient_research_depth" if count >= minimum else f"shallow_context:{count}/{minimum}"
