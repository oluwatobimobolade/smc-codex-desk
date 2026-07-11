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
    fvg_times = {f["time"] for f in fvgs}

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
            # origin = opposing extreme before the impulse start
            origin_i = max(0, start - 1)
            if direction == "bullish":
                origin_price = float(min(lows[: start])) if start > 0 else float(lows[origin_i])
                # find the actual low in the lookback window before start
                origin_i = int(int(__import__("numpy").argmin(lows[:start]))) if start > 0 else 0
                origin_price = float(lows[origin_i])
                pivot_type = "low"
            else:
                origin_i = int(int(__import__("numpy").argmax(highs[:start]))) if start > 0 else 0
                origin_price = float(highs[origin_i])
                pivot_type = "high"
            fvg_in_run = any(iso_from_index(df, k) in fvg_times for k in range(start, i + 1))
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


__all__ = ["detect"]


from pandas import DataFrame  # noqa: E402