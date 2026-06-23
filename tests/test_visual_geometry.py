from __future__ import annotations

import unittest

import pandas as pd

from smc_desk.models import StructureEvent, SwingPoint, TradePlan, Zone
from smc_desk.visual_geometry import (
    has_actionable_plan,
    plan_levels,
    select_display_events,
    structure_origin_index,
    zone_lifecycle,
)


def candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=6, freq="15min"),
            "open": [101.0, 102.0, 103.0, 104.0, 102.0, 101.0],
            "high": [102.0, 103.0, 104.0, 105.0, 103.0, 102.0],
            "low": [100.0, 101.0, 102.0, 103.0, 99.0, 100.0],
            "close": [101.5, 102.5, 103.5, 104.5, 100.0, 101.5],
            "volume": [1.0] * 6,
        }
    )


def zone(*, kind: str = "fvg", direction: str = "bullish", status: str = "fresh") -> Zone:
    return Zone(
        label="Bullish FVG" if kind == "fvg" else "Equal Lows",
        kind=kind,
        direction=direction,
        low=100.0,
        high=102.0,
        start_index=1,
        end_index=2,
        status=status,
        reason="test",
    )


class VisualGeometryTests(unittest.TestCase):
    def test_active_zone_runs_from_confirmation_to_decision_not_an_arbitrary_width(self) -> None:
        df = candles().assign(low=[100.0, 101.0, 102.0, 103.0, 100.5, 100.5])
        lifecycle = zone_lifecycle(df, zone(), [])

        self.assertEqual(lifecycle.activation_index, 2)
        self.assertEqual(lifecycle.end_index, 5)
        self.assertTrue(lifecycle.is_active)

    def test_mitigated_zone_stops_on_first_full_mitigation_candle(self) -> None:
        lifecycle = zone_lifecycle(candles(), zone(), [])

        self.assertEqual(lifecycle.activation_index, 2)
        self.assertEqual(lifecycle.end_index, 4)
        self.assertEqual(lifecycle.state, "mitigated")
        self.assertFalse(lifecycle.is_active)

    def test_liquidity_pool_stops_at_matching_sweep(self) -> None:
        liquidity = zone(kind="liquidity", direction="bullish")
        sweep = StructureEvent(
            label="Liquidity Sweep",
            direction="bullish",
            index=4,
            timestamp="2026-01-01T01:00:00",
            price=99.0,
            swept_level=100.4,
            reason="test",
        )

        lifecycle = zone_lifecycle(candles(), liquidity, [sweep])

        self.assertEqual(lifecycle.end_index, 4)
        self.assertEqual(lifecycle.state, "swept")
        self.assertFalse(lifecycle.is_active)

    def test_structure_segment_uses_matching_swing_not_a_fixed_backwards_width(self) -> None:
        event = StructureEvent(
            label="BOS",
            direction="bullish",
            index=5,
            timestamp="2026-01-01T01:15:00",
            price=104.0,
            broken_level=103.0,
            reason="test",
        )
        swings = [
            SwingPoint(kind="high", index=1, timestamp="2026-01-01T00:15:00", price=101.0),
            SwingPoint(kind="high", index=3, timestamp="2026-01-01T00:45:00", price=103.0),
        ]

        self.assertEqual(structure_origin_index(event, swings, candles()), 3)

    def test_display_policy_prefers_swing_structure_over_duplicate_internal_break(self) -> None:
        internal = StructureEvent(
            label="BOS",
            direction="bullish",
            index=5,
            timestamp="2026-01-01T01:15:00",
            price=104.0,
            broken_level=103.0,
            structure_scope="internal",
            reason="test",
        )
        swing = StructureEvent(
            label="CHoCH",
            direction="bullish",
            index=5,
            timestamp="2026-01-01T01:15:00",
            price=104.0,
            broken_level=103.0,
            structure_scope="swing",
            reason="test",
        )

        self.assertEqual(select_display_events([internal, swing]), [swing])

    def test_pass_plan_has_no_visual_entry_or_targets(self) -> None:
        plan = TradePlan(
            direction="bearish",
            verdict="Pass",
            entry_type="no_trade",
            entry_low=101.0,
            entry_high=102.0,
            invalidation=103.0,
            targets=[99.0],
            thesis="test",
        )

        self.assertFalse(has_actionable_plan(plan))
        self.assertEqual(plan_levels(plan), [])

    def test_watch_plan_keeps_only_real_plan_levels(self) -> None:
        plan = TradePlan(
            direction="bearish",
            verdict="Watch",
            entry_type="confirmation",
            entry_low=101.0,
            entry_high=102.0,
            invalidation=103.0,
            structural_invalidation=104.0,
            targets=[99.0],
            thesis="test",
        )

        self.assertTrue(has_actionable_plan(plan))
        self.assertEqual([level.label for level in plan_levels(plan)], ["Execution SL", "Structural invalidation", "Target 1"])


if __name__ == "__main__":
    unittest.main()
