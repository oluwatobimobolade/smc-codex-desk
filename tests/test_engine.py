from __future__ import annotations

import unittest

import pandas as pd

from smc_desk.engine import build_trade_plan, detect_equal_levels, detect_structure_events
from smc_desk.models import StructureEvent, SwingPoint, Zone
from smc_desk.rules import RuleConfig


def candles(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(rows), freq="15min"),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": [1_000 for _ in rows],
        }
    )


class EngineTests(unittest.TestCase):
    def test_structure_break_requires_displacement(self) -> None:
        config = RuleConfig(pivot_window=2, displacement_body_factor=1.5)
        df = candles(
            [
                (100.00, 100.20, 99.90, 100.05),
                (100.05, 100.25, 99.95, 100.10),
                (100.10, 100.30, 100.00, 100.15),
                (100.15, 100.35, 100.05, 100.20),
                (100.20, 100.40, 100.10, 100.25),
                (104.90, 105.00, 104.80, 104.95),
                (105.04, 105.20, 104.90, 105.06),
                (105.10, 106.20, 105.00, 106.05),
            ]
        )
        swings = [SwingPoint(kind="high", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=105.0)]

        events = detect_structure_events(df, swings, config)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].index, 7)
        self.assertEqual(events[0].direction, "bullish")
        self.assertGreaterEqual(events[0].displacement_score, config.displacement_body_factor)

    def test_bullish_choch_requires_protected_high_not_internal_high(self) -> None:
        config = RuleConfig(pivot_window=2, displacement_body_factor=1.2)
        df = candles(
            [
                (105, 106, 104, 105),
                (105, 106, 104, 105),
                (106, 110, 105, 108),
                (108, 109, 99, 100),
                (100, 101, 95, 96),
                (96, 98, 95, 97),
                (97, 98, 95, 96),
                (100, 101, 89, 90),
                (94, 100, 93, 99),
                (99, 100, 93, 94),
                (94, 95, 90, 91),
                (91, 99, 91, 98),
                (94, 104, 93, 103),
                (101, 113, 100, 112),
            ]
        )
        swings = [
            SwingPoint(kind="high", index=2, timestamp=df.at[2, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=4, timestamp=df.at[4, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=8, timestamp=df.at[8, "timestamp"].isoformat(), price=100.0),
            SwingPoint(kind="low", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=90.0),
        ]

        events = detect_structure_events(df, swings, config)
        bullish_events = [event for event in events if event.direction == "bullish"]

        self.assertEqual(len(bullish_events), 1)
        self.assertEqual(bullish_events[0].label, "CHoCH")
        self.assertEqual(bullish_events[0].index, 13)
        self.assertEqual(bullish_events[0].broken_level, 110.0)

    def test_internal_choch_can_break_internal_high_for_entry_confirmation(self) -> None:
        config = RuleConfig(pivot_window=2, displacement_body_factor=1.2)
        df = candles(
            [
                (105, 106, 104, 105),
                (105, 106, 104, 105),
                (106, 110, 105, 108),
                (108, 109, 99, 100),
                (100, 101, 95, 96),
                (96, 98, 95, 97),
                (97, 98, 95, 96),
                (100, 101, 89, 90),
                (94, 100, 93, 99),
                (99, 100, 93, 94),
                (94, 95, 90, 91),
                (91, 99, 91, 98),
                (94, 104, 93, 103),
                (101, 113, 100, 112),
            ]
        )
        swings = [
            SwingPoint(kind="high", index=2, timestamp=df.at[2, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=4, timestamp=df.at[4, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=8, timestamp=df.at[8, "timestamp"].isoformat(), price=100.0),
            SwingPoint(kind="low", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=90.0),
        ]

        events = detect_structure_events(df, swings, config, structure_scope="internal")
        bullish_events = [event for event in events if event.direction == "bullish"]

        self.assertEqual(len(bullish_events), 1)
        self.assertEqual(bullish_events[0].label, "CHoCH")
        self.assertEqual(bullish_events[0].structure_scope, "internal")
        self.assertEqual(bullish_events[0].index, 12)
        self.assertEqual(bullish_events[0].broken_level, 100.0)

    def test_equal_levels_are_clustered_not_pairwise_spam(self) -> None:
        config = RuleConfig(equal_level_tolerance_pct=0.0015, equal_level_min_touches=2)
        swings = [
            SwingPoint(kind="high", index=3, timestamp="2026-01-01T00:45:00", price=100.00),
            SwingPoint(kind="high", index=9, timestamp="2026-01-01T02:15:00", price=100.05),
            SwingPoint(kind="high", index=15, timestamp="2026-01-01T03:45:00", price=100.08),
            SwingPoint(kind="low", index=6, timestamp="2026-01-01T01:30:00", price=95.00),
            SwingPoint(kind="low", index=12, timestamp="2026-01-01T03:00:00", price=94.90),
        ]

        zones = detect_equal_levels(swings, config)
        equal_highs = [zone for zone in zones if zone.label == "Equal Highs"]

        self.assertEqual(len(equal_highs), 1)
        self.assertEqual(equal_highs[0].touched_count, 3)

    def test_trade_plan_refuses_missing_liquidity_sweep(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0)
        df = candles([(100, 101, 99, 100) for _ in range(30)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=98.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=108.0),
        ]
        zones = [
            Zone(
                label="Bearish FVG",
                kind="fvg",
                direction="bearish",
                low=105.0,
                high=106.0,
                start_index=12,
                end_index=14,
                score=0.82,
                confidence=0.82,
                status="fresh",
                reason="test zone",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=95.0,
                high=95.1,
                score=0.8,
                confidence=0.8,
                reason="target",
            ),
        ]
        events = [
            StructureEvent(
                label="BOS",
                direction="bearish",
                index=28,
                timestamp=df.at[28, "timestamp"].isoformat(),
                price=99.0,
                broken_level=100.0,
                displacement_score=2.0,
                strength="valid",
                reason="test break",
            )
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        self.assertEqual(plan.verdict, "Watch")
        self.assertEqual(plan.risk_pct, 0.0)
        self.assertFalse(plan.checklist["liquidity_sweep"])

    def test_trade_plan_executes_only_when_full_checklist_passes(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0)
        df = candles([(105.0, 106.0, 104.5, 105.5) for _ in range(30)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=98.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=108.0),
        ]
        zones = [
            Zone(
                label="Bearish Order Block",
                kind="order_block",
                direction="bearish",
                low=105.0,
                high=106.0,
                start_index=20,
                end_index=21,
                score=0.86,
                confidence=0.86,
                status="fresh",
                reason="test poi",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=95.0,
                high=95.1,
                score=0.8,
                confidence=0.8,
                reason="target",
            ),
        ]
        events = [
            StructureEvent(
                label="Liquidity Sweep",
                direction="bearish",
                index=27,
                timestamp=df.at[27, "timestamp"].isoformat(),
                price=105.5,
                swept_level=107.0,
                displacement_score=1.4,
                strength="valid",
                reason="test sweep",
            ),
            StructureEvent(
                label="CHoCH",
                direction="bearish",
                index=28,
                timestamp=df.at[28, "timestamp"].isoformat(),
                price=104.0,
                broken_level=104.5,
                displacement_score=2.4,
                strength="strong",
                reason="test choch",
            ),
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        self.assertEqual(plan.verdict, "Execute")
        self.assertIn(plan.setup_grade, {"A", "A+"})
        self.assertGreaterEqual(plan.risk_reward or 0.0, config.risk_reward_floor)
        self.assertTrue(all(plan.checklist.values()))

    def test_trade_plan_widens_tight_structural_stop_with_atr_buffer(self) -> None:
        config = RuleConfig(risk_reward_floor=1.0, stop_buffer_atr_mult=0.75)
        df = candles([(100.0, 102.0, 100.0, 101.0) for _ in range(30)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=90.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=96.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=108.0),
        ]
        zones = [
            Zone(
                label="Bearish FVG",
                kind="fvg",
                direction="bearish",
                low=105.0,
                high=106.0,
                start_index=20,
                end_index=21,
                score=0.86,
                confidence=0.86,
                status="fresh",
                reason="test poi",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=90.0,
                high=90.1,
                score=0.8,
                confidence=0.8,
                reason="target",
            ),
        ]

        plan = build_trade_plan(df, swings, zones, [], config, bias_hint="bearish")

        self.assertEqual(plan.stop_quality, "volatility_adjusted")
        self.assertEqual(plan.invalidation, plan.execution_invalidation)
        self.assertGreater(plan.invalidation or 0.0, plan.structural_invalidation or 0.0)
        self.assertAlmostEqual(plan.structural_invalidation or 0.0, 106.106, places=3)
        self.assertGreaterEqual(plan.stop_buffer_atr or 0.0, config.stop_buffer_atr_mult)
        self.assertTrue(plan.checklist["stop_has_volatility_buffer"])
        self.assertTrue(any("Execution stop widened" in warning for warning in plan.warnings))

    def test_trade_plan_default_rejects_partial_poi(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0)
        df = candles([(105.0, 106.0, 104.5, 105.5) for _ in range(30)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=98.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=108.0),
        ]
        zones = [
            Zone(
                label="Bearish Order Block",
                kind="order_block",
                direction="bearish",
                low=105.0,
                high=106.0,
                start_index=20,
                end_index=21,
                score=0.86,
                confidence=0.86,
                status="partial",
                reason="test partially mitigated poi",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=95.0,
                high=95.1,
                score=0.8,
                confidence=0.8,
                reason="target",
            ),
        ]
        events = [
            StructureEvent(
                label="Liquidity Sweep",
                direction="bearish",
                index=27,
                timestamp=df.at[27, "timestamp"].isoformat(),
                price=105.5,
                swept_level=107.0,
                displacement_score=1.4,
                strength="valid",
                reason="test sweep",
            ),
            StructureEvent(
                label="CHoCH",
                direction="bearish",
                index=28,
                timestamp=df.at[28, "timestamp"].isoformat(),
                price=104.0,
                broken_level=104.5,
                displacement_score=2.4,
                strength="strong",
                reason="test choch",
            ),
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        self.assertIsNone(plan.selected_poi)
        self.assertFalse(plan.checklist["fresh_or_partial_poi"])
        self.assertEqual(plan.verdict, "Pass")

    def test_trade_plan_can_opt_into_partial_poi_research(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0, require_fresh_poi=False)
        df = candles([(105.0, 106.0, 104.5, 105.5) for _ in range(30)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=98.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=108.0),
        ]
        zones = [
            Zone(
                label="Bearish Order Block",
                kind="order_block",
                direction="bearish",
                low=105.0,
                high=106.0,
                start_index=20,
                end_index=21,
                score=0.86,
                confidence=0.86,
                status="partial",
                reason="test partially mitigated poi",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=95.0,
                high=95.1,
                score=0.8,
                confidence=0.8,
                reason="target",
            ),
        ]
        events = [
            StructureEvent(
                label="Liquidity Sweep",
                direction="bearish",
                index=27,
                timestamp=df.at[27, "timestamp"].isoformat(),
                price=105.5,
                swept_level=107.0,
                displacement_score=1.4,
                strength="valid",
                reason="test sweep",
            ),
            StructureEvent(
                label="CHoCH",
                direction="bearish",
                index=28,
                timestamp=df.at[28, "timestamp"].isoformat(),
                price=104.0,
                broken_level=104.5,
                displacement_score=2.4,
                strength="strong",
                reason="test choch",
            ),
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        self.assertIsNotNone(plan.selected_poi)
        self.assertEqual(plan.selected_poi.status if plan.selected_poi else None, "partial")

    def test_trade_plan_can_restrict_poi_kinds_for_research(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0, require_fresh_poi=False, allowed_poi_kinds=["fvg"])
        df = candles([(105.0, 106.0, 104.5, 105.5) for _ in range(30)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=98.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=108.0),
        ]
        zones = [
            Zone(
                label="Bearish Order Block",
                kind="order_block",
                direction="bearish",
                low=105.0,
                high=106.0,
                start_index=20,
                end_index=21,
                score=0.99,
                confidence=0.99,
                status="partial",
                reason="higher score but disallowed by research config",
            ),
            Zone(
                label="Bearish FVG",
                kind="fvg",
                direction="bearish",
                low=105.1,
                high=105.9,
                start_index=22,
                end_index=24,
                score=0.70,
                confidence=0.70,
                status="partial",
                reason="allowed research POI kind",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=95.0,
                high=95.1,
                score=0.8,
                confidence=0.8,
                reason="target",
            ),
        ]
        events = [
            StructureEvent(
                label="Liquidity Sweep",
                direction="bearish",
                index=27,
                timestamp=df.at[27, "timestamp"].isoformat(),
                price=105.5,
                swept_level=107.0,
                displacement_score=1.4,
                strength="valid",
                reason="test sweep",
            ),
            StructureEvent(
                label="CHoCH",
                direction="bearish",
                index=28,
                timestamp=df.at[28, "timestamp"].isoformat(),
                price=104.0,
                broken_level=104.5,
                displacement_score=2.4,
                strength="strong",
                reason="test choch",
            ),
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        self.assertIsNotNone(plan.selected_poi)
        self.assertEqual(plan.selected_poi.kind if plan.selected_poi else None, "fvg")


if __name__ == "__main__":
    unittest.main()
