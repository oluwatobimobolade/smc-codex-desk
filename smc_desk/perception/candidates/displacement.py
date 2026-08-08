"""Displacement-linked candidate generator.

Per programme §4.2E ("Displacement-linked candidates"). Identify impulse
sequences with:

* large normalised candle bodies;
* consecutive directional closes;
* range expansion;
* FVG creation;
* rapid movement relative to recent volatility.

Trace each impulse backward to plausible origins. The origin of an impulse
becomes a candidate (a protected-point hypothesis source); the impulse
itself records the candle range and FVG list.

Deterministic and causal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from smc_desk.perception.candidates.indicators import (
    atr,
    body_ratio,
    consecutive_directional_closes,
    detect_fvgs,
    iso_from_index,
)
from smc_desk.perception.candidates.schema import (
    GENERATOR_DISPLACEMENT,
    SwingCandidate,
    candidate_id,
)


def detect(
    df: pd.DataFrame,
    *,
    timeframe: str,
    min_consecutive: int = 3,
    min_body_ratio: float = 0.6,
    min_range_atr: float = 0.8,
    atr_period: int = 14,
    origin_lookback: int = 12,
) -> list[SwingCandidate]:
    """Emit origin candidates for displacement impulses.

    An impulse is N consecutive same-direction candles with body_ratio >=
    min_body_ratio and cumulative range >= min_range_atr * ATR. The origin is
    the opposing extreme immediately before the first impulse candle.
    """
    n = len(df)
    if n < min_consecutive + 2:
        return []
    atr_arr = atr(df, period=atr_period)
    body = body_ratio(df)
    run = consecutive_directional_closes(df)
    fvgs = detect_fvgs(df, atr_arr=atr_arr)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    opens = df["open"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    timestamps = df["timestamp"].to_numpy()

    out: list[SwingCandidate] = []
    i = min_consecutive
    while i < n:
        if run[i] >= min_consecutive:
            start = i - run[i] + 1
            direction = "bullish" if closes[i] > opens[start] else "bearish"
            # verify body quality over the run
            run_bodies = body[start : i + 1]
            if (run_bodies >= min_body_ratio).mean() < 0.5:
                i += 1
                continue
            run_range = float(max(highs[start : i + 1]) - min(lows[start : i + 1]))
            if run_range < min_range_atr * max(atr_arr[i], 1e-12):
                i += 1
                continue
            origin_i, origin_price, pivot_type, cluster_start = _local_origin(
                opens=opens,
                closes=closes,
                highs=highs,
                lows=lows,
                impulse_start=start,
                direction=direction,
                lookback=origin_lookback,
            )
            fvg_in_run = any(
                f.get("confirmed_at") in {iso_from_index(df, k) for k in range(start, i + 1)}
                for f in fvgs
            )
            confirmed_at = iso_from_index(df, i)
            out.append(
                SwingCandidate(
                    candidate_id=candidate_id(
                        GENERATOR_DISPLACEMENT, timeframe, iso_from_index(df, origin_i), pivot_type
                    ),
                    timeframe=timeframe,
                    pivot_type=pivot_type,
                    pivot_time=iso_from_index(df, origin_i),
                    pivot_price=origin_price,
                    generator_source=GENERATOR_DISPLACEMENT,
                    confirmed_at=confirmed_at,
                    available_at=confirmed_at,
                    generator_sources=(GENERATOR_DISPLACEMENT,),
                    scale="external_candidate",
                    volatility_normalized_move=float(round(run_range / max(atr_arr[i], 1e-12), 4)),
                    displacement_after=True,
                    fvg_created=fvg_in_run,
                    breaks_caused=[],
                    liquidity_visibility=None,
                    lifecycle="CANDIDATE",
                    causal_origin_hypotheses=[
                        {
                            "impulse_start": iso_from_index(df, start),
                            "impulse_end": iso_from_index(df, i),
                            "origin_cluster_start": iso_from_index(df, cluster_start),
                            "origin_cluster_end": iso_from_index(df, origin_i),
                            "direction": direction,
                            "range_atr": float(round(run_range / max(atr_arr[i], 1e-12), 4)),
                            "consecutive": int(run[i]),
                            "fvg_created": fvg_in_run,
                        }
                    ],
                )
            )
            i += 1
        else:
            i += 1
    return out


def _local_origin(*, opens, closes, highs, lows, impulse_start, direction, lookback):
    """Return the local opposing candle cluster immediately before an impulse."""
    if impulse_start <= 0:
        pivot_type = "low" if direction == "bullish" else "high"
        price = float(lows[0] if pivot_type == "low" else highs[0])
        return 0, price, pivot_type, 0

    end = impulse_start - 1
    floor = max(0, impulse_start - max(int(lookback), 1))
    if direction == "bullish":
        opposing = lambda j: closes[j] < opens[j]
        pivot_type = "low"
    else:
        opposing = lambda j: closes[j] > opens[j]
        pivot_type = "high"

    cluster_end = end
    while cluster_end >= floor and not opposing(cluster_end):
        cluster_end -= 1
    if cluster_end < floor:
        cluster_end = end
    cluster_start = cluster_end
    while cluster_start - 1 >= floor and opposing(cluster_start - 1):
        cluster_start -= 1
    window = slice(cluster_start, cluster_end + 1)
    if pivot_type == "low":
        origin_i = cluster_start + int(np.argmin(lows[window]))
        price = float(lows[origin_i])
    else:
        origin_i = cluster_start + int(np.argmax(highs[window]))
        price = float(highs[origin_i])
    return origin_i, price, pivot_type, cluster_start


__all__ = ["detect"]
