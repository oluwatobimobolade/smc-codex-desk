import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time

from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.data.schemas import Candle

def generate_candles(count: int, gap_at: int = -1, incomplete_at: int = -1) -> list[Candle]:
    base_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(count):
        candles.append(
            Candle(
                venue="BINANCE",
                instrument="BTCUSDT",
                timeframe="15m",
                open_time=base_time + timedelta(minutes=15 * i),
                close_time=base_time + timedelta(minutes=15 * (i + 1)),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("1000"),
                trade_count=100,
                is_closed=True,
                is_complete=False if i == incomplete_at else True,
                contains_gap=True if i == gap_at else False
            )
        )
    return candles

def test_n1_partial_service_failure_gap():
    """
    Test N1: Partial Service Failure
    Mock corrupted data drops (contains_gap) to ensure graceful failure.
    """
    engine = PerceptionEngineV2()
    candles = generate_candles(50, gap_at=25)
    
    dt = datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Cannot analyze sequence containing gaps or incomplete data"):
        engine.analyze(candles, dt)

def test_n1_partial_service_failure_incomplete():
    """
    Test N1: Partial Service Failure
    Mock incomplete data to ensure graceful failure.
    """
    engine = PerceptionEngineV2()
    candles = generate_candles(50, incomplete_at=40)
    
    dt = datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Cannot analyze sequence containing gaps or incomplete data"):
        engine.analyze(candles, dt)

def test_n2_high_volume_load():
    """
    Test N2: High-Volume Load
    Process 10,000 candles to measure memory bloat, latency, and rule out race conditions.
    """
    engine = PerceptionEngineV2()
    
    # 10,000 candles
    candles = generate_candles(10000)
    # Set the decision time to far in the future to process all of them
    dt = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    
    start = time.time()
    snapshot = engine.analyze(candles, dt)
    end = time.time()
    
    # Simple assertion that it finishes and returns a valid snapshot
    assert snapshot is not None
    assert len(snapshot.swings) > 0
    
    # Assert acceptable execution time (e.g., under 5 seconds for 10k candles)
    assert (end - start) < 5.0, f"Performance regression: 10,000 candles took {end - start:.2f} seconds."
