"""Observable, scale-free market-state features for evidence packs.

These features describe price-path and range behavior.  They intentionally do
not infer accumulation, distribution, participant intent, or trade direction.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def observe_regime_features(frame: pd.DataFrame, *, lookback: int = 96) -> dict[str, Any]:
    required = {"open", "high", "low", "close"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        return _failed("missing_columns", {"columns": missing})
    work = frame.tail(lookback).copy()
    if len(work) < 30:
        return {
            **_base_contract(),
            "data_status": "INSUFFICIENT",
            "sample_bars": len(work),
            "minimum_bars": 30,
            "reason_codes": ["insufficient_history"],
            "features": {},
            "descriptive_states": {},
        }
    try:
        for column in required:
            work[column] = pd.to_numeric(work[column], errors="raise")
    except (TypeError, ValueError) as exc:
        return _failed("non_numeric_ohlc", {"detail": str(exc)})
    invalid = (
        (work["high"] < work[["open", "close", "low"]].max(axis=1))
        | (work["low"] > work[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        return _failed("impossible_ohlc_geometry", {"invalid_rows": int(invalid.sum())})

    closes = work["close"].to_numpy(dtype=float)
    opens = work["open"].to_numpy(dtype=float)
    highs = work["high"].to_numpy(dtype=float)
    lows = work["low"].to_numpy(dtype=float)
    path = float(np.abs(np.diff(closes)).sum())
    net = float(closes[-1] - closes[0])
    efficiency = abs(net) / path if path > 0 else 0.0
    true_ranges = _true_ranges(highs, lows, closes)
    recent_atr = float(np.mean(true_ranges[-14:]))
    baseline_slice = true_ranges[:-14]
    baseline_atr = float(np.median(baseline_slice)) if len(baseline_slice) else recent_atr
    atr_ratio = recent_atr / baseline_atr if baseline_atr > 0 else None
    normalized_net_move = float(net / (recent_atr * np.sqrt(len(work)))) if recent_atr > 0 else None

    ranges = highs - lows
    safe_ranges = np.where(ranges > 0, ranges, np.nan)
    upper_wicks = highs - np.maximum(opens, closes)
    lower_wicks = np.minimum(opens, closes) - lows
    max_wick_ratio = np.nan_to_num(np.maximum(upper_wicks, lower_wicks) / safe_ranges, nan=0.0)
    rejection_rate = float(np.mean(max_wick_ratio >= 0.55))
    sweep_highs, sweep_lows = _sweep_proxies(highs, lows, closes, window=10)
    sweep_rate = (sweep_highs + sweep_lows) / max(len(work) - 10, 1)
    normalized_changes = np.diff(closes) / recent_atr if recent_atr > 0 else np.diff(closes)
    autocorrelation = _lag_one_autocorrelation(normalized_changes)

    features = {
        "directional_efficiency": round(efficiency, 8),
        "signed_net_move_atr_sqrt_n": None if normalized_net_move is None else round(normalized_net_move, 8),
        "recent_to_baseline_atr_ratio": None if atr_ratio is None else round(atr_ratio, 8),
        "large_wick_rejection_rate": round(rejection_rate, 8),
        "ten_bar_high_sweep_proxy_count": sweep_highs,
        "ten_bar_low_sweep_proxy_count": sweep_lows,
        "sweep_proxy_rate": round(sweep_rate, 8),
        "return_lag_one_autocorrelation": None if autocorrelation is None else round(autocorrelation, 8),
    }
    states = {
        "price_path": _path_state(efficiency),
        "range_behavior": _range_state(atr_ratio),
        "wick_rejection": _rejection_state(rejection_rate),
        "sweep_proxy_activity": _sweep_state(sweep_rate),
    }
    return {
        **_base_contract(),
        "data_status": "AVAILABLE",
        "sample_bars": len(work),
        "minimum_bars": 30,
        "reason_codes": [],
        "features": features,
        "descriptive_states": states,
        "thresholds": {
            "directional_efficiency": {"choppy_max": 0.18, "directional_min": 0.34},
            "atr_ratio": {"contracted_max": 0.75, "expanded_min": 1.45},
            "large_wick_ratio": 0.55,
            "rejection_rate": {"infrequent_max": 0.15, "frequent_min": 0.35},
            "sweep_proxy_rate": {"low_max": 0.08, "high_min": 0.18},
        },
    }


def _base_contract() -> dict[str, Any]:
    return {
        "schema": "observable_regime_features_v1",
        "epistemic_class": "OBSERVED_DERIVED_FEATURES",
        "participant_intent_inferred": False,
        "accumulation_distribution_inferred": False,
        "forecast_authority": False,
        "signal_allowed": False,
    }


def _failed(reason: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base_contract(),
        "data_status": "FAILED",
        "sample_bars": 0,
        "reason_codes": [reason],
        "failure_detail": detail,
        "features": {},
        "descriptive_states": {},
    }


def _true_ranges(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
    previous = np.concatenate(([closes[0]], closes[:-1]))
    return np.maximum.reduce((highs - lows, np.abs(highs - previous), np.abs(lows - previous)))


def _sweep_proxies(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, *, window: int) -> tuple[int, int]:
    high_count = 0
    low_count = 0
    for index in range(window, len(closes)):
        prior_high = float(np.max(highs[index - window:index]))
        prior_low = float(np.min(lows[index - window:index]))
        if highs[index] > prior_high and closes[index] < prior_high:
            high_count += 1
        if lows[index] < prior_low and closes[index] > prior_low:
            low_count += 1
    return high_count, low_count


def _lag_one_autocorrelation(values: np.ndarray) -> float | None:
    if len(values) < 3 or float(np.std(values[:-1])) == 0 or float(np.std(values[1:])) == 0:
        return None
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


def _path_state(value: float) -> str:
    return "CHOPPY" if value <= 0.18 else "DIRECTIONAL" if value >= 0.34 else "MIXED"


def _range_state(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    return "CONTRACTED" if value <= 0.75 else "EXPANDED" if value >= 1.45 else "STABLE"


def _rejection_state(value: float) -> str:
    return "INFREQUENT" if value <= 0.15 else "FREQUENT" if value >= 0.35 else "MIXED"


def _sweep_state(value: float) -> str:
    return "LOW" if value <= 0.08 else "HIGH" if value >= 0.18 else "MODERATE"


__all__ = ["observe_regime_features"]
