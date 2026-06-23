"""Calibration utilities for fusion layer confidence scores.

Until a confidence number is calibrated against the gold set (Brier score,
reliability curve, isotonic/Platt regression), the rule runs in log-only mode
and contributes nothing to the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class CalibrationReport:
    """Result of calibrating a set of confidence scores against outcomes."""

    raw_brier: float
    calibrated_brier: float
    reliability: list[dict[str, float]]
    isotonic_weights: np.ndarray | None = None
    n_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_brier": round(self.raw_brier, 4),
            "calibrated_brier": round(self.calibrated_brier, 4),
            "reliability": self.reliability,
            "n_samples": self.n_samples,
        }


def brier_score(predictions: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean squared error between predicted probabilities and binary outcomes."""
    return float(np.mean((predictions - outcomes) ** 2))


def reliability_curve(
    predictions: np.ndarray, outcomes: np.ndarray, n_bins: int = 5
) -> list[dict[str, float]]:
    """Binned calibration: for each bin, mean prediction vs mean outcome."""
    bins = np.linspace(0, 1, n_bins + 1)
    curve: list[dict[str, float]] = []
    for i in range(n_bins):
        mask = (predictions >= bins[i]) & (predictions < bins[i + 1])
        if mask.sum() == 0:
            continue
        curve.append({
            "bin_low": round(float(bins[i]), 2),
            "bin_high": round(float(bins[i + 1]), 2),
            "mean_prediction": round(float(predictions[mask].mean()), 4),
            "mean_outcome": round(float(outcomes[mask].mean()), 4),
            "count": int(mask.sum()),
        })
    return curve


def calibrate_isotonic(predictions: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Simple isotonic regression (pool-adjacent-violators algorithm).

    Returns the calibrated predictions. Does not require sklearn.
    """
    n = len(predictions)
    if n == 0:
        return predictions

    # Sort by prediction.
    order = np.argsort(predictions)
    sorted_preds = predictions[order]
    sorted_outcomes = outcomes[order]

    # Pool-adjacent-violators.
    weights = np.ones(n)
    values = sorted_outcomes.copy().astype(float)
    preds = sorted_preds.copy().astype(float)

    i = 0
    while i < len(values) - 1:
        if values[i] > values[i + 1]:
            # Violation: pool.
            pooled_w = weights[i] + weights[i + 1]
            pooled_v = (values[i] * weights[i] + values[i + 1] * weights[i + 1]) / pooled_w
            values[i] = pooled_v
            weights[i] = pooled_w
            values = np.delete(values, i + 1)
            weights = np.delete(weights, i + 1)
            preds = np.delete(preds, i + 1)
            if i > 0:
                i -= 1
        else:
            i += 1

    # Map back: for each original prediction, find the calibrated value.
    calibrated = np.zeros(n)
    for idx in range(n):
        orig_pred = predictions[idx]
        # Find the nearest calibrated prediction.
        pos = np.searchsorted(preds, orig_pred)
        if pos == 0:
            calibrated[idx] = values[0]
        elif pos >= len(values):
            calibrated[idx] = values[-1]
        else:
            calibrated[idx] = values[pos]
    return calibrated


def calibrate(predictions: np.ndarray, outcomes: np.ndarray) -> CalibrationReport:
    """Full calibration report: raw Brier, isotonic-calibrated Brier, reliability."""
    raw_brier = brier_score(predictions, outcomes)
    calibrated_preds = calibrate_isotonic(predictions, outcomes)
    calibrated_brier = brier_score(calibrated_preds, outcomes)
    reliability = reliability_curve(predictions, outcomes)
    return CalibrationReport(
        raw_brier=raw_brier,
        calibrated_brier=calibrated_brier,
        reliability=reliability,
        isotonic_weights=calibrated_preds,
        n_samples=len(predictions),
    )
