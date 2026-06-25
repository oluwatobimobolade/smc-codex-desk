"""Truth-boundary tests: candle closure, availability, and quality gating.

These tests verify that no unclosed candle enters confirmed history under
any boundary condition.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.run_context import slice_history, dataframe_to_candles
from smc_desk.colleague.run_context import TIMEFRAME_DURATIONS


def _make_ohlcv(n_bars: int = 24, interval_minutes: int = 15) -> pd.DataFrame:
    """Create hourly bars starting at 2026-01-01 00:00 with given interval."""
    rows = []
    for i in range(n_bars):
        hour = (i * interval_minutes) // 60
        minute = (i * interval_minutes) % 60
        rows.append({
            "timestamp": f"2026-01-01 {hour:02d}:{minute:02d}:00",
            "open": 100.0 + i * 0.1,
            "high": 100.5 + i * 0.1,
            "low": 99.5 + i * 0.1,
            "close": 100.1 + i * 0.1,
            "volume": 1.0,
        })
    return pd.DataFrame(rows)


class CandleClosureBoundaryTests(unittest.TestCase):
    """Verify that only fully closed candles enter confirmed history."""

    def setUp(self) -> None:
        self.df = _make_ohlcv(n_bars=24)  # 00:00 .. 05:45

    def test_request_before_close_excludes_in_progress_candle(self) -> None:
        """At 00:07, the 00:00 candle (closes at 00:15) is excluded.

        Since no candle has closed yet, slice_history raises ValueError.
        """
        decision = pd.Timestamp("2026-01-01 00:07:00")
        with self.assertRaises(ValueError) as ctx:
            slice_history(self.df, decision)
        self.assertIn("before the first fully closed candle", str(ctx.exception))

    def test_request_at_close_includes_fully_closed_candle(self) -> None:
        """At 00:15, the 00:00 candle (closed at 00:15) is included."""
        decision = pd.Timestamp("2026-01-01 00:15:00")
        history, candle_open = slice_history(self.df, decision)
        # 00:00 closes at 00:15, so it is included.
        self.assertGreater(len(history), 0)
        self.assertEqual(pd.Timestamp(history["timestamp"].iloc[-1]), pd.Timestamp("2026-01-01 00:00:00"))

    def test_request_midway_excludes_latest(self) -> None:
        """At 00:30, the 00:15 candle (closes at 00:30) is included,
        00:00 is also included (closed at 00:15 <= 00:30).
        The 00:30 candle (closes 00:45) is NOT included."""
        decision = pd.Timestamp("2026-01-01 00:40:00")
        history, candle_open = slice_history(self.df, decision)
        # Last included is 00:15 (closes at 00:30 <= 00:40)
        self.assertEqual(candle_open, pd.Timestamp("2026-01-01 00:15:00"))

    def test_request_at_exact_close_second(self) -> None:
        """At exactly 00:30:00, the 00:15 candle is included (closed at 00:30)."""
        decision = pd.Timestamp("2026-01-01 00:30:00")
        history, candle_open = slice_history(self.df, decision)
        self.assertEqual(candle_open, pd.Timestamp("2026-01-01 00:15:00"))

    def test_request_one_microsecond_before_close(self) -> None:
        """At 00:29:59.999999, the 00:15 candle (close 00:30) is excluded."""
        decision = pd.Timestamp("2026-01-01 00:29:59.999999")
        history, candle_open = slice_history(self.df, decision)
        self.assertEqual(candle_open, pd.Timestamp("2026-01-01 00:00:00"))

    def test_multiple_bars_accumulate_correctly(self) -> None:
        """At 01:00, all bars from 00:00 to 00:45 are included (00:45 closes at 01:00)."""
        decision = pd.Timestamp("2026-01-01 01:00:00")
        history, candle_open = slice_history(self.df, decision)
        self.assertEqual(candle_open, pd.Timestamp("2026-01-01 00:45:00"))
        # Count: 00:00, 00:15, 00:30, 00:45 = 4 bars
        self.assertEqual(len(history), 4)


class CandleQualityTests(unittest.TestCase):
    """Verify that Candle quality metadata is computed, not hardcoded."""

    def test_historical_candles_are_closed_and_complete(self) -> None:
        df = _make_ohlcv(n_bars=12)
        candles = dataframe_to_candles(
            df, venue="TEST", instrument="UNKNOWN", timeframe="15m"
        )
        self.assertTrue(all(c.is_closed for c in candles))
        self.assertTrue(all(c.is_complete for c in candles))

    def test_no_gap_in_contiguous_data(self) -> None:
        df = _make_ohlcv(n_bars=12)
        candles = dataframe_to_candles(
            df, venue="TEST", instrument="UNKNOWN", timeframe="15m"
        )
        self.assertFalse(any(c.contains_gap for c in candles))

    def test_gap_detected_when_timestamps_skip(self) -> None:
        rows = [
            {"timestamp": "2026-01-01 00:00:00", "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.1, "volume": 1.0},
            {"timestamp": "2026-01-01 00:15:00", "open": 100.1, "high": 100.6, "low": 99.6, "close": 100.2, "volume": 1.0},
            # Gap: 30 minutes missing.
            {"timestamp": "2026-01-01 00:45:00", "open": 100.2, "high": 100.7, "low": 99.7, "close": 100.3, "volume": 1.0},
        ]
        df = pd.DataFrame(rows)
        candles = dataframe_to_candles(
            df, venue="TEST", instrument="UNKNOWN", timeframe="15m"
        )
        # First two bars are contiguous; third bar has a gap.
        self.assertFalse(candles[0].contains_gap)
        self.assertFalse(candles[1].contains_gap)
        self.assertTrue(candles[2].contains_gap)

    def test_live_reference_time_marks_unclosed(self) -> None:
        from datetime import datetime, timezone
        rows = [
            {"timestamp": "2026-01-01 00:00:00", "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.1, "volume": 1.0},
            # This bar would close at 00:30. Reference time is 00:20, so it's still forming.
            {"timestamp": "2026-01-01 00:15:00", "open": 100.1, "high": 100.6, "low": 99.6, "close": 100.2, "volume": 1.0},
        ]
        df = pd.DataFrame(rows)
        ref = datetime(2026, 1, 1, 0, 20, 0, tzinfo=timezone.utc)
        candles = dataframe_to_candles(
            df, venue="TEST", instrument="UNKNOWN", timeframe="15m",
            reference_time=ref,
        )
        # 00:00 closed at 00:15 <= 00:20
        self.assertTrue(candles[0].is_closed)
        # 00:15 closes at 00:30 > 00:20
        self.assertFalse(candles[1].is_closed)
        self.assertFalse(candles[1].is_complete)


if __name__ == "__main__":
    unittest.main()
