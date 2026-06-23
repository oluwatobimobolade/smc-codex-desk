"""Tests for smc_desk.features."""
from __future__ import annotations

import unittest

from smc_desk.features import (
    detect_failed_breakout,
    detect_vertical_spike_trap,
    regime_features,
    upper_wick_rejection_score,
    wick_body_ratio,
)


class WickFeaturesTests(unittest.TestCase):
    def test_wick_body_ratio_for_long_wick(self) -> None:
        bar = {"open": 100.0, "high": 105.0, "low": 99.5, "close": 100.2}
        ratio = wick_body_ratio(bar)
        self.assertGreater(ratio, 3.0)

    def test_upper_wick_rejection_score_high(self) -> None:
        bar = {"open": 100.0, "high": 105.0, "low": 99.5, "close": 99.6}
        score = upper_wick_rejection_score(bar)
        self.assertGreater(score, 0.9)

    def test_upper_wick_rejection_score_low(self) -> None:
        bar = {"open": 100.0, "high": 100.1, "low": 99.5, "close": 100.09}
        score = upper_wick_rejection_score(bar)
        self.assertLess(score, 0.2)


class VerticalSpikeTests(unittest.TestCase):
    def _spike_ohlcv(self) -> list[dict[str, float]]:
        data: list[dict[str, float]] = []
        base = 100.0
        for _ in range(5):
            data.append({"open": base, "high": base + 0.5, "low": base - 0.5, "close": base, "volume": 1.0})
        # Spike up with long upper wick
        data.append({"open": base, "high": base + 6.0, "low": base, "close": base + 0.5, "volume": 5.0})
        # Reversal down
        data.append({"open": base + 0.5, "high": base + 1.0, "low": base - 2.0, "close": base - 1.5, "volume": 4.0})
        data.append({"open": base - 1.5, "high": base - 0.5, "low": base - 3.0, "close": base - 2.5, "volume": 3.0})
        return data

    def test_detects_vertical_spike_trap(self) -> None:
        result = detect_vertical_spike_trap(self._spike_ohlcv(), lookback=5, spike_threshold=2.0)
        self.assertTrue(result["detected"])
        self.assertEqual(result["direction"], "bullish")
        self.assertGreater(result["score"], 0.0)

    def test_no_spike_in_flat_data(self) -> None:
        flat = [{"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "volume": 1.0} for _ in range(20)]
        result = detect_vertical_spike_trap(flat)
        self.assertFalse(result["detected"])

    def test_respects_decision_time_cutoff(self) -> None:
        data = self._spike_ohlcv()
        # Cutoff before the reversal bars; spike should not be confirmed.
        result = detect_vertical_spike_trap(data, decision_time=5)
        self.assertFalse(result["detected"])


class FailedBreakoutTests(unittest.TestCase):
    def _failed_breakout_ohlcv(self) -> list[dict[str, float]]:
        data: list[dict[str, float]] = []
        for _ in range(6):
            data.append({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1.0})
        # Wick above resistance then fail
        data.append({"open": 100.0, "high": 103.0, "low": 99.8, "close": 100.1, "volume": 2.0})
        # Fail to reclaim
        for _ in range(4):
            data.append({"open": 100.1, "high": 100.3, "low": 99.7, "close": 99.9, "volume": 1.0})
        return data

    def test_detects_bullish_failed_breakout(self) -> None:
        result = detect_failed_breakout(self._failed_breakout_ohlcv(), lookback=6, confirmation_bars=3)
        self.assertTrue(result["detected"])
        self.assertEqual(result["direction"], "bearish")

    def test_no_breakout_in_flat_data(self) -> None:
        flat = [{"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "volume": 1.0} for _ in range(20)]
        result = detect_failed_breakout(flat)
        self.assertFalse(result["detected"])

    def test_respects_decision_time_cutoff(self) -> None:
        data = self._failed_breakout_ohlcv()
        # Cutoff before confirmation bars.
        result = detect_failed_breakout(data, decision_time=6)
        self.assertFalse(result["detected"])


class RegimeFeaturesTests(unittest.TestCase):
    def test_regime_features_return_reasonable_values(self) -> None:
        data = [
            {"open": 100.0 + i * 0.1, "high": 100.5 + i * 0.1, "low": 99.5 + i * 0.1, "close": 100.1 + i * 0.1, "volume": 1.0}
            for i in range(30)
        ]
        features = regime_features(data, lookback=20)
        self.assertGreaterEqual(features["adx_proxy"], 0.0)
        self.assertLessEqual(features["adx_proxy"], 1.0)
        self.assertGreater(features["volatility_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
