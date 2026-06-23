"""Tests that hard gates are binary vetoes, not score deductions."""
from __future__ import annotations

import unittest

from smc_desk.engine import _build_trade_plan_for_direction
from smc_desk.models import StructureEvent, Zone
from smc_desk.rules import RuleConfig

import pandas as pd


class HardGateVetoTests(unittest.TestCase):
    """A disqualifier must force Pass even if every other signal is perfect."""

    def _make_bullish_df(self, close: float = 100.0, bars: int = 50) -> pd.DataFrame:
        """A boring upward drift with the final bar at `close`."""
        rows = []
        for i in range(bars):
            price = 95.0 + i * 0.1
            rows.append({
                "timestamp": f"2026-01-01T{i:02d}:00:00",
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.1,
                "volume": 1.0,
            })
        # Overwrite the last close to the requested value.
        rows[-1]["close"] = close
        rows[-1]["high"] = max(rows[-1]["high"], close)
        rows[-1]["low"] = min(rows[-1]["low"], close)
        return pd.DataFrame(rows)

    def _make_ranging_df(self, close: float = 95.5) -> pd.DataFrame:
        """A flat range from 90 to 110; midpoint is 100.

        Lets us place a discount bullish POI at 95-96 with price inside it.
        """
        rows = []
        for i in range(50):
            rows.append({
                "timestamp": f"2026-01-01T{i:02d}:00:00",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 100.0,
                "volume": 1.0,
            })
        rows[-1]["close"] = close
        rows[-1]["high"] = max(rows[-1]["high"], close)
        rows[-1]["low"] = min(rows[-1]["low"], close)
        return pd.DataFrame(rows)

    def _make_perfect_bullish_poi(self, low: float, high: float) -> Zone:
        return Zone(
            label="Bullish FVG",
            kind="fvg",
            direction="bullish",
            low=low,
            high=high,
            start_index=40,
            end_index=42,
            status="fresh",
            score=0.9,
            reason="synthetic perfect POI",
        )

    def _make_perfect_sweep(self, index: int, price: float) -> StructureEvent:
        return StructureEvent(
            label="Liquidity Sweep",
            direction="bullish",
            index=index,
            timestamp="2026-01-01T00:00:00",
            price=price,
            reason="synthetic perfect sweep",
        )

    def _make_perfect_break(self, index: int, price: float) -> StructureEvent:
        return StructureEvent(
            label="BOS",
            direction="bullish",
            index=index,
            timestamp="2026-01-01T00:00:00",
            price=price,
            structure_scope="swing",
            strength="strong",
            displacement_score=1.0,
            reason="synthetic perfect break",
        )

    def test_rr_floor_below_minimum_forces_pass(self) -> None:
        """A plan that would otherwise be Watch must be Pass when R:R is too low."""
        config = RuleConfig(risk_reward_floor=3.0)
        # Flat range 90-110, midpoint 100. Price at 95.5 inside a discount POI.
        df = self._make_ranging_df(close=95.5)
        poi = self._make_perfect_bullish_poi(low=95.0, high=96.0)
        # Nearby liquidity at 97 gives a poor R:R; every other gate can pass.
        liquidity = Zone(
            label="Equal Highs",
            kind="liquidity",
            direction="bearish",
            low=97.0,
            high=97.0,
            status="fresh",
            score=0.8,
            reason="nearby liquidity",
        )
        sweep = self._make_perfect_sweep(index=47, price=94.5)
        break_event = StructureEvent(
            label="BOS",
            direction="bullish",
            index=48,
            timestamp="2026-01-01T00:00:00",
            price=95.6,
            structure_scope="swing",
            strength="strong",
            displacement_score=1.5,
            reason="synthetic perfect break",
        )
        zones = [poi, liquidity]
        events = [sweep, break_event]

        plan = _build_trade_plan_for_direction(
            df=df,
            swings=[],
            zones=zones,
            events=events,
            config=config,
            direction="bullish",
        )
        # The only failing gate must be R:R.
        self.assertFalse(plan.checklist.get("risk_reward_floor"), plan.checklist)
        self.assertTrue(plan.checklist.get("fresh_or_partial_poi"), plan.checklist)
        self.assertTrue(plan.checklist.get("liquidity_sweep"), plan.checklist)
        self.assertTrue(plan.checklist.get("displacement_break"), plan.checklist)
        self.assertTrue(plan.checklist.get("sweep_before_break"), plan.checklist)
        self.assertTrue(plan.checklist.get("price_at_or_near_poi"), plan.checklist)
        # The R:R hard gate must veto any Execute/Watch verdict.
        self.assertEqual(plan.verdict, "Pass")
        self.assertTrue(
            any("risk/reward" in w.lower() or "risk_reward" in w.lower() for w in plan.warnings),
            f"expected R:R warning, got {plan.warnings}",
        )

    def test_perfect_checklist_without_rr_still_passes_rr_gate(self) -> None:
        """Sanity: a setup with R:R above floor should be allowed to Execute."""
        config = RuleConfig(risk_reward_floor=3.0)
        df = self._make_bullish_df(close=100.0)
        poi = self._make_perfect_bullish_poi(low=99.5, high=100.0)
        liquidity = Zone(
            label="Equal Highs",
            kind="liquidity",
            direction="bearish",
            low=103.5,
            high=103.5,
            status="fresh",
            score=0.8,
            reason="distant liquidity",
        )
        sweep = self._make_perfect_sweep(index=47, price=99.0)
        break_event = self._make_perfect_break(index=48, price=100.1)
        zones = [poi, liquidity]
        events = [sweep, break_event]

        plan = _build_trade_plan_for_direction(
            df=df,
            swings=[],
            zones=zones,
            events=events,
            config=config,
            direction="bullish",
        )
        self.assertIsNotNone(plan.risk_reward)
        if plan.risk_reward is not None:
            self.assertGreaterEqual(plan.risk_reward, config.risk_reward_floor)


if __name__ == "__main__":
    unittest.main()
