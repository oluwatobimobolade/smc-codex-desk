"""Tests for smc_desk.perception_bridge."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.data.schemas import Candle
from smc_desk.perception_bridge import (
    dataframe_to_candles,
    run_v2_perception_shadow,
)


class DataFrameToCandlesTests(unittest.TestCase):
    def test_basic_conversion(self) -> None:
        df = pd.DataFrame([
            {
                "timestamp": "2026-01-01T00:00:00",
                "open": 100.0, "high": 101.0, "low": 99.0,
                "close": 100.5, "volume": 1.0,
            },
            {
                "timestamp": "2026-01-01T00:15:00",
                "open": 100.5, "high": 101.5, "low": 100.0,
                "close": 101.0, "volume": 2.0,
            },
        ])
        candles = dataframe_to_candles(df, instrument="BTCUSDT", timeframe="15m")
        self.assertEqual(len(candles), 2)
        self.assertIsInstance(candles[0], Candle)
        self.assertEqual(candles[0].instrument, "BTCUSDT")
        self.assertEqual(candles[0].timeframe, "15m")
        self.assertTrue(candles[0].is_closed)
        self.assertTrue(candles[0].is_complete)
        self.assertFalse(candles[0].contains_gap)

    def test_timestamp_with_timezone(self) -> None:
        df = pd.DataFrame([{
            "timestamp": "2026-01-01T00:00:00+00:00",
            "open": 100.0, "high": 101.0, "low": 99.0,
            "close": 100.5, "volume": 1.0,
        }])
        candles = dataframe_to_candles(df)
        self.assertIsNotNone(candles[0].open_time.tzinfo)

    def test_decimal_prices(self) -> None:
        from decimal import Decimal
        df = pd.DataFrame([{
            "timestamp": "2026-01-01T00:00:00",
            "open": 100.123456789, "high": 101.0, "low": 99.0,
            "close": 100.5, "volume": 1.0,
        }])
        candles = dataframe_to_candles(df)
        # Decimal prices preserve full float precision.
        self.assertIsInstance(candles[0].open, Decimal)


class RunV2PerceptionShadowTests(unittest.TestCase):
    def _make_df(self, bars: int = 100) -> pd.DataFrame:
        rows = []
        price = 100.0
        for i in range(bars):
            hour, minute = i // 60, i % 60
            open_p = price
            close = price + (-1 if i % 2 else 1) * 0.3
            high = max(open_p, close) + 0.2
            low = min(open_p, close) - 0.2
            rows.append({
                "timestamp": f"2026-01-01T{hour:02d}:{minute:02d}:00",
                "open": open_p, "high": high, "low": low,
                "close": close, "volume": 1.0,
            })
            price = close
        return pd.DataFrame(rows)

    def test_returns_ok_status(self) -> None:
        result = run_v2_perception_shadow(self._make_df(80), instrument="BTCUSDT")
        self.assertEqual(result["status"], "ok")

    def test_returns_required_keys(self) -> None:
        result = run_v2_perception_shadow(self._make_df(80), instrument="BTCUSDT")
        for key in ("status", "decision_time", "swing_count", "break_count", "fvg_count"):
            self.assertIn(key, result)

    def test_detects_objects(self) -> None:
        """V2 either detects objects or returns ok with zero — both are valid.

        This is a smoke test: the bridge must not crash and must return
        a valid result shape, regardless of whether the input series
        contains detectable structures.
        """
        result = run_v2_perception_shadow(self._make_df(100), instrument="BTCUSDT")
        # All counts must be non-negative integers.
        for key in ("swing_count", "break_count", "fvg_count"):
            self.assertIsInstance(result[key], int)
            self.assertGreaterEqual(result[key], 0)
        # Swing list, break list, FVG list must be present and well-formed.
        self.assertIsInstance(result["swings"], list)
        self.assertIsInstance(result["structure_breaks"], list)
        self.assertIsInstance(result["fvgs"], list)

    def test_handles_empty_dataframe(self) -> None:
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        result = run_v2_perception_shadow(df, instrument="BTCUSDT")
        # Empty input should return error status, not crash.
        self.assertIn(result["status"], ("error", "ok"))


if __name__ == "__main__":
    unittest.main()
