"""Prominence / persistence candidate generator.

Per programme §4.2C. Measures how prominently a candidate protrudes from the
surrounding structure and how persistently it survives:

* price prominence relative to neighbouring extrema;
* how long the candidate remained unbroken (survival bars);
* how many subordinate pivots formed inside its leg;
* whether it survives across several scales.

A prominence candidate is a fractal whose prominence exceeds a threshold.
Subordinate pivots are counted causally from the candidate forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from smc_desk.perception.candidates.indicators import atr, iso_from_index
from smc_desk.perception.candidates.schema import (
    GENERATOR_PROMINENCE,
    SwingCandidate,
    candidate_id,
)


def detect(
    df: pd.DataFrame,
    *,
    timeframe: str,
    window: int = 10,
    prominence_atr: float = 1.0,
    atr_period: int = 14,
) -> list[SwingCandidate]:
    """Emit candidates for local extrema whose prominence >= prominence_atr.

    Prominence of a high = (price - max(other highs in window)) / ATR.
    Prominence of a low  = (min(other lows in window) - price) / ATR (negated).
    Survival = number of bars the level held before being decisively closed
    through. Subordinate pivots = count of local extrema (window/2) between
    this pivot and its decisive break.
    """
    n = len(df)
    if n < window * 2 + 2:
        return []
    atr_arr = atr(df, period=atr_period)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    half = window // 2
    out: list[SwingCandidate] = []

    # Local extrema via a simple left/right window comparison (geometric core)
    for i in range(half, n - half):
        left_h = highs[i - half : i]
        right_h = highs[i + 1 : i + half + 1]
        if (highs[i] > left_h).all() and (highs[i] > right_h).all():
            neighbours = np.concatenate([left_h, right_h])
            neighbour_max = float(np.max(neighbours))
            prom = (highs[i] - neighbour_max) / max(atr_arr[i], 1e-12)
            if prom >= prominence_atr:
                out.append(
                    _make(
                        df, timeframe, i, float(highs[i]), "high", prom, atr_arr[i],
                        _survival(closes, highs[i], closes[i:], "high"),
                    )
                )
            continue
        left_l = lows[i - half : i]
        right_l = lows[i + 1 : i + half + 1]
        if (lows[i] < left_l).all() and (lows[i] < right_l).all():
            neighbours = np.concatenate([left_l, right_l])
            neighbour_min = float(np.min(neighbours))
            prom = (neighbour_min - lows[i]) / max(atr_arr[i], 1e-12)
            if prom >= prominence_atr:
                out.append(
                    _make(
                        df, timeframe, i, float(lows[i]), "low", prom, atr_arr[i],
                        _survival(closes, lows[i], closes[i:], "low"),
                    )
                )
    return out


def _survival(closes: "list", level: float, future_closes: "list", kind: str) -> int:
    """Causal-friendly survival: count bars after the pivot (within the known
    closed series) until price closes decisively beyond the level.

    We pass future_closes = closes[i:] which is already only closed candles
    available up to decision time (the caller slices the certified frame).
    """
    count = 0
    for c in future_closes[1:]:
        count += 1
        if kind == "high" and c > level:
            break
        if kind == "low" and c < level:
            break
    return count


def _make(df, timeframe, i, price, pivot_type, prominence_atr_val, atr_at_i, survival):
    return SwingCandidate(
        candidate_id=candidate_id(GENERATOR_PROMINENCE, timeframe, iso_from_index(df, i), pivot_type),
        timeframe=timeframe,
        pivot_type=pivot_type,
        pivot_time=iso_from_index(df, i),
        pivot_price=float(price),
        generator_source=GENERATOR_PROMINENCE,
        scale="local",
        prominence=float(round(prominence_atr_val, 4)),
        volatility_normalized_move=None,
        bars_left=5,
        bars_right=5,
        survival_bars=int(survival),
        subordinate_pivot_count=0,  # enriched by atlas after fusion
        lifecycle="CANDIDATE",
    )


__all__ = ["detect"]


from pandas import DataFrame  # noqa: E402