"""What happened last time a zone like this one appeared.

A trader's confidence does not come from a rule. It comes from having seen the
same configuration a few hundred times and remembering how it usually resolved.
That is the thing this repository has been missing, and no amount of additional
gating produces it -- gates decide whether to *allow* a trade, and the question
here is which zone is *worth* one.

So this module compresses screen time. It walks stored history, records every
order block the detector finds together with the features that were knowable
when it formed, and then records what price actually did about it. A live zone
is answered by retrieving its nearest historical analogues and reporting their
empirical outcomes -- with counts, not a fitted probability.

Three outcomes, and the third is the one naive analyses drop:

``REJECTED``
    Price returned to the zone and left in the expected direction, reaching the
    target before invalidating the zone.
``BROKE``
    Price returned and closed through the zone instead.
``NEVER_RETURNED``
    Price never came back within the horizon. No trade existed.

Dropping ``NEVER_RETURNED`` is how a 55% zone becomes a "90% setup" on a slide.
It is the majority case for most zones and it is counted here.

The features are chosen from what traders and the support/resistance literature
actually weigh -- how the level was *formed*, whether liquidity was taken before
it, whether it left an imbalance behind -- rather than from what happens to be
easy to compute. Two of them are things this system already detects and has
never used to rank anything.

Authority: descriptive. A retrieved distribution is a statement about the past.
It is not a prediction, it grants no signal authority, and its sample size and
recency are reported so a reader can discount it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

REJECTED = "REJECTED"
BROKE = "BROKE"
NEVER_RETURNED = "NEVER_RETURNED"
UNRESOLVED = "UNRESOLVED"

# How long a zone is given to be revisited before it is called stale. Beyond
# this the market has usually moved on and the analogue is a different regime.
DEFAULT_RETURN_WINDOW = 200
# Once price is in the zone, how long the trade has to work.
DEFAULT_RESOLVE_WINDOW = 100
# Invalidation buffer beyond the zone edge, in multiples of the zone height.
DEFAULT_INVALIDATION_BUFFER = 0.25


@dataclass(frozen=True)
class PoiCase:
    """One historical zone, its formation features, and what followed."""

    case_id: str
    symbol: str
    timeframe: str
    direction: str
    formed_index: int
    price_low: float
    price_high: float
    features: dict[str, float]
    outcome: str = UNRESOLVED
    bars_to_return: int | None = None
    r_achieved: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "symbol": self.symbol, "timeframe": self.timeframe,
            "direction": self.direction, "formed_index": self.formed_index,
            "price_low": self.price_low, "price_high": self.price_high,
            "features": self.features, "outcome": self.outcome,
            "bars_to_return": self.bars_to_return,
            "r_achieved": None if self.r_achieved is None else round(self.r_achieved, 4),
        }


# Feature names, and the scale each is normalised by when measuring similarity.
# Binary features are already 0/1; continuous ones are divided by a typical
# spread so no single dimension dominates the distance.
FEATURE_SCALES: dict[str, float] = {
    "caused_structure_break": 1.0,
    "is_external": 1.0,
    "displacement_atr": 2.0,
    "zone_height_atr": 2.0,
    "location_in_range": 1.0,
    "htf_aligned": 1.0,
    # Was the opposite side's liquidity taken shortly before this zone formed?
    # A zone built on the back of a sweep has fuel behind it. The system detects
    # sweeps and inducements and has never used either to rank a POI.
    "swept_before": 1.0,
    # Did the departure leave an unfilled gap? Inefficiency left behind is one
    # of the few things that distinguishes a zone price *ran* from one it drifted
    # out of, and it is likewise detected and unused.
    "left_imbalance": 1.0,
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def featurize(
    poi: Mapping[str, Any],
    *,
    atr: float,
    range_low: float,
    range_high: float,
    htf_bias: str | None = None,
    swept_before: bool = False,
    left_imbalance: bool = False,
) -> dict[str, float]:
    """Feature vector as of formation. Nothing here may look forward."""
    low, high = sorted((_f(poi.get("price_low")), _f(poi.get("price_high"))))
    direction = str(poi.get("direction") or "").lower()
    evidence = poi.get("evidence") if isinstance(poi.get("evidence"), Mapping) else {}
    span = max(range_high - range_low, 1e-9)
    atr = max(atr, 1e-9)
    scope = str(
        (poi.get("metadata") or {}).get("linked_break_scope")
        or evidence.get("structure_scope") or "internal"
    ).lower()
    return {
        "caused_structure_break": 1.0 if evidence.get("caused_structure_break") else 0.0,
        "is_external": 1.0 if scope == "external" else 0.0,
        "displacement_atr": _f(evidence.get("displacement_atr")),
        "zone_height_atr": (high - low) / atr,
        "location_in_range": float(np.clip(((low + high) / 2.0 - range_low) / span, 0.0, 1.0)),
        "htf_aligned": 1.0 if (htf_bias and htf_bias.lower() == direction) else 0.0,
        "swept_before": 1.0 if swept_before else 0.0,
        "left_imbalance": 1.0 if left_imbalance else 0.0,
    }


def resolve_outcome(
    candles: pd.DataFrame,
    *,
    formed_index: int,
    direction: str,
    price_low: float,
    price_high: float,
    atr: float,
    target: float | None = None,
    return_window: int = DEFAULT_RETURN_WINDOW,
    resolve_window: int = DEFAULT_RESOLVE_WINDOW,
    invalidation_buffer: float = DEFAULT_INVALIDATION_BUFFER,
    target_r: float = 2.0,
) -> tuple[str, int | None, float | None]:
    """Did price come back, and what happened when it did?

    Returns ``(outcome, bars_to_return, r_achieved)``. The search begins strictly
    after the formation bar: a zone cannot be revisited by the candle that
    created it.
    """
    highs = candles["high"].astype(float).to_numpy()
    lows = candles["low"].astype(float).to_numpy()
    closes = candles["close"].astype(float).to_numpy()
    total = len(candles)
    low, high = min(price_low, price_high), max(price_low, price_high)
    height = max(high - low, 1e-9)
    bearish = direction == "bearish"

    entry = high if bearish else low
    # The stop is floored at half an ATR. Scaling it purely by zone height gave
    # a thin order block an absurdly tight stop, and since the target was a
    # multiple of that same risk, the objective landed half a zone-height away
    # -- inside normal noise. That version reported 83% of all zones "rejecting"
    # on live BTCUSDT, which is the shape a broken measurement makes.
    buffer = max(height * invalidation_buffer, max(atr, 1e-9) * 0.5)
    stop = (high + buffer) if bearish else (low - buffer)
    risk = abs(stop - entry)
    if risk <= 0:
        return UNRESOLVED, None, None

    # Phase 1: does price return to the zone at all?
    touch = None
    end_of_search = min(total, formed_index + 1 + return_window)
    for index in range(formed_index + 1, end_of_search):
        if lows[index] <= high and highs[index] >= low:
            touch = index
            break
    if touch is None:
        return (NEVER_RETURNED, None, None) if end_of_search < total else (UNRESOLVED, None, None)

    # Phase 2: from the touch, does it work or fail?
    if target is None:
        # No named draw: a fixed R objective, measured against the ATR-floored
        # risk above, so the target is a real move rather than a fraction of
        # the zone that produced it.
        target = entry - target_r * risk if bearish else entry + target_r * risk

    resolve_end = min(total, touch + resolve_window)
    if touch + 1 >= resolve_end:
        return UNRESOLVED, touch - formed_index, None
    for index in range(touch, resolve_end):
        invalidated = closes[index] > stop if bearish else closes[index] < stop
        reached = lows[index] <= target if bearish else highs[index] >= target
        if invalidated and reached:
            # Ambiguous bar: intrabar order is unknowable, so credit neither.
            return BROKE, touch - formed_index, None
        if invalidated:
            return BROKE, touch - formed_index, -1.0
        if reached:
            reward = abs(entry - target)
            return REJECTED, touch - formed_index, reward / risk
    return UNRESOLVED, touch - formed_index, None


def similarity_distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Scaled Euclidean distance over the shared feature space."""
    total = 0.0
    for name, scale in FEATURE_SCALES.items():
        delta = (_f(a.get(name)) - _f(b.get(name))) / max(scale, 1e-9)
        total += delta * delta
    return float(np.sqrt(total))


