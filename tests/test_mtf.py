from __future__ import annotations

import unittest

import pandas as pd

from smc_desk.engine import build_trade_plan
from smc_desk.models import HigherTimeframePoi, StructureEvent, SwingPoint, Zone
from smc_desk.mtf import (
    HtfContext,
    MtfSnapshot,
    build_mtf_snapshot,
    derive_htf_consensus_bias,
    precompute_htf_series,
    resample_ohlcv,
    select_htf_poi,
    slice_precomputed_htf,
    snapshot_to_dict,
)
from smc_desk.rules import RuleConfig


def candles(rows: list[tuple[float, float, float, float]], freq: str = "15min") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(rows), freq=freq),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": [1_000 for _ in rows],
        }
    )


def snapshot_dict(one_hour: str, four_hour: str, daily: str) -> dict:
    return {
        "1h": {"bias": one_hour},
        "4h": {"bias": four_hour},
        "1d": {"bias": daily},
    }


class HtfConsensusBiasTests(unittest.TestCase):
    def test_1h_and_4h_agreement_with_neutral_daily_is_valid_bias(self) -> None:
        self.assertEqual(derive_htf_consensus_bias(snapshot_dict("bearish", "bearish", "neutral")), "bearish")

    def test_1h_alone_cannot_drive_execution_bias(self) -> None:
        self.assertEqual(derive_htf_consensus_bias(snapshot_dict("bullish", "bearish", "neutral")), "neutral")

    def test_daily_opposition_blocks_1h_4h_agreement(self) -> None:
        self.assertEqual(derive_htf_consensus_bias(snapshot_dict("bullish", "bullish", "bearish")), "neutral")

    def test_snapshot_exposes_strict_execution_consensus_not_directional_plurality(self) -> None:
        snapshot = MtfSnapshot(
            decision_time=pd.Timestamp("2026-01-02 12:00:00"),
            bars_visible_15m=300,
            one_hour=HtfContext("1h", 40, 100.0, "bullish", None, None, None, "bullish"),
            four_hour=HtfContext("4h", 40, 100.0, "bearish", None, None, None, "bearish"),
            daily=HtfContext("1d", 40, 100.0, "neutral", None, None, None, "neutral"),
            alignment="bullish",
            agreement_count=1,
            total_count=3,
            agreement_ratio=0.3333,
        )
        self.assertEqual(snapshot_to_dict(snapshot)["execution_consensus"], "neutral")


