"""The moment price trades through a swing extreme it already knew about.

This is the event Osler measured from the Royal Bank of Scotland order book:
stop orders cluster just beyond prior extremes, and price moves unusually fast
when it reaches them. Of everything Smart Money Concepts asserts, this is the
claim with real institutional data behind it, and the repository could not test
it because it had no way to name the event.

A penetration is not a structure break, and conflating them is the main way this
gets built wrong:

* A **break** requires a body close beyond the level. It is a statement about
  structure -- the market has accepted a new state.
* A **penetration** requires only that price traded through. It is a statement
  about *orders* -- resting stops beyond the level have been filled, whether or
  not the candle closed there.

Osler's cascade is about the second. A wick through a prior high fills the stops
sitting above it just as surely as a close does, so penetration counts the wick.

Four rules keep the event honest:

**Knowable first.** A swing needs bars to its right before it is confirmed, so
price can trade through a level days before the system could have identified it.
Only interactions at or after ``confirmed_at`` count. Without this the extractor
would report the system reacting to levels it had not yet detected -- the
lookahead class of error this project exists to prevent.

**Approached from the protected side.** Price must be below a swing high, or
above a swing low, at the moment of confirmation. Price already beyond the level
cannot penetrate it.

**First touch only.** Once a level is taken the resting orders are gone. A
second visit is a different phenomenon and is not another penetration.

**Age recorded, never gated.** Resting orders presumably decay, but by how much
is exactly the kind of threshold the truth constitution lists as
``doctrine_undefined``. The bars elapsed are recorded so a consumer can model it;
nothing here filters on a number nobody has established.

Authority: descriptive. This names an event. It grants no signal, promotes no
object, and makes no claim about what happens next -- that is what the mechanism
rung is for.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

# A swing high tops a bearish turn; a swing low bottoms a bullish one.
SWING_HIGH_SIDE = "bearish"
SWING_LOW_SIDE = "bullish"


@dataclass(frozen=True)
class PenetrationEvent:
    """One first-touch of a previously confirmed swing extreme."""

    swing_object_id: str
    side: str                    # "high" or "low"
    level: float
    bar_index: int               # index of the penetrating bar
    penetrated_at: str
    confirmed_at: str
    bars_since_confirmation: int
    penetration_depth: float     # how far beyond the level, in price
    closed_beyond: bool          # whether it was also a body close (a break)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "swing_penetration_event_v1",
            "swing_object_id": self.swing_object_id,
            "side": self.side,
            "level": self.level,
            "bar_index": self.bar_index,
            "penetrated_at": self.penetrated_at,
            "confirmed_at": self.confirmed_at,
            "bars_since_confirmation": self.bars_since_confirmation,
            "penetration_depth": round(self.penetration_depth, 8),
            "closed_beyond": self.closed_beyond,
        }


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_penetration_events(
    swings: Iterable[Mapping[str, Any]],
    candles: pd.DataFrame,
    *,
    require_confirmed: bool = True,
) -> list[PenetrationEvent]:
    """Find the first knowable trade-through of each confirmed swing extreme.

    ``candles`` must carry ``timestamp``, ``high``, ``low`` and ``close``, in
    ascending time order. Timestamps are candle opens, matching the rest of the
    repository.
    """
    if candles is None or candles.empty:
        return []
    required = {"timestamp", "high", "low", "close"}
    if not required.issubset(candles.columns):
        return []

    stamps = pd.to_datetime(candles["timestamp"], utc=True)
    highs = candles["high"].astype(float).to_numpy()
    lows = candles["low"].astype(float).to_numpy()
    closes = candles["close"].astype(float).to_numpy()
    total = len(candles)

    events: list[PenetrationEvent] = []
    for swing in swings:
        if not isinstance(swing, Mapping):
            continue
        if require_confirmed and str(swing.get("confirmation_status")) != "confirmed":
            continue
        confirmed_at = swing.get("confirmed_at")
        if not confirmed_at:
            continue

        direction = str(swing.get("direction") or "").lower()
        if direction == SWING_HIGH_SIDE:
            side, level = "high", _f(swing.get("price_high"))
        elif direction == SWING_LOW_SIDE:
            side, level = "low", _f(swing.get("price_low"))
        else:
            continue
        if level is None:
            continue

        confirmation = pd.Timestamp(confirmed_at)
        if confirmation.tzinfo is None:
            confirmation = confirmation.tz_localize("UTC")
        # Search begins strictly after confirmation: the confirming bar itself
        # is part of establishing the swing, not a later interaction with it.
        start = int(stamps.searchsorted(confirmation, side="right"))
        if start >= total:
            continue

        # Approached from the protected side. Price already beyond the level at
        # confirmation has nothing left to penetrate.
        if side == "high" and highs[start - 1 if start else 0] > level and start > 0:
            if closes[start - 1] > level:
                continue
        if side == "low" and lows[start - 1 if start else 0] < level and start > 0:
            if closes[start - 1] < level:
                continue

        for index in range(start, total):
            beyond = highs[index] > level if side == "high" else lows[index] < level
            if not beyond:
                continue
            depth = (highs[index] - level) if side == "high" else (level - lows[index])
            closed_beyond = (
                closes[index] > level if side == "high" else closes[index] < level
            )
            events.append(
                PenetrationEvent(
                    swing_object_id=str(swing.get("object_id") or ""),
                    side=side,
                    level=level,
                    bar_index=index,
                    penetrated_at=str(stamps.iloc[index]),
                    confirmed_at=str(confirmation),
                    bars_since_confirmation=index - start + 1,
                    penetration_depth=depth,
                    closed_beyond=bool(closed_beyond),
                )
            )
            break  # first touch only; the resting orders are gone after it

    events.sort(key=lambda e: (e.bar_index, e.swing_object_id))
    return events


def deduplicate_by_bar(
    events: Sequence[PenetrationEvent], *, keep: str = "deepest"
) -> list[PenetrationEvent]:
    """One event per bar per side.

    A single decisive candle routinely takes several stacked swing extremes at
    once. Those are one liquidity event, not three, and counting them separately
    would inflate the sample with observations that share an outcome window --
    the dependence a block bootstrap is meant to model, smuggled in as extra n.
    """
    best: dict[tuple[int, str], PenetrationEvent] = {}
    for event in events:
        key = (event.bar_index, event.side)
        current = best.get(key)
        if current is None:
            best[key] = event
            continue
        if keep == "deepest" and event.penetration_depth > current.penetration_depth:
            best[key] = event
    return sorted(best.values(), key=lambda e: (e.bar_index, e.swing_object_id))


__all__ = [
    "SWING_HIGH_SIDE",
    "SWING_LOW_SIDE",
    "PenetrationEvent",
    "deduplicate_by_bar",
    "extract_penetration_events",
]
