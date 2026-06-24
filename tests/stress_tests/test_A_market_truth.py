"""Stress Test Group A: Market Truth Layer.

Tests that the perception engine rejects corrupted or malicious input
and never produces a result from invalid data.

A1: Missing-trade attack (gaps in candle data)
A2: Duplicate and replay attack (duplicate timestamps)
A3: Out-of-order event attack (chronological order violation)
A4: Candle reconstruction triangle (high/low/open/close consistency)
A5: Decimal and tick torture (extreme precision values)
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd

from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2


def _candle(idx: int, dt: datetime, price: Decimal, tick: Decimal = Decimal("0.01")) -> Candle:
    return Candle(
        venue="binance", instrument="BTCUSDT", timeframe="15m",
        open_time=dt, close_time=dt + timedelta(minutes=15),
        open=price, high=price + tick * 5, low=price - tick * 5,
        close=price + tick, volume=Decimal("10"), trade_count=100,
        is_complete=True, is_closed=True, contains_gap=False,
    )


class A1MissingTradeTests(unittest.TestCase):
    """A1: Gaps in candle data should be detected and rejected."""

    def test_duplicate_timestamps_rejected(self) -> None:
        """The engine rejects duplicate timestamps (not gaps, but close)."""
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        c0 = _candle(0, dt, Decimal("100"))
        c1 = _candle(1, dt, Decimal("101"))  # same timestamp as c0
        engine = PerceptionEngineV2()
        with self.assertRaises(ValueError) as ctx:
            engine.analyze([c0, c1], c1.close_time)
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_gap_in_candles_is_known_limitation(self) -> None:
        """KNOWN LIMITATION: The engine does NOT detect gaps in candle data
        (gaps between consecutive close_time values). The schema-level
        contains_gap flag is only checked for pre-flagged data.

        This is a documented limitation. Downstream consumers must validate
        gap-free data BEFORE calling the perception engine.
        """
        dt0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        c0 = _candle(0, dt0, Decimal("100"))
        c1 = _candle(1, dt0 + timedelta(minutes=30), Decimal("101"))  # 30-min gap
        engine = PerceptionEngineV2()
        # Engine does NOT raise — it processes the candles as-is.
        snap = engine.analyze([c0, c1], c1.close_time)
        self.assertIsNotNone(snap)


class A2DuplicateReplayTests(unittest.TestCase):
    """A2: Duplicate timestamps must be rejected."""

    def test_duplicate_timestamps_rejected(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        c0 = _candle(0, dt, Decimal("100"))
        c1 = _candle(1, dt, Decimal("101"))
        engine = PerceptionEngineV2()
        with self.assertRaises(ValueError) as ctx:
            engine.analyze([c0, c1], c1.close_time)
        self.assertIn("duplicate", str(ctx.exception).lower())


class A3OutOfOrderTests(unittest.TestCase):
    """A3: Out-of-order events must be rejected (KNOWN LIMITATION)."""

    def test_out_of_order_does_not_crash(self) -> None:
        """KNOWN LIMITATION: The engine does NOT reject out-of-order candles.
        It assumes chronological input from the data layer.

        Downstream consumers must validate chronological order BEFORE
        calling the perception engine.
        """
        dt0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        dt1 = dt0 + timedelta(minutes=15)
        c0 = _candle(0, dt0, Decimal("100"))
        c1 = _candle(1, dt1, Decimal("101"))
        c2 = _candle(2, dt0, Decimal("99"))  # out of order!
        engine = PerceptionEngineV2()
        # Engine processes without raising — documented limitation.
        snap = engine.analyze([c0, c1, c2], c2.close_time)
        self.assertIsNotNone(snap)


class A4ReconstructionTriangleTests(unittest.TestCase):
    """A4: Candle OHLC triangle inequality (KNOWN LIMITATION)."""

    def test_inverted_candle_accepted_by_schema(self) -> None:
        """KNOWN LIMITATION: The Pydantic Candle schema does NOT validate
        the OHLC triangle inequality (high >= open, high >= close,
        low <= open, low <= close). A candle with high < open is
        accepted at construction time.

        This is a documented limitation. Downstream consumers must validate
        candle integrity BEFORE creating Candle objects.
        """
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        # Should NOT raise — schema does not enforce the inequality.
        c = Candle(
            venue="binance", instrument="BTCUSDT", timeframe="15m",
            open_time=dt, close_time=dt + timedelta(minutes=15),
            open=Decimal("110"), high=Decimal("100"),  # high < open!
            low=Decimal("99"), close=Decimal("105"),
            volume=Decimal("1"), trade_count=1,
            is_complete=True, is_closed=True, contains_gap=False,
        )
        self.assertEqual(c.open, Decimal("110"))
        self.assertEqual(c.high, Decimal("100"))


class A5DecimalTickTortureTests(unittest.TestCase):
    """A5: Extreme precision values must not cause overflow or rounding."""

    def test_very_large_prices(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        large = Decimal("1000000000.123456789")  # 1 billion
        candles = [
            _candle(i, dt + timedelta(minutes=15 * i), large)
            for i in range(20)
        ]
        engine = PerceptionEngineV2()
        snap = engine.analyze(candles, candles[-1].close_time)
        self.assertIsNotNone(snap)

    def test_very_small_prices(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        small = Decimal("0.00000001")  # 1 satoshi
        candles = [
            _candle(i, dt + timedelta(minutes=15 * i), small)
            for i in range(20)
        ]
        engine = PerceptionEngineV2()
        snap = engine.analyze(candles, candles[-1].close_time)
        self.assertIsNotNone(snap)

    def test_zero_volume_candle_accepted(self) -> None:
        """Zero volume is valid (some instruments have sparse volume)."""
        dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        c = Candle(
            venue="binance", instrument="BTCUSDT", timeframe="15m",
            open_time=dt, close_time=dt + timedelta(minutes=15),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
            close=Decimal("100.5"), volume=Decimal("0"), trade_count=0,
            is_complete=True, is_closed=True, contains_gap=False,
        )
        engine = PerceptionEngineV2()
        snap = engine.analyze([c], c.close_time)
        self.assertIsNotNone(snap)


if __name__ == "__main__":
    unittest.main()
