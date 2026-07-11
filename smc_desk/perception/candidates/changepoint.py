"""Statistical change-point candidate generator.

Per programme §4.2D ("change-point candidates do not become BOS automatically.
They provide independent evidence that the market process changed.").

This is a deliberately simple mean-shift detector (CUSUM-style) on a single
feature at a time. It emits a candidate at the bar the shift becomes
detectable. The candidate carries the feature name and shift magnitude; the
reconciler reasons across features and pivots -- a change point is *not* a
pivot of price, it's a candidate the AI may use as independent evidence.

Deterministic, causal: the decision at bar i uses only bars 0..i.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from smc_desk.perception.candidates.indicators import (
    atr,
    body_ratio,
    candle_range_atr,
    consecutive_directional_closes,
    iso_from_index,
    realized_volatility,
)
from smc_desk.perception.candidates.schema import (
    GENERATOR_CHANGEPOINT,
    SwingCandidate,
    candidate_id,
)


def detect(
    df: pd.DataFrame,
    *,
    timeframe: str,
    features: Iterable[str] = (
        "log_return_mean",
        "log_return_variance",
        "range_atr",
        "directional_persistence",
        "body_ratio",
    ),
    warmup: int = 30,
    sigma_k: float = 3.0,
) -> list[SwingCandidate]:
    """Emit candidates when a feature exceeds sigma_k sigma over its warmup mean.

    The candidate's pivot_time is the bar the shift becomes detectable; the
    pivot_price is the close at that bar (a sentinel, NOT a structural pivot).
    The reconciler treats change-point candidates as evidence of process
    change, never as swing pivots directly.
    """
    n = len(df)
    if n < warmup * 2:
        return []
    close = df["close"].to_numpy(dtype=float)
    logret = np.zeros(n, dtype=float)
    logret[1:] = np.log(np.maximum(close[1:], 1e-12) / np.maximum(close[:-1], 1e-12))
    atr_arr = atr(df)
    rng_atr = candle_range_atr(df, atr_arr)
    persist = consecutive_directional_closes(df)
    body = body_ratio(df)
    realvol = realized_volatility(df)

    series = {
        "log_return_mean": logret,
        "log_return_variance": realvol,
        "range_atr": rng_atr,
        "directional_persistence": persist.astype(float),
        "body_ratio": body,
    }

    out: list[SwingCandidate] = []
    timestamps = df["timestamp"].to_numpy()

    for feat in features:
        if feat not in series:
            continue
        s = series[feat]
        warm = s[:warmup]
        mu = float(np.mean(warm))
        sd = float(np.std(warm, ddof=1)) or 1e-9
        # Track which bars already produced a candidate per feature to avoid
        # emitting one per bar within a sustained shift.
        last_emit = -10_000
        for i in range(warmup, n):
            if abs(s[i] - mu) >= sigma_k * sd:
                if i - last_emit >= warmup:
                    out.append(_make(df, timeframe, i, float(close[i]), feat, abs(s[i] - mu) / sd, timestamps[i]))
                    last_emit = i
    return out


def _make(df, timeframe, i, close_price, feature, shift_sigma, timestamp):
    return SwingCandidate(
        candidate_id=candidate_id(GENERATOR_CHANGEPOINT, timeframe, iso_from_index(df, i), f"cp:{feature}"),
        timeframe=timeframe,
        pivot_type="changepoint",
        pivot_time=iso_from_index(df, i),
        pivot_price=float(close_price),
        generator_source=GENERATOR_CHANGEPOINT,
        scale="atlas",
        prominence=float(round(shift_sigma, 4)),
        volatility_normalized_move=None,
        lifecycle="CANDIDATE",
        causal_origin_hypotheses=[{"feature": feature, "shift_sigma": float(round(shift_sigma, 4))}],
    )


__all__ = ["detect"]


from pandas import DataFrame  # noqa: E402