"""Volatility-adaptive directional-change candidate generator.

Per programme §4.2B. A reversal exceeding a threshold *relative to ATR (or
realized volatility)* creates a directional-change candidate; the overshoot
becomes part of the same market leg.

The generator tracks the running pivot (last confirmed high or low). When the
opposite move from that pivot exceeds the threshold, the pivot becomes a
candidate and the threshold-crossing direction sets the next running pivot.

Directional-change research argues for event-based segmentation (programme
§2.1). This is the candidate source that adapts to volatility regime: in a
high-ATR environment, fewer pivots survive; in a low-ATR environment, more.

Deterministic, causal (each decision uses only closed candles up to the bar).
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from smc_desk.perception.candidates.indicators import atr, iso_from_index
from smc_desk.perception.candidates.schema import (
    GENERATOR_DIRECTIONAL_CHANGE,
    SwingCandidate,
    candidate_id,
)

DEFAULT_THRESHOLDS = (0.5, 0.75, 1.0, 1.5, 2.0)


def detect(
    df: pd.DataFrame,
    *,
    timeframe: str,
    thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
    atr_period: int = 14,
) -> list[SwingCandidate]:
    """Emit one directional-change candidate per confirmed pivot per threshold.

    The pivot (not the cross-bar) is the candidate. The cross-bar's ATR is
    recorded as volatility_normalized_move so the ranking layer can weight
    by regime.
    """
    if len(df) < atr_period + 2:
        return []
    atr_arr = atr(df, period=atr_period)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    n = len(df)
    out: list[SwingCandidate] = []

    thresholds = sorted(set(round(float(t), 4) for t in thresholds))

    for thr in thresholds:
        # direction +1 = tracking highs (running low); -1 = tracking lows (running high)
        direction = 1
        pivot_i = 0
        pivot_price = highs[0]
        pivot_type = "high"

        for i in range(1, n):
            if direction == 1:
                # extend running high
                if highs[i] > pivot_price:
                    pivot_i = i
                    pivot_price = highs[i]
                # check down-cross from the running high
                move = pivot_price - lows[i]
                if move >= thr * max(atr_arr[i], 1e-12):
                    out.append(_make(df, timeframe, pivot_i, pivot_price, pivot_type, thr, move, atr_arr[i]))
                    # switch to tracking lows starting from the cross bar
                    direction = -1
                    pivot_i = i
                    pivot_price = lows[i]
                    pivot_type = "low"
            else:  # direction == -1
                # extend running low
                if lows[i] < pivot_price:
                    pivot_i = i
                    pivot_price = lows[i]
                # check up-cross from the running low
                move = highs[i] - pivot_price
                if move >= thr * max(atr_arr[i], 1e-12):
                    out.append(_make(df, timeframe, pivot_i, pivot_price, pivot_type, thr, move, atr_arr[i]))
                    direction = 1
                    pivot_i = i
                    pivot_price = highs[i]
                    pivot_type = "high"
    return out


def _make(
    df: pd.DataFrame,
    timeframe: str,
    pivot_i: int,
    pivot_price: float,
    pivot_type: str,
    threshold: float,
    move_price: float,
    atr_at_i: float,
) -> SwingCandidate:
    return SwingCandidate(
        candidate_id=candidate_id(GENERATOR_DIRECTIONAL_CHANGE, timeframe, iso_from_index(df, pivot_i), pivot_type),
        timeframe=timeframe,
        pivot_type=pivot_type,
        pivot_time=iso_from_index(df, pivot_i),
        pivot_price=float(pivot_price),
        generator_source=GENERATOR_DIRECTIONAL_CHANGE,
        scale="atlas",
        volatility_normalized_move=float(round(move_price / max(atr_at_i, 1e-12), 4)),
        bars_left=None,
        bars_right=None,
        survival_bars=0,
        lifecycle="CANDIDATE",
    )


__all__ = ["detect", "DEFAULT_THRESHOLDS"]


# Re-export df type-hint helper for modules that import this
from pandas import DataFrame  # noqa: E402
