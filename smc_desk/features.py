"""OHLCV-derivable features for intent/contextual layers.

These functions replace pixel-based detection for everything that is losslessly
computable from the raw bar data. They are deterministic, fast, and testable.

Each function accepts an optional `decision_time` so callers can enforce the
no-leakage rule explicitly.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _as_records(ohlcv: list[dict] | pd.DataFrame) -> list[dict]:
    if isinstance(ohlcv, pd.DataFrame):
        return ohlcv.to_dict("records")
    return list(ohlcv)


def _trim_to_decision_time(
    records: list[dict],
    decision_time: Optional[str | int],
    time_key: str = "timestamp",
) -> list[dict]:
    """Return only records up to and including the decision cutoff."""
    if decision_time is None:
        return records
    if isinstance(decision_time, int):
        return records[: decision_time + 1]
    # String timestamp comparison.
    return [r for r in records if str(r.get(time_key, "")) <= str(decision_time)]


def wick_body_ratio(record: dict) -> float:
    """Total wick size divided by body size for one bar.

    A high ratio means a long wick relative to the body (rejection).
    """
    body = abs(record["close"] - record["open"])
    if body == 0:
        return float("inf")
    upper_wick = record["high"] - max(record["open"], record["close"])
    lower_wick = min(record["open"], record["close"]) - record["low"]
    return (upper_wick + lower_wick) / body


def upper_wick_rejection_score(record: dict) -> float:
    """Measure of how strongly the bar rejects higher prices.

    Returns a value in [0, 1] where 1 means the close is at the low and the
    upper wick is large relative to the range.
    """
    range_size = record["high"] - record["low"]
    if range_size == 0:
        return 0.0
    upper_wick = record["high"] - max(record["open"], record["close"])
    body_bottom = min(record["open"], record["close"])
    distance_from_top = record["high"] - body_bottom
    if distance_from_top == 0:
        return 0.0
    return upper_wick / distance_from_top


def lower_wick_rejection_score(record: dict) -> float:
    """Measure of how strongly the bar rejects lower prices."""
    range_size = record["high"] - record["low"]
    if range_size == 0:
        return 0.0
    lower_wick = min(record["open"], record["close"]) - record["low"]
    body_top = max(record["open"], record["close"])
    distance_from_bottom = body_top - record["low"]
    if distance_from_bottom == 0:
        return 0.0
    return lower_wick / distance_from_bottom


def detect_vertical_spike_trap(
    ohlcv: list[dict] | pd.DataFrame,
    lookback: int = 5,
    spike_threshold: float = 3.0,
    reversal_bars: int = 2,
    decision_time: Optional[str | int] = None,
) -> dict:
    """Detect a vertical spike trap from OHLCV without rendering to pixels.

    A spike trap is a sudden expansion of range (spike) followed by a reversal
    of at least `reversal_bars` in the opposite direction.

    Returns a dict with keys:
        - detected: bool
        - direction: "bullish" | "bearish" | None
        - spike_index: int | None
        - score: float (0.0 to 1.0)
        - metadata: dict
    """
    records = _as_records(ohlcv)
    records = _trim_to_decision_time(records, decision_time)
    n = len(records)
    if n < lookback + reversal_bars + 1:
        return {"detected": False, "direction": None, "spike_index": None, "score": 0.0, "metadata": {}}

    ranges = np.array([r["high"] - r["low"] for r in records])
    avg_range = np.mean(ranges[max(0, n - lookback - reversal_bars - 5) : n - reversal_bars])
    if avg_range <= 0:
        avg_range = 1e-9

    best: dict = {"detected": False, "direction": None, "spike_index": None, "score": 0.0, "metadata": {}}

    # Look for a spike in the recent history, leaving room for reversal bars.
    for spike_idx in range(n - reversal_bars - 1, max(lookback, n - lookback - reversal_bars) - 1, -1):
        spike_range = ranges[spike_idx]
        if spike_range < spike_threshold * avg_range:
            continue

        # Determine spike direction by where the close sits in the range.
        spike = records[spike_idx]
        upper_wick = spike["high"] - max(spike["open"], spike["close"])
        lower_wick = min(spike["open"], spike["close"]) - spike["low"]

        if upper_wick > lower_wick * 1.5:
            spike_direction = "bullish"  # spike up, likely bearish trap
        elif lower_wick > upper_wick * 1.5:
            spike_direction = "bearish"  # spike down, likely bullish trap
        else:
            continue

        # Check reversal: the next bars move opposite to the spike.
        reversal_start = spike_idx + 1
        reversal_end = min(reversal_start + reversal_bars, n)
        start_close = records[reversal_start]["close"]
        end_close = records[reversal_end - 1]["close"]

        if spike_direction == "bullish" and end_close >= start_close:
            continue
        if spike_direction == "bearish" and end_close <= start_close:
            continue

        score = min(1.0, spike_range / (avg_range * spike_threshold))
        if score > best["score"]:
            best = {
                "detected": True,
                "direction": spike_direction,
                "spike_index": spike_idx,
                "score": round(score, 4),
                "metadata": {
                    "spike_range": round(spike_range, 5),
                    "avg_range": round(avg_range, 5),
                    "reversal_bars": reversal_end - reversal_start,
                    "reversal_distance": round(abs(end_close - start_close), 5),
                },
            }

    return best


def detect_failed_breakout(
    ohlcv: list[dict] | pd.DataFrame,
    lookback: int = 10,
    confirmation_bars: int = 3,
    decision_time: Optional[str | int] = None,
) -> dict:
    """Detect a failed breakout from OHLCV.

    A failed breakout occurs when price pierces a recent extreme but closes back
    inside the established range within `confirmation_bars`.

    Returns a dict with keys:
        - detected: bool
        - direction: "bullish" | "bearish" | None
        - breakout_index: int | None
        - score: float (0.0 to 1.0)
        - metadata: dict
    """
    records = _as_records(ohlcv)
    records = _trim_to_decision_time(records, decision_time)
    n = len(records)
    if n < lookback + confirmation_bars + 1:
        return {"detected": False, "direction": None, "breakout_index": None, "score": 0.0, "metadata": {}}

    best: dict = {"detected": False, "direction": None, "breakout_index": None, "score": 0.0, "metadata": {}}

    for idx in range(lookback, n - confirmation_bars + 1):
        base_window = records[idx - lookback : idx]
        base_high = max(r["high"] for r in base_window)
        base_low = min(r["low"] for r in base_window)
        bar = records[idx]
        post_bars = records[idx + 1 : idx + 1 + confirmation_bars]
        if not post_bars:
            continue

        # Bullish failed breakout: wick above resistance then close back below.
        if bar["high"] > base_high:
            all_back_inside = all(b["close"] < base_high and b["high"] < bar["high"] for b in post_bars)
            if all_back_inside:
                score = min(1.0, (bar["high"] - base_high) / max(base_high - base_low, 1e-9))
                if score > best["score"]:
                    best = {
                        "detected": True,
                        "direction": "bearish",
                        "breakout_index": idx,
                        "score": round(score, 4),
                        "metadata": {
                            "base_high": round(base_high, 5),
                            "base_low": round(base_low, 5),
                            "breakout_high": round(bar["high"], 5),
                            "confirmation_bars": len(post_bars),
                        },
                    }

        # Bearish failed breakout: wick below support then close back above.
        if bar["low"] < base_low:
            all_back_inside = all(b["close"] > base_low and b["low"] > bar["low"] for b in post_bars)
            if all_back_inside:
                score = min(1.0, (base_low - bar["low"]) / max(base_high - base_low, 1e-9))
                if score > best["score"]:
                    best = {
                        "detected": True,
                        "direction": "bullish",
                        "breakout_index": idx,
                        "score": round(score, 4),
                        "metadata": {
                            "base_high": round(base_high, 5),
                            "base_low": round(base_low, 5),
                            "breakout_low": round(bar["low"], 5),
                            "confirmation_bars": len(post_bars),
                        },
                    }

    return best


def regime_features(ohlcv: list[dict] | pd.DataFrame, lookback: int = 20) -> dict:
    """Compute simple trend/volatility features useful for intent modulation.

    Returns:
        - adx_proxy: average directional move per bar / ATR (rough proxy)
        - volatility_pct: current ATR as % of price
        - net_change: close[-1] - close[-lookback]
    """
    records = _as_records(ohlcv)
    if len(records) < lookback:
        return {"adx_proxy": 0.0, "volatility_pct": 0.0, "net_change": 0.0}

    window = records[-lookback:]
    closes = np.array([r["close"] for r in window])
    highs = np.array([r["high"] for r in window])
    lows = np.array([r["low"] for r in window])

    atr = np.mean(highs - lows)
    price = closes[-1]
    net_change = closes[-1] - closes[0]
    gross_moves = np.sum(np.abs(np.diff(closes)))
    adx_proxy = abs(net_change) / gross_moves if gross_moves > 0 else 0.0

    return {
        "adx_proxy": round(adx_proxy, 4),
        "volatility_pct": round(atr / max(price, 1e-9), 4),
        "net_change": round(net_change, 5),
    }