class HtfPoiWatchTests(unittest.TestCase):
    def _context(self, timeframe: str, bias: str, zones: list[Zone] | None = None) -> HtfContext:
        return HtfContext(
            timeframe=timeframe,
            candle_count=40,
            last_close=104.0,
            bias=bias,  # type: ignore[arg-type]
            last_structure_label="BOS",
            last_structure_direction=bias,
            last_structure_index=35,
            inferred_trend=bias,
            atr=2.0,
            poi_candidates=zones or [],
        )

    def _snapshot(self, zone: Zone) -> MtfSnapshot:
        return MtfSnapshot(
            decision_time=pd.Timestamp("2026-01-02 12:00:00"),
            bars_visible_15m=300,
            one_hour=self._context("1h", "bearish", [zone]),
            four_hour=self._context("4h", "bearish"),
            daily=self._context("1d", "neutral"),
            alignment="bearish",
            agreement_count=2,
            total_count=3,
            agreement_ratio=0.6667,
        )

    def _bearish_zone(self) -> Zone:
        return Zone(
            label="Bearish Order Block",
            kind="order_block",
            direction="bearish",
            low=105.0,
            high=106.0,
            start_index=32,
            end_index=35,
            score=0.84,
            confidence=0.84,
            status="fresh",
            reason="test HTF POI",
        )

    def test_approaching_aligned_htf_poi_is_selected_for_monitoring(self) -> None:
        poi = select_htf_poi(
            self._snapshot(self._bearish_zone()),
            current_price=104.0,
            config=RuleConfig(htf_poi_watch_distance_atr=1.5, htf_approach_lookback_bars=4),
            recent_15m_closes=pd.Series([102.5, 102.8, 103.0, 103.4, 104.0]),
        )

        self.assertIsNotNone(poi)
        assert poi is not None
        self.assertEqual(poi.timeframe, "1h")
        self.assertEqual(poi.state, "approaching")
        self.assertTrue(poi.approach_confirmed)
        self.assertEqual(poi.distance_atr, 0.5)

    def test_distant_or_non_approaching_htf_poi_stays_mapped(self) -> None:
        poi = select_htf_poi(
            self._snapshot(self._bearish_zone()),
            current_price=100.0,
            config=RuleConfig(htf_poi_watch_distance_atr=1.5),
            recent_15m_closes=pd.Series([99.0, 99.2, 99.4, 99.6, 100.0]),
        )

        self.assertIsNotNone(poi)
        assert poi is not None
        self.assertEqual(poi.state, "mapped")

    def test_htf_poi_watch_does_not_manufacture_an_executable_trade(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0)
        df = candles([(100.0, 101.0, 99.0, 100.0) for _ in range(40)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
        ]
        htf_poi = HigherTimeframePoi(
            timeframe="1h",
            zone=self._bearish_zone(),
            state="approaching",
            distance_atr=0.5,
            age_bars=4,
            rank=0.9,
            approach_confirmed=True,
        )

        plan = build_trade_plan(df, swings, [], [], config, bias_hint="bearish", htf_poi=htf_poi)

        self.assertEqual(plan.verdict, "Watch HTF POI")
        self.assertEqual(plan.risk_pct, 0.0)
        self.assertIsNone(plan.entry_low)
        self.assertIsNone(plan.entry_high)
        self.assertIsNone(plan.invalidation)
        self.assertEqual(plan.targets, [])
        self.assertEqual(plan.selected_htf_poi, htf_poi)

    def test_mapped_htf_poi_does_not_override_a_pass(self) -> None:
        config = RuleConfig(risk_reward_floor=3.0)
        df = candles([(100.0, 101.0, 99.0, 100.0) for _ in range(40)])
        swings = [
            SwingPoint(kind="low", index=5, timestamp=df.at[5, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=10, timestamp=df.at[10, "timestamp"].isoformat(), price=110.0),
        ]
        htf_poi = HigherTimeframePoi(
            timeframe="1h",
            zone=self._bearish_zone(),
            state="mapped",
            distance_atr=3.0,
            age_bars=4,
            rank=0.8,
        )

        plan = build_trade_plan(df, swings, [], [], config, bias_hint="bearish", htf_poi=htf_poi)

        self.assertEqual(plan.verdict, "Pass")


class MtfLeakageTests(unittest.TestCase):
    """Verify that no HTF candle visible at decision time has a close time
    after the decision timestamp. This is the core no-leakage guarantee."""

    def test_resample_drops_all_in_progress_htf_candles(self) -> None:
        rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
        df = candles(rows, freq="15min")
        decision_time = pd.Timestamp(df.at[80, "timestamp"])

        for tf, duration in [("1h", pd.Timedelta("1h")), ("4h", pd.Timedelta("4h")), ("1d", pd.Timedelta("1D"))]:
            htf = resample_ohlcv(df, tf, decision_time)
            if htf.empty:
                continue
            timestamps = pd.to_datetime(htf["timestamp"])
            close_times = timestamps + duration
            self.assertTrue(
                (close_times <= decision_time).all(),
                f"{tf}: found HTF candle with close time > decision_time — future leakage!",
            )

    def test_precomputed_slice_matches_direct_resample(self) -> None:
        rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
        df = candles(rows, freq="15min")
        precomputed = precompute_htf_series(df)
        decision_time = pd.Timestamp(df.at[100, "timestamp"])

        for tf in ("1h", "4h", "1d"):
            sliced = slice_precomputed_htf(precomputed[tf], tf, decision_time)
            direct = resample_ohlcv(df, tf, decision_time)
            self.assertEqual(len(sliced), len(direct), f"{tf}: precomputed slice and direct resample disagree")
            if not sliced.empty:
                self.assertEqual(
                    sliced["timestamp"].iloc[-1],
                    direct["timestamp"].iloc[-1],
                    f"{tf}: last HTF candle timestamp differs",
                )

    def test_snapshot_htf_candles_all_closed_before_decision(self) -> None:
        rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(300)]
        df = candles(rows, freq="15min")
        cfg = RuleConfig(lookback_bars=200)
        decision_time = pd.Timestamp(df.at[150, "timestamp"])
        precomputed = precompute_htf_series(df)
        snap = build_mtf_snapshot(df, decision_time, cfg, precomputed=precomputed)

        for tf, duration in [("1h", pd.Timedelta("1h")), ("4h", pd.Timedelta("4h")), ("1d", pd.Timedelta("1D"))]:
            htf = slice_precomputed_htf(precomputed[tf], tf, decision_time)
            if htf.empty:
                continue
            close_times = pd.to_datetime(htf["timestamp"]) + duration
            self.assertTrue(
                (close_times <= decision_time).all(),
                f"{tf}: snapshot includes a HTF candle that closes after decision time",
            )

    def test_decision_at_htf_boundary_excludes_current_htf_candle(self) -> None:
        """If decision time is exactly at a 1H boundary (e.g. 01:00), the
        1H candle that closes at 01:00 should be visible, but the next one
        (closing at 02:00) should not."""
        rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
        df = candles(rows, freq="15min")
        # 15m candle at index 4 is at 01:00 — a 1H boundary
        decision_time = pd.Timestamp(df.at[4, "timestamp"])
        htf_1h = resample_ohlcv(df, "1h", decision_time)
        if not htf_1h.empty:
            last_close = pd.to_datetime(htf_1h["timestamp"].iloc[-1]) + pd.Timedelta("1h")
            self.assertLessEqual(last_close, decision_time)


class EngineVerdictTests(unittest.TestCase):
    def test_watch_retrace_when_only_price_at_poi_is_missing(self) -> None:
        """Watch Retrace = everything passes except price is not yet at the POI."""
        config = RuleConfig(risk_reward_floor=3.0)
        # 60 candles, all at 95.0 — price is far below the POI (112-114)
        df = candles([(94.5, 95.5, 94.0, 95.0) for _ in range(60)])

        # Swings: range from 90 to 120, midpoint = 105
        swings = [
            SwingPoint(kind="low", index=2, timestamp=df.at[2, "timestamp"].isoformat(), price=90.0),
            SwingPoint(kind="high", index=8, timestamp=df.at[8, "timestamp"].isoformat(), price=120.0),
            SwingPoint(kind="low", index=15, timestamp=df.at[15, "timestamp"].isoformat(), price=95.0),
            SwingPoint(kind="high", index=22, timestamp=df.at[22, "timestamp"].isoformat(), price=118.0),
        ]

        # Bearish OB at 112-114 (in premium, above midpoint of 105)
        zones = [
            Zone(
                label="Bearish Order Block",
                kind="order_block",
                direction="bearish",
                low=112.0,
                high=114.0,
                start_index=20,
                end_index=21,
                score=0.86,
                confidence=0.86,
                status="fresh",
                reason="test poi in premium",
            ),
            Zone(
                label="Equal Lows",
                kind="liquidity",
                direction="bullish",
                low=90.0,
                high=90.1,
                score=0.8,
                confidence=0.8,
                reason="liquidity target",
            ),
        ]

        events = [
            # Liquidity sweep (bearish) at index 57 — swept buy-side at 116
            StructureEvent(
                label="Liquidity Sweep",
                direction="bearish",
                index=57,
                timestamp=df.at[57, "timestamp"].isoformat(),
                price=115.5,
                swept_level=116.0,
                displacement_score=1.4,
                strength="valid",
                reason="test sweep",
            ),
            # CHoCH (bearish) at index 58 — broke structure low at 108
            StructureEvent(
                label="CHoCH",
                direction="bearish",
                index=58,
                timestamp=df.at[58, "timestamp"].isoformat(),
                price=107.0,
                broken_level=108.0,
                displacement_score=2.4,
                strength="strong",
                reason="test choch",
            ),
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        # The only missing check should be price_at_or_near_poi
        missing = [k for k, v in plan.checklist.items() if not v]
        self.assertEqual(missing, ["price_at_or_near_poi"], f"Expected only price_at_or_near_poi missing, got: {missing}")

        self.assertEqual(plan.verdict, "Watch Retrace")
        self.assertEqual(plan.setup_grade, "B")
        self.assertEqual(plan.risk_pct, 0.0)

    def test_watch_when_sweep_missing(self) -> None:
        """When liquidity_sweep is missing (not just price), verdict should be Watch, not Watch Retrace."""
        config = RuleConfig(risk_reward_floor=3.0)
        df = candles([(104.5, 106.0, 104.0, 105.5) for _ in range(60)])
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
                index=55,
                timestamp=df.at[55, "timestamp"].isoformat(),
                price=99.0,
                broken_level=100.0,
                displacement_score=2.0,
                strength="valid",
                reason="test break",
            )
        ]

        plan = build_trade_plan(df, swings, zones, events, config, bias_hint="bearish")

        self.assertEqual(plan.verdict, "Watch")
        self.assertFalse(plan.checklist["liquidity_sweep"])


