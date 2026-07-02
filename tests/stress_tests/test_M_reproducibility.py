import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.data.schemas import Candle

def generate_complex_sequence() -> list[Candle]:
    base_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = []
    # Create 50 candles with varying highs and lows to trigger swings, breaks, and FVGs
    for i in range(50):
        # Introduce some volatility to create structure
        if i % 5 == 0:
            h = Decimal("110") + Decimal(i)
            l = Decimal("90") + Decimal(i)
            c = Decimal("105") + Decimal(i)
            o = Decimal("95") + Decimal(i)
        elif i % 5 == 2:
            h = Decimal("80") - Decimal(i)
            l = Decimal("60") - Decimal(i)
            c = Decimal("65") - Decimal(i)
            o = Decimal("75") - Decimal(i)
        else:
            h = Decimal("105")
            l = Decimal("95")
            c = Decimal("100")
            o = Decimal("100")
            
        candles.append(
            Candle(
                venue="BINANCE",
                instrument="BTCUSDT",
                timeframe="15m",
                open_time=base_time + timedelta(minutes=15 * i),
                close_time=base_time + timedelta(minutes=15 * (i + 1)),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=Decimal("1000"),
                trade_count=100,
                is_closed=True,
                is_complete=True,
                contains_gap=False
            )
        )
    return candles

def test_m1_bit_for_bit_reproducibility():
    """
    Test M1: Bit-for-bit Deterministic Rerun
    Run a complex history twice under the exact same configuration and decision timestamps.
    Hash the resulting serialized objects and assert they are identical bit-for-bit.
    """
    dt = datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc)
    candles = generate_complex_sequence()
    
    # Run 1
    engine1 = PerceptionEngineV2()
    snapshot1 = engine1.analyze(candles, dt)
    dump1 = snapshot1.model_dump_json()
    
    # Run 2
    engine2 = PerceptionEngineV2()
    snapshot2 = engine2.analyze(candles, dt)
    dump2 = snapshot2.model_dump_json()
    
    assert dump1 == dump2, "Non-deterministic state leakage detected between runs"
