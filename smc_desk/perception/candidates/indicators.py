"""Deterministic indicators shared by every candidate generator.

These are intentionally simple, dependency-free, and deterministic (no random
seeds, no look-ahead). They operate on a canonical OHLCV DataFrame with
columns (timestamp, open, high, low, close, volume) produced by
``smc_desk/data/ohlcv_contract.py``.

The generators only ever need: ATR, realized volatility, candle body/range,
directional-close runs, and FVG detection. Nothing here touches future data
beyond the row being computed (no centering, no smoothing that looks forward).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _iso(value: Any) -> str:
    if pd.isna(value):
        return ""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat().replace("+00:00", "Z")


def true_range(df: pd.DataFrame) -> np.ndarray:
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    prev_close = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum.reduce(
        [
            high - low,
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ]
    )
    tr[0] = high[0] - low[0]
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Wilder-style ATR, computed causally (each value uses only past data)."""
    tr = true_range(df)
    n = len(tr)
    if n == 0:
        return np.array([])
    out = np.empty(n, dtype=float)
    out[0] = tr[0]
    # Wilder smoothing: alpha = 1/period
    alpha = 1.0 / max(period, 1)
    for i in range(1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period if i < period else out[i - 1] * (1 - alpha) + tr[i] * alpha
        if i < period:
            # use simple average over the warmup window
            out[i] = tr[: i + 1].mean()
    return out


def realized_volatility(df: pd.DataFrame, period: int = 20) -> np.ndarray:
    """Rolling std of log returns over the prior `period` closed candles."""
    close = df["close"].to_numpy(dtype=float)
    n = len(close)
    out = np.zeros(n, dtype=float)
    if n == 0:
        return out
    logret = np.zeros(n, dtype=float)
    logret[1:] = np.log(np.maximum(close[1:], 1e-12) / np.maximum(close[:-1], 1e-12))
    for i in range(n):
        if i >= period:
            out[i] = float(np.std(logret[i - period + 1 : i + 1], ddof=0))
    return out


def body_ratio(df: pd.DataFrame) -> np.ndarray:
    """|close - open| / max(high - low, eps) -- 0..1 body size."""
    o = df["open"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    rng = np.maximum(h - l, 1e-12)
    return np.abs(c - o) / rng


def candle_range_atr(df: pd.DataFrame, atr_arr: np.ndarray) -> np.ndarray:
    rng = (df["high"].to_numpy(dtype=float) - df["low"].to_numpy(dtype=float))
    return rng / np.maximum(atr_arr, 1e-12)


def consecutive_directional_closes(df: pd.DataFrame) -> np.ndarray:
    """For each bar i, how many consecutive bars up to and including i closed
    in the same direction as bar i. 1 = bar i is the first in its run."""
    c = df["close"].to_numpy(dtype=float)
    o = df["open"].to_numpy(dtype=float)
    n = len(c)
    out = np.ones(n, dtype=int)
    for i in range(1, n):
        same = np.sign(c[i] - o[i]) == np.sign(c[i - 1] - o[i - 1]) and (c[i] != o[i])
        if same:
            out[i] = out[i - 1] + 1
        else:
            out[i] = 1
    return out


def detect_fvgs(df: pd.DataFrame, min_gap_atr: float = 0.1, atr_arr: np.ndarray | None = None) -> list[dict]:
    """Detect Fair Value Gaps (three-candle imbalance), computed causally.

    A bullish FVG forms when candle[i+1].low > candle[i-1].high. A bearish
    FVG forms when candle[i+1].high < candle[i-1].low. The object becomes
    available only when candle[i+1] closes.
    """
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    ts = df["timestamp"].to_numpy()
    n = len(h)
    if atr_arr is None:
        atr_arr = atr(df)
    fvgs: list[dict] = []
    for i in range(1, n - 1):
        gap = l[i + 1] - h[i - 1]
        if gap > min_gap_atr * max(atr_arr[i], 1e-12):
            fvgs.append({
                "index": i,
                "kind": "bullish",
                "low": h[i - 1],
                "high": l[i + 1],
                "time": _iso(ts[i]),
                "confirmed_at": _iso(ts[i + 1]),
            })
            continue
        gap = l[i - 1] - h[i + 1]
        if gap > min_gap_atr * max(atr_arr[i], 1e-12):
            fvgs.append({
                "index": i,
                "kind": "bearish",
                "low": h[i + 1],
                "high": l[i - 1],
                "time": _iso(ts[i]),
                "confirmed_at": _iso(ts[i + 1]),
            })
    return fvgs


def iso_from_index(df: pd.DataFrame, i: int) -> str:
    return _iso(df["timestamp"].to_numpy()[i])
