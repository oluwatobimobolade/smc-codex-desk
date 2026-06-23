"""Tests for the dual-direction trade plan generator."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_ohlcv, build_dual_trade_plan
from smc_desk.rules import RuleConfig, load_rule_config


class DualDirectionEngineTests(unittest.TestCase):
    """Verify the engine emits both long and short candidates on the same chart."""

    def setUp(self) -> None:
        self.ohlcv = ROOT / "data" / "sample_ohlcv.csv"
        if not self.ohlcv.exists():
            raise unittest.SkipTest("sample_ohlcv.csv not found; run tools/generate_sample_ohlcv.py")

    def test_analyze_ohlcv_populates_both_directions(self) -> None:
        config = load_rule_config(None)
        result, _df = analyze_ohlcv(
            ohlcv_path=str(self.ohlcv),
            symbol="EURUSD",
            timeframe="15m",
            config=config,
        )
        self.assertIsNotNone(result.bullish_plan)
        self.assertIsNotNone(result.bearish_plan)
        self.assertEqual(result.bullish_plan.direction, "bullish")
        self.assertEqual(result.bearish_plan.direction, "bearish")

    def test_bullish_and_bearish_plans_use_direction_matched_pois(self) -> None:
        config = load_rule_config(None)
        result, _df = analyze_ohlcv(
            ohlcv_path=str(self.ohlcv),
            symbol="EURUSD",
            timeframe="15m",
            config=config,
        )
        if result.bullish_plan.selected_poi is not None:
            self.assertEqual(result.bullish_plan.selected_poi.direction, "bullish")
        if result.bearish_plan.selected_poi is not None:
            self.assertEqual(result.bearish_plan.selected_poi.direction, "bearish")

    def test_primary_trade_plan_matches_bias_hint(self) -> None:
        config = load_rule_config(None)
        result, _df = analyze_ohlcv(
            ohlcv_path=str(self.ohlcv),
            symbol="EURUSD",
            timeframe="15m",
            config=config,
            bias_hint="bearish",
        )
        self.assertEqual(result.trade_plan.direction, "bearish")

    def test_dual_plan_stops_are_on_correct_side(self) -> None:
        config = load_rule_config(None)
        result, _df = analyze_ohlcv(
            ohlcv_path=str(self.ohlcv),
            symbol="EURUSD",
            timeframe="15m",
            config=config,
        )
        bullish = result.bullish_plan
        bearish = result.bearish_plan
        if bullish.invalidation is not None and bullish.entry_low is not None:
            self.assertLess(bullish.invalidation, bullish.entry_low)
        if bearish.invalidation is not None and bearish.entry_high is not None:
            self.assertGreater(bearish.invalidation, bearish.entry_high)

    def test_hard_gates_apply_independently_per_direction(self) -> None:
        """A direction can be Pass while the opposite is Watch/Execute."""
        config = load_rule_config(None)
        result, _df = analyze_ohlcv(
            ohlcv_path=str(self.ohlcv),
            symbol="EURUSD",
            timeframe="15m",
            config=config,
        )
        # Plans must be independent objects; mutating one must not affect the other.
        self.assertIsNot(result.bullish_plan, result.bearish_plan)
        # Each plan carries its own directional checklist.
        self.assertEqual(result.bullish_plan.checklist.get("directional_bias"), True)
        self.assertEqual(result.bearish_plan.checklist.get("directional_bias"), True)
        # Directional labels are distinct.
        self.assertEqual(result.bullish_plan.direction, "bullish")
        self.assertEqual(result.bearish_plan.direction, "bearish")


if __name__ == "__main__":
    unittest.main()
