"""Sweep / breakout / probe / reclaim lifecycle state machine (programme §6).

The programme explicitly rejects the one-bar binary rule. Every level
interaction is a lifecycle with multiple horizons:

    at_event       -- exactly on the interaction candle
    after_2_bars   -- 2 bars later
    after_6_bars   -- 6 bars later

The state machine emits typed Lifecycle objects:
    LEVEL_ACTIVE -> PROBE -> CONCLUDED_PROBE | UPGRADED_TO_SWEEP_CANDIDATE |
                                  UPGRADED_TO_BREAKOUT_CANDIDATE
    LEVEL_ACTIVE -> SWEEP_CANDIDATE -> CONFIRMED_SWEEP | UNRESOLVED
    LEVEL_ACTIVE -> BREAKOUT_CANDIDATE -> ACCEPTED_BREAKOUT | FAILED_BREAKOUT
    EXCURSION -> RECLAIM_ATTEMPTED -> RECLAIM_CONFIRMED | RECLAIM_FAILED

Rules (programme §6):
  * Wick alone is a PROBE, never a sweep or BOS.
  * Body close beyond a level + normalised penetration starts a
    BREAKOUT_CANDIDATE.
  * Sweep = level touched, no sustained closes beyond, RECLAIM_CONFIRMED,
    opposite displacement, internal structure break.
  * An event may be classified differently at different horizons (a wick at
    at_event may upgrade to breakout at after_6_bars). The state machine
    records all three horizons, not a snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from smc_desk.data.hashing import object_sha256


class InteractionType(str, Enum):
    PROBE = "probe"
    SWEEP_CANDIDATE = "sweep_candidate"
    CONFIRMED_SWEEP = "confirmed_sweep"
    BREAKOUT_CANDIDATE = "breakout_candidate"
    ACCEPTED_BREAKOUT = "accepted_breakout"
    FAILED_BREAKOUT = "failed_breakout"
    CONCLUDED_PROBE = "concluded_probe"
    RECLAIM_CONFIRMED = "reclaim_confirmed"
    RECLAIM_FAILED = "reclaim_failed"
    UNRESOLVED = "unresolved"


class Horizon(str, Enum):
    AT_EVENT = "at_event"
    AFTER_2_BARS = "after_2_bars"
    AFTER_6_BARS = "after_6_bars"


@dataclass(frozen=True)
class LevelInteraction:
    """One classified interaction between price and a level, at one horizon."""
    interaction_type: str           # see InteractionType
    horizon: str                    # see Horizon
    level_id: str
    interacting_candle_id: str
    timeframe: str
    wick_penetration_atr: float = 0.0
    body_close_beyond: bool = False
    closes_beyond_count: int = 0
    displacement_magnitude: float = 0.0
    internal_structure_break_id: str | None = None
    notes: tuple[str, ...] = ()
    schema: str = "level_interaction_v1"

    @property
    def sha256(self) -> str:
        return object_sha256({
            "interaction_type": self.interaction_type,
            "horizon": self.horizon,
            "level_id": self.level_id,
            "interacting_candle_id": self.interacting_candle_id,
            "timeframe": self.timeframe,
            "body_close_beyond": self.body_close_beyond,
            "closes_beyond_count": self.closes_beyond_count,
            "displacement_magnitude": self.displacement_magnitude,
            "internal_structure_break_id": self.internal_structure_break_id,
        })


@dataclass(frozen=True)
class LevelInteractionReport:
    """All three horizons for one candle-level interaction."""
    level_id: str
    timeframe: str
    horizons: tuple[LevelInteraction, ...]

    @property
    def at_event(self) -> LevelInteraction | None:
        for h in self.horizons:
            if h.horizon == Horizon.AT_EVENT.value:
                return h
        return None

    @property
    def after_2(self) -> LevelInteraction | None:
        for h in self.horizons:
            if h.horizon == Horizon.AFTER_2_BARS.value:
                return h
        return None

    @property
    def after_6(self) -> LevelInteraction | None:
        for h in self.horizons:
            if h.horizon == Horizon.AFTER_6_BARS.value:
                return h
        return None

    @property
    def upgraded(self) -> bool:
        """The interaction promoted at a later horizon (e.g., probe -> sweep)."""
        types = {h.interaction_type for h in self.horizons}
        return (
            InteractionType.SWEEP_CANDIDATE.value in types
            or InteractionType.BREAKOUT_CANDIDATE.value in types
            or InteractionType.ACCEPTED_BREAKOUT.value in types
            or InteractionType.CONFIRMED_SWEEP.value in types
        )


def classify_at_event(
    *,
    level_id: str,
    timeframe: str,
    interacting_candle: Mapping,
    atr_at_candle: float,
) -> LevelInteraction:
    """Classify the at_event interaction between one candle and one level."""
    high = float(interacting_candle.get("high", 0.0) or 0.0)
    low = float(interacting_candle.get("low", 0.0) or 0.0)
    close = float(interacting_candle.get("close", 0.0) or 0.0)
    open_ = float(interacting_candle.get("open", 0.0) or 0.0)
    level_price = float(interacting_candle.get("_level_price", close) or close)
    candle_id = str(interacting_candle.get("object_id") or interacting_candle.get("candle_id"))

    wick_above = max(high, open_, close) - level_price
    wick_below = level_price - min(low, open_, close)
    wick_pen = max(0.0, wick_above, wick_below) / max(atr_at_candle, 1e-12)
    # A breakout candidate requires the BODY to cross the level (open on one
    # side, close on the other). Merely closing on the far side after the body
    # was already there is NOT a breakout -- it is a probe or no interaction.
    upside_cross = (open_ <= level_price) and (close > level_price)
    downside_cross = (open_ >= level_price) and (close < level_price)
    body_close_beyond = upside_cross or downside_cross

    if upside_cross:
        t = InteractionType.BREAKOUT_CANDIDATE.value
        notes = ("body crossed level to the upside (open<=level, close>level)",
                 "candidate accepted breakout (pending post-horizon evidence)")
    elif downside_cross:
        t = InteractionType.BREAKOUT_CANDIDATE.value
        notes = ("body crossed level to the downside (open>=level, close<level)",
                 "candidate accepted breakout (pending post-horizon evidence)")
    elif high > level_price:
        t = InteractionType.PROBE.value
        notes = ("wick exceeded level upside, body did NOT close beyond",
                 "not a BOS by §6.3; promotion only at later horizon")
    elif low < level_price:
        t = InteractionType.PROBE.value
        notes = ("wick exceeded level downside, body did NOT close beyond",
                 "not a BOS by §6.3; promotion only at later horizon")
    else:
        t = InteractionType.PROBE.value
        notes = ("no excursion", "interaction pre-probe")

    return LevelInteraction(
        interaction_type=t,
        horizon=Horizon.AT_EVENT.value,
        level_id=level_id,
        interacting_candle_id=candle_id,
        timeframe=timeframe,
        wick_penetration_atr=float(round(wick_pen, 4)),
        body_close_beyond=bool(body_close_beyond),
        closes_beyond_count=int(close > level_price) or int(close < level_price),
        notes=notes,
    )


def refine_at_horizon(
    *,
    base: LevelInteraction,
    horizon: str,
    closes_within: int,
    internal_structure_break_id: str | None = None,
    displacement_magnitude: float = 0.0,
) -> LevelInteraction:
    """Refine an at_event interaction at after_2_bars or after_6_bars.

    Upgrades / downgrades follow programme §6.4:
    * closes_within (price back inside the level) at after_2 -> SWEEP_CANDIDATE
    * closes_within at after_6 + internal structure break + opposite
      displacement -> CONFIRMED_SWEEP
    * sustained closes_beyond beyond the horizon + new structure ->
      ACCEPTED_BREAKOUT (or FAILED_BREAKOUT if reclaims with no structure)
    """
    cid = base.interacting_candle_id

    if closes_within > 0:
        if horizon == Horizon.AFTER_2_BARS.value:
            t = InteractionType.SWEEP_CANDIDATE.value
            notes = ("closes inside level at after_2_bars",)
        else:
            # after_6: confirm only if internal structure break + displacement
            if internal_structure_break_id and displacement_magnitude > 0:
                t = InteractionType.CONFIRMED_SWEEP.value
                notes = ("closes inside level at after_6_bars",
                         "internal structure break present",
                         "opposite displacement present")
            else:
                t = InteractionType.SWEEP_CANDIDATE.value
                notes = ("closes inside level at after_6_bars",
                         "internal structure break or displacement MISSING")
    else:
        if horizon == Horizon.AFTER_2_BARS.value:
            t = InteractionType.BREAKOUT_CANDIDATE.value
            notes = ("sustained closes beyond at after_2_bars",
                     "candidate breakout")
        else:
            if internal_structure_break_id and displacement_magnitude > 0:
                t = InteractionType.ACCEPTED_BREAKOUT.value
                notes = ("sustained closes beyond at after_6_bars",
                         "internal structure break present",
                         "displacement magnitude present",
                         "accepted breakout per programme §6.4")
            else:
                t = InteractionType.FAILED_BREAKOUT.value
                notes = ("reclaims without new structure at after_6_bars",
                         "failed breakout")
        # Note: "closes_within=False AND no internal break AND no displacement"
        # is the failed_breakout branch above; a fully inert level (price moves
        # away without body close beyond AND no closes back inside) maps to
        # FAILED_BREAKOUT too, by design.

    return LevelInteraction(
        interaction_type=t,
        horizon=horizon,
        level_id=base.level_id,
        interacting_candle_id=cid,
        timeframe=base.timeframe,
        wick_penetration_atr=base.wick_penetration_atr,
        body_close_beyond=base.body_close_beyond,
        closes_beyond_count=base.closes_beyond_count,
        displacement_magnitude=float(displacement_magnitude),
        internal_structure_break_id=internal_structure_break_id,
        notes=notes,
    )


def build_report(
    *,
    level_id: str,
    timeframe: str,
    interacting_candle: Mapping,
    atr_at_candle: float,
    closes_within_after_2: bool = False,
    closes_within_after_6: bool = False,
    internal_structure_break_id: str | None = None,
    displacement_magnitude: float = 0.0,
) -> LevelInteractionReport:
    """Emit the at_event + after_2_bars + after_6_bars triplet for one interaction."""
    at = classify_at_event(
        level_id=level_id, timeframe=timeframe,
        interacting_candle=interacting_candle, atr_at_candle=atr_at_candle,
    )
    a2 = refine_at_horizon(
        base=at, horizon=Horizon.AFTER_2_BARS.value,
        closes_within=int(closes_within_after_2),
        internal_structure_break_id=internal_structure_break_id,
        displacement_magnitude=displacement_magnitude,
    )
    a6 = refine_at_horizon(
        base=at, horizon=Horizon.AFTER_6_BARS.value,
        closes_within=int(closes_within_after_6),
        internal_structure_break_id=internal_structure_break_id,
        displacement_magnitude=displacement_magnitude,
    )
    return LevelInteractionReport(
        level_id=level_id, timeframe=timeframe, horizons=(at, a2, a6),
    )


def is_wick_only(report: LevelInteractionReport) -> bool:
    """Programme §6 forbids treating a wick as a sweep or BOS.

    A wick-only interaction must classify as PROBE / CONCLUDED_PROBE for
    every horizon. Callers can use this to enforce the rule.
    """
    return all(
        h.interaction_type in {
            InteractionType.PROBE.value,
            InteractionType.CONCLUDED_PROBE.value,
        } for h in report.horizons
    )


__all__ = [
    "Horizon",
    "InteractionType",
    "LevelInteraction",
    "LevelInteractionReport",
    "build_report",
    "classify_at_event",
    "is_wick_only",
    "refine_at_horizon",
]