@dataclass(frozen=True)
class AnalogueReport:
    """The empirical answer, with everything needed to distrust it."""

    matched: int = 0
    rejected: int = 0
    broke: int = 0
    never_returned: int = 0
    median_r: float | None = None
    median_bars_to_return: float | None = None
    mean_distance: float | None = None
    neighbours: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def traded(self) -> int:
        return self.rejected + self.broke

    @property
    def rejection_rate(self) -> float | None:
        """Of the times price actually came back, how often did the zone hold?"""
        return (self.rejected / self.traded) if self.traded else None

    @property
    def return_rate(self) -> float | None:
        """How often price came back at all. The base rate a slide would hide."""
        total = self.traded + self.never_returned
        return (self.traded / total) if total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "poi_analogue_report_v1",
            "matched": self.matched,
            "rejected": self.rejected,
            "broke": self.broke,
            "never_returned": self.never_returned,
            "traded": self.traded,
            "rejection_rate": None if self.rejection_rate is None else round(self.rejection_rate, 4),
            "return_rate": None if self.return_rate is None else round(self.return_rate, 4),
            "median_r": self.median_r,
            "median_bars_to_return": self.median_bars_to_return,
            "mean_distance": self.mean_distance,
            "neighbours": list(self.neighbours),
            "notes": list(self.notes),
            "authority": "descriptive_historical_analogue_not_a_prediction",
            "signal_allowed": False,
        }


