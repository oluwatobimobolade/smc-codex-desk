"""Tests for the fusion gold-set and judgment evaluation tools."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evaluate_fusion_judgment import evaluate, _direction_match, _brier_score
import numpy as np


class DirectionMatchTests(unittest.TestCase):
    def test_long_matches_bullish(self) -> None:
        self.assertTrue(_direction_match("long", "bullish"))

    def test_short_matches_bearish(self) -> None:
        self.assertTrue(_direction_match("short", "bearish"))

    def test_no_trade_matches_neutral(self) -> None:
        self.assertTrue(_direction_match("no_trade", "neutral"))

    def test_long_does_not_match_bearish(self) -> None:
        self.assertFalse(_direction_match("long", "bearish"))


class BrierScoreTests(unittest.TestCase):
    def test_perfect_prediction(self) -> None:
        preds = np.array([1.0, 1.0, 0.0, 0.0])
        outcomes = np.array([1.0, 1.0, 0.0, 0.0])
        self.assertAlmostEqual(_brier_score(preds, outcomes), 0.0)

    def test_worst_prediction(self) -> None:
        preds = np.array([1.0, 0.0])
        outcomes = np.array([0.0, 1.0])
        self.assertAlmostEqual(_brier_score(preds, outcomes), 1.0)

    def test_half_prediction(self) -> None:
        preds = np.array([0.5, 0.5])
        outcomes = np.array([1.0, 0.0])
        self.assertAlmostEqual(_brier_score(preds, outcomes), 0.25)


class EvaluateTests(unittest.TestCase):
    def _make_case(
        self,
        human_dir: str = "long",
        human_conv: str = "high",
        fusion_dir: str = "bullish",
        fusion_verdict: str = "Execute",
        fusion_conf: float = 0.8,
        engine_dir: str = "bullish",
        engine_verdict: str = "Execute",
        contested: bool = False,
    ) -> dict:
        return {
            "case_id": "test_001",
            "human_direction": human_dir,
            "human_conviction": human_conv,
            "human_why": "test",
            "fusion_verdict": fusion_verdict,
            "fusion_direction": fusion_dir,
            "fusion_confidence": fusion_conf,
            "fusion_contested": contested,
            "engine_verdict": engine_verdict,
            "engine_direction": engine_dir,
        }

    def test_empty_cases_returns_no_adjudicated(self) -> None:
        report = evaluate([])
        self.assertEqual(report["status"], "no_adjudicated_cases")

    def test_perfect_direction_accuracy(self) -> None:
        cases = [
            self._make_case(human_dir="long", fusion_dir="bullish"),
            self._make_case(human_dir="short", fusion_dir="bearish"),
            self._make_case(human_dir="no_trade", fusion_dir="neutral"),
        ]
        report = evaluate(cases)
        self.assertEqual(report["direction_accuracy"], 1.0)
        self.assertEqual(report["verdict"], "NO-GO")  # not enough cases

    def test_enough_cases_with_good_accuracy_passes_gates(self) -> None:
        cases = []
        for i in range(12):
            cases.append(self._make_case(
                human_dir="long",
                fusion_dir="bullish",
                fusion_conf=0.9,
            ))
        report = evaluate(cases)
        self.assertEqual(report["direction_accuracy"], 1.0)
        self.assertLessEqual(report["brier_score"], 0.25)
        self.assertTrue(report["acceptance_gates"]["direction_accuracy_gte_85"])
        self.assertTrue(report["acceptance_gates"]["min_cases_met"])
        self.assertEqual(report["verdict"], "GO")

    def test_poor_direction_accuracy_fails_gate(self) -> None:
        cases = []
        for i in range(12):
            cases.append(self._make_case(
                human_dir="long",
                fusion_dir="bearish",  # wrong
                fusion_conf=0.9,
            ))
        report = evaluate(cases)
        self.assertFalse(report["acceptance_gates"]["direction_accuracy_gte_85"])
        self.assertEqual(report["verdict"], "NO-GO")

    def test_no_trade_accuracy(self) -> None:
        cases = [
            self._make_case(human_dir="no_trade", fusion_dir="neutral", fusion_verdict="Pass"),
            self._make_case(human_dir="no_trade", fusion_dir="neutral", fusion_verdict="Pass"),
            self._make_case(human_dir="no_trade", fusion_dir="bullish", fusion_verdict="Execute"),  # wrong
        ]
        report = evaluate(cases)
        self.assertAlmostEqual(report["no_trade_accuracy"], 2 / 3, places=2)

    def test_reliability_curve_returned(self) -> None:
        cases = [self._make_case(fusion_conf=0.3 + i * 0.1) for i in range(8)]
        report = evaluate(cases)
        self.assertIn("reliability_curve", report)
        self.assertIsInstance(report["reliability_curve"], list)

    def test_engine_baseline_comparison(self) -> None:
        cases = [
            self._make_case(human_dir="long", fusion_dir="bullish", engine_dir="bearish"),
            self._make_case(human_dir="long", fusion_dir="bullish", engine_dir="bearish"),
        ]
        report = evaluate(cases)
        self.assertEqual(report["direction_accuracy"], 1.0)
        self.assertEqual(report["engine_baseline_accuracy"], 0.0)
        self.assertGreater(report["fusion_vs_engine_delta"], 0.0)


if __name__ == "__main__":
    unittest.main()
