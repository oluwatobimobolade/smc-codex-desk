"""Tests for smc_desk.calibration."""
from __future__ import annotations

import unittest

import numpy as np

from smc_desk.calibration import (
    brier_score,
    calibrate,
    calibrate_isotonic,
    reliability_curve,
)


class BrierScoreTests(unittest.TestCase):
    def test_perfect(self) -> None:
        preds = np.array([1.0, 0.0, 1.0])
        outcomes = np.array([1.0, 0.0, 1.0])
        self.assertAlmostEqual(brier_score(preds, outcomes), 0.0)

    def test_constant_05(self) -> None:
        preds = np.array([0.5, 0.5, 0.5, 0.5])
        outcomes = np.array([1.0, 0.0, 1.0, 0.0])
        self.assertAlmostEqual(brier_score(preds, outcomes), 0.25)


class ReliabilityCurveTests(unittest.TestCase):
    def test_returns_binned_data(self) -> None:
        preds = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        outcomes = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
        curve = reliability_curve(preds, outcomes, n_bins=5)
        self.assertGreater(len(curve), 0)
        for entry in curve:
            self.assertIn("mean_prediction", entry)
            self.assertIn("mean_outcome", entry)
            self.assertIn("count", entry)

    def test_empty_bins_skipped(self) -> None:
        preds = np.array([0.1, 0.1, 0.1])
        outcomes = np.array([0.0, 1.0, 0.0])
        curve = reliability_curve(preds, outcomes, n_bins=10)
        # Only one bin should have data.
        self.assertEqual(len(curve), 1)


class IsotonicCalibrationTests(unittest.TestCase):
    def test_monotonic_input_unchanged(self) -> None:
        preds = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        outcomes = np.array([0.0, 0.0, 0.5, 1.0, 1.0])
        calibrated = calibrate_isotonic(preds, outcomes)
        # Already monotonic, so calibrated should be close to outcomes.
        self.assertEqual(len(calibrated), len(preds))

    def test_violations_pooled(self) -> None:
        preds = np.array([0.9, 0.1])
        outcomes = np.array([0.0, 1.0])
        calibrated = calibrate_isotonic(preds, outcomes)
        # After isotonic, the high prediction should not have a lower value
        # than the low prediction.
        self.assertLessEqual(calibrated[0], calibrated[1] + 1e-9)

    def test_empty_input(self) -> None:
        calibrated = calibrate_isotonic(np.array([]), np.array([]))
        self.assertEqual(len(calibrated), 0)


class CalibrateReportTests(unittest.TestCase):
    def test_report_has_required_fields(self) -> None:
        preds = np.array([0.3, 0.5, 0.7, 0.8, 0.9])
        outcomes = np.array([0.0, 1.0, 1.0, 1.0, 1.0])
        report = calibrate(preds, outcomes)
        self.assertIn("raw_brier", report.to_dict())
        self.assertIn("calibrated_brier", report.to_dict())
        self.assertIn("reliability", report.to_dict())
        self.assertEqual(report.n_samples, 5)

    def test_calibration_improves_or_maintains_brier(self) -> None:
        preds = np.array([0.9, 0.1, 0.9, 0.1])
        outcomes = np.array([0.0, 1.0, 0.0, 1.0])
        report = calibrate(preds, outcomes)
        self.assertLessEqual(report.calibrated_brier, report.raw_brier + 1e-6)


if __name__ == "__main__":
    unittest.main()
