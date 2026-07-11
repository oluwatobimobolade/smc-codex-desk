"""Fractal candidate adapter.

Per programme §4.2A, the fixed-scale fractal detector is one of five
candidate generators. It is NOT authoritative on its own. The atlas fuses
its output with the four other generators (directional change, prominence,
change points, displacement origins) and the reconciler decides what matters.

This adapter wraps ``smc_desk.perception.swings.SwingDetector`` so its output
shares the ``SwingCandidate`` schema with the four new generators.

We also offer a lightweight DataFrame fractal that does not depend on the
existing swing detector so the atlas is portable (no ontology import cycle,
no Candle coupling) for tests and synthetic cases.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from smc_desk.perception.candidates.indicators import atr, iso_from_index
from smc_desk.perception.candidates.schema import (
    GENERATOR_FRACTAL,
    SwingCandidate,
    candidate_id,
)


def detect_dataframe(
    df: pd.DataFrame,
    *,
    timeframe: str,
    bars_left: int = 5,
    bars_right: int = 5,
    scale: str = "internal",
) -> list[SwingCandidate]:
    """DataFrame-native fractal detection for portability.

    Mirrors the geometric core of ``SwingDetector`` (a pivot higher than
    both adjacent windows) but produces ``SwingCandidate`` records.
    """
    n = len(df)
    if n < bars_left + bars_right + 1:
        return []
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    atr_arr = atr(df)
    out: list[SwingCandidate] = []
    for i in range(bars_left, n - bars_right):
        left_high = highs[i - bars_left : i]
        right_high = highs[i + 1 : i + bars_right + 1]
        if (highs[i] > left_high).all() and (highs[i] > right_high).all():
            out.append(_make(df, timeframe, i, float(highs[i]), "high", scale, bars_left, bars_right, atr_arr[i]))
            continue
        left_low = lows[i - bars_left : i]
        right_low = lows[i + 1 : i + bars_right + 1]
        if (lows[i] < left_low).all() and (lows[i] < right_low).all():
            out.append(_make(df, timeframe, i, float(lows[i]), "low", scale, bars_left, bars_right, atr_arr[i]))
    return out


def _make(df, timeframe, i, price, pivot_type, scale, bars_left, bars_right, atr_at_i):
    return SwingCandidate(
        candidate_id=candidate_id(GENERATOR_FRACTAL, timeframe, iso_from_index(df, i), pivot_type),
        timeframe=timeframe,
        pivot_type=pivot_type,
        pivot_time=iso_from_index(df, i),
        pivot_price=float(price),
        generator_source=GENERATOR_FRACTAL,
        scale=scale,
        prominence=None,
        volatility_normalized_move=None,
        bars_left=int(bars_left),
        bars_right=int(bars_right),
        survival_bars=0,
        lifecycle="CANDIDATE",
        causal_origin_hypotheses=[
            {"generator": GENERATOR_FRACTAL, "scale": scale, "bars_left": int(bars_left), "bars_right": int(bars_right)}
        ],
    )


__all__ = ["detect_dataframe"]


from pandas import DataFrame  # noqa: E402