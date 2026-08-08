"""Active dealing-range state machine (programme §7).

An active range is the causal structural leg currently controlling location
and invalidation on a stated timeframe. It is not simply the latest high
and low.

Creation (§7.3):
    * an accepted external BOS establishes a leg;
    * an accepted reversal creates a new external leg;
    * the causal origin and terminal structural point are known.

Hierarchy (§7.4): Daily parent > 4H active > 1H child > 15m execution.
A child range cannot overwrite its parent.

Replacement triggers (§7.5): any of
    * the terminal point is extended by a new accepted external break;
    * the protected point is invalidated and an opposite structure confirmed;
    * a parent range supersedes the child;
    * the range is explicitly classified stale.

Location output (§7.6):
    {range_validity, price_location, distance_from_equilibrium,
     nested_location, confidence}.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from smc_desk.data.hashing import object_sha256


class RangeLifecycle(str, Enum):
    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    EXTENDED = "EXTENDED"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"


class RangeDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ReplacementTrigger(str, Enum):
    TERMINAL_EXTENSION = "terminal_extension"
    PROTECTED_VIOLATION = "protected_violation"
    PARENT_SUPERSESSION = "parent_supersession"
    EXPLICIT_STALE = "explicit_stale"


@dataclass(frozen=True)
class RangeObject:
    range_id: str
    owner_timeframe: str
    direction: str
    origin_id: str
    terminal_id: str
    origin_price: float
    terminal_price: float
    creating_event_id: str
    protected_point_id: str
    parent_range_id: str | None
    child_range_ids: tuple[str, ...]
    equilibrium_price: float
    premium_zone: tuple[float, float]
    discount_zone: tuple[float, float]
    lifecycle: str
    replacement_conditions: tuple[str, ...]
    invalidation_evidence_id: str | None = None
    schema: str = "active_range_object_v1"

    @property
    def midpoint(self) -> float:
        return (self.origin_price + self.terminal_price) / 2.0

    @property
    def size(self) -> float:
        return abs(self.terminal_price - self.origin_price)

    @property
    def sha256(self) -> str:
        return object_sha256({**self.__dict__, "child_range_ids": list(self.child_range_ids),
                              "replacement_conditions": list(self.replacement_conditions)})


def _mid(o: float, t: float) -> float:
    return (o + t) / 2.0


def propose_range(
    *,
    range_id: str,
    owner_timeframe: str,
    direction: str,
    origin_id: str,
    terminal_id: str,
    origin_price: float,
    terminal_price: float,
    creating_event_id: str,
    protected_point_id: str,
    parent_range_id: str | None = None,
    child_range_ids: Sequence[str] = (),
) -> RangeObject:
    """Propose a new active-range object per §7.2. Lifecycle starts PROPOSED."""
    if direction not in {RangeDirection.BULLISH.value, RangeDirection.BEARISH.value}:
        raise ValueError(f"Unsupported range direction: {direction!r}")
    if not all((range_id, owner_timeframe, origin_id, terminal_id, creating_event_id, protected_point_id)):
        raise ValueError("Range identity, endpoints, creating event, and protected point are required.")
    if float(origin_price) == float(terminal_price):
        raise ValueError("Active range requires distinct origin and terminal prices.")
    lo, hi = (origin_price, terminal_price) if origin_price <= terminal_price else (terminal_price, origin_price)
    equilibrium = _mid(origin_price, terminal_price)
    return RangeObject(
        range_id=range_id,
        owner_timeframe=owner_timeframe,
        direction=direction,
        origin_id=origin_id,
        terminal_id=terminal_id,
        origin_price=origin_price,
        terminal_price=terminal_price,
        creating_event_id=creating_event_id,
        protected_point_id=protected_point_id,
        parent_range_id=parent_range_id,
        child_range_ids=tuple(child_range_ids),
        equilibrium_price=equilibrium,
        premium_zone=(equilibrium, hi),
        discount_zone=(lo, equilibrium),
        lifecycle=RangeLifecycle.PROPOSED.value,
        replacement_conditions=(),
        invalidation_evidence_id=None,
    )


def activate(rng: RangeObject) -> RangeObject:
    """Promote PROPOSED -> ACTIVE once §7.3 prerequisites are met."""
    if rng.lifecycle != RangeLifecycle.PROPOSED.value:
        return rng
    return RangeObject(
        **{**rng.__dict__, "lifecycle": RangeLifecycle.ACTIVE.value},
    )


def can_replace(
    rng: RangeObject,
    *,
    terminal_extension: bool = False,
    protected_violation: bool = False,
    parent_supersession: bool = False,
    explicit_stale: bool = False,
) -> tuple[bool, list[str]]:
    """§7.5: at least one of the four replacement triggers must fire."""
    fired: list[str] = []
    if terminal_extension:
        fired.append(ReplacementTrigger.TERMINAL_EXTENSION.value)
    if protected_violation:
        fired.append(ReplacementTrigger.PROTECTED_VIOLATION.value)
    if parent_supersession:
        fired.append(ReplacementTrigger.PARENT_SUPERSESSION.value)
    if explicit_stale:
        fired.append(ReplacementTrigger.EXPLICIT_STALE.value)
    return (len(fired) > 0), fired


def replace(
    rng: RangeObject, *,
    replacement_reason: str,
    terminal_extension: bool = False,
    protected_violation: bool = False,
    parent_supersession: bool = False,
    explicit_stale: bool = False,
) -> RangeObject:
    """Transition ACTIVE -> EXTENDED / SUPERSEDED / STALE per §7.5."""
    if rng.lifecycle not in {RangeLifecycle.ACTIVE.value, RangeLifecycle.EXTENDED.value}:
        return rng
    ok, fired = can_replace(
        rng,
        terminal_extension=terminal_extension,
        protected_violation=protected_violation,
        parent_supersession=parent_supersession,
        explicit_stale=explicit_stale,
    )
    if not ok:
        return rng
    if parent_supersession:
        new_state = RangeLifecycle.SUPERSEDED.value
    elif explicit_stale:
        new_state = RangeLifecycle.STALE.value
    elif terminal_extension:
        new_state = RangeLifecycle.EXTENDED.value
    else:
        new_state = RangeLifecycle.SUPERSEDED.value
    return RangeObject(
        **{**rng.__dict__,
           "lifecycle": new_state,
           "replacement_conditions": tuple(fired),
           "invalidation_evidence_id": (rng.invalidation_evidence_id or replacement_reason)},
    )


def location_in_range(rng: RangeObject, price: float) -> dict[str, Any]:
    """§7.6 location output: range_validity, price_location, distance_from_equilibrium."""
    if rng.lifecycle not in (RangeLifecycle.ACTIVE.value, RangeLifecycle.EXTENDED.value):
        return {
            "range_validity": rng.lifecycle,
            "price_location": None,
            "distance_from_equilibrium": None,
            "nested_location": None,
            "confidence": "insufficient_context",
        }
    eq = rng.equilibrium_price
    _, top = rng.premium_zone
    bottom, _ = rng.discount_zone
    location = "premium" if price >= eq else "discount"
    return {
        "range_validity": rng.lifecycle,
        "price_location": location,
        "distance_from_equilibrium": float(price - eq),
        "nested_location": rng.owner_timeframe,
        "confidence": "probable" if rng.lifecycle == RangeLifecycle.EXTENDED.value else "confirmed",
        "top_of_range": float(top),
        "bottom_of_range": float(bottom),
    }


def link_child_range(parent: RangeObject, child: RangeObject) -> tuple[RangeObject, RangeObject]:
    """Validate and record a parent/child relation without allowing overwrite."""
    hierarchy = {"1d": 4, "4h": 3, "1h": 2, "15m": 1, "5m": 0}
    parent_rank = hierarchy.get(parent.owner_timeframe.lower())
    child_rank = hierarchy.get(child.owner_timeframe.lower())
    if parent_rank is None or child_rank is None or parent_rank <= child_rank:
        raise ValueError("Parent range must own a strictly higher timeframe than its child.")
    if child.parent_range_id not in {None, parent.range_id}:
        raise ValueError("Child range already points to a different parent.")
    updated_parent = RangeObject(**{
        **parent.__dict__,
        "child_range_ids": tuple(dict.fromkeys((*parent.child_range_ids, child.range_id))),
    })
    updated_child = RangeObject(**{**child.__dict__, "parent_range_id": parent.range_id})
    return updated_parent, updated_child


__all__ = [
    "RangeLifecycle",
    "RangeDirection",
    "ReplacementTrigger",
    "RangeObject",
    "propose_range",
    "activate",
    "can_replace",
    "replace",
    "location_in_range",
    "link_child_range",
]