class MtfRowContentTests(unittest.TestCase):
    """Verify that HTF candles actually contain the correct 15m rows,
    not just that they close before decision time."""

    def test_1h_candle_contains_exactly_four_15m_candles(self) -> None:
        """A 1H candle labeled 00:00 should contain 15m candles at
        00:00, 00:15, 00:30, 00:45 — all four."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=8, freq="15min"),
                "open":  [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
                "high":  [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5],
                "low":   [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
                "close": [100.2, 101.2, 102.2, 103.2, 104.2, 105.2, 106.2, 107.2],
                "volume": [1.0] * 8,
            }
        )
        precomputed = precompute_htf_series(df)
        htf_1h = precomputed["1h"]

        first_hour = htf_1h[htf_1h["timestamp"] == pd.Timestamp("2026-01-01 00:00:00")]
        self.assertEqual(len(first_hour), 1)
        row = first_hour.iloc[0]
        # Open should be the FIRST 15m candle (00:00) = 100.0
        self.assertEqual(row["open"], 100.0)
        # Close should be the LAST 15m candle in bucket (00:45) = 103.2
        self.assertEqual(row["close"], 103.2)
        # High should be the max of all four = 103.5
        self.assertEqual(row["high"], 103.5)
        # Low should be the min of all four = 99.5
        self.assertEqual(row["low"], 99.5)

        second_hour = htf_1h[htf_1h["timestamp"] == pd.Timestamp("2026-01-01 01:00:00")]
        self.assertEqual(len(second_hour), 1)
        row2 = second_hour.iloc[0]
        self.assertEqual(row2["open"], 104.0)
        self.assertEqual(row2["close"], 107.2)
        self.assertEqual(row2["high"], 107.5)
        self.assertEqual(row2["low"], 103.5)


if __name__ == "__main__":
    unittest.main()