def retrieve_analogues(
    features: Mapping[str, float],
    library: Sequence[PoiCase],
    *,
    direction: str | None = None,
    k: int = 40,
    max_distance: float | None = None,
    minimum_matched: int = 20,
) -> AnalogueReport:
    """Answer a live zone from the closest historical ones.

    Refuses rather than guesses when the neighbourhood is thin: a distribution
    over five cases is an anecdote, and reporting it as a rate would manufacture
    exactly the false confidence this module exists to replace.
    """
    pool = [c for c in library if c.outcome != UNRESOLVED]
    if direction:
        pool = [c for c in pool if c.direction == direction]
    if not pool:
        return AnalogueReport(notes=("no resolved cases for this direction",))

    scored = sorted(((similarity_distance(features, c.features), c) for c in pool), key=lambda p: p[0])
    if max_distance is not None:
        scored = [pair for pair in scored if pair[0] <= max_distance]
    chosen = scored[:k]
    if len(chosen) < minimum_matched:
        return AnalogueReport(
            matched=len(chosen),
            notes=(
                f"only {len(chosen)} comparable cases found; "
                f"below the floor of {minimum_matched}, so no rate is reported",
            ),
        )

    rejected = [c for _, c in chosen if c.outcome == REJECTED]
    broke = [c for _, c in chosen if c.outcome == BROKE]
    never = [c for _, c in chosen if c.outcome == NEVER_RETURNED]
    rs = [c.r_achieved for c in rejected if c.r_achieved is not None]
    returns = [c.bars_to_return for _, c in chosen if c.bars_to_return is not None]

    return AnalogueReport(
        matched=len(chosen),
        rejected=len(rejected),
        broke=len(broke),
        never_returned=len(never),
        median_r=round(float(np.median(rs)), 4) if rs else None,
        median_bars_to_return=round(float(np.median(returns)), 1) if returns else None,
        mean_distance=round(float(np.mean([d for d, _ in chosen])), 4),
        neighbours=tuple(c.case_id for _, c in chosen[:5]),
    )


__all__ = [
    "BROKE",
    "DEFAULT_INVALIDATION_BUFFER",
    "DEFAULT_RESOLVE_WINDOW",
    "DEFAULT_RETURN_WINDOW",
    "FEATURE_SCALES",
    "NEVER_RETURNED",
    "REJECTED",
    "UNRESOLVED",
    "AnalogueReport",
    "PoiCase",
    "featurize",
    "resolve_outcome",
    "retrieve_analogues",
    "similarity_distance",
]
