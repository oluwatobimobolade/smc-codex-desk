import pytest
from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd
from pathlib import Path

from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2

def create_valid_candle(idx: int, t: str) -> Candle:
    return Candle(
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
        close_time=datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("102"),
        volume=Decimal("1000"),
        trade_count=100,
        is_closed=True,
        is_complete=True,
        contains_gap=False
    )

def test_missing_event_attack_blocks_perception():
    """Missing-sequence detection: 100%. Silent continuation after a material gap: 0"""
    engine = PerceptionEngineV2()
    
    # Create a sequence with a gap
    c1 = create_valid_candle(1, "2026-06-24T00:00:00")
    c2 = create_valid_candle(2, "2026-06-24T00:15:00")
    c2.contains_gap = True
    c2.is_complete = False
    
    with pytest.raises(ValueError, match="Cannot analyze sequence containing gaps or incomplete data"):
        engine.analyze([c1, c2], decision_time=datetime.fromisoformat("2026-06-24T00:15:00").replace(tzinfo=timezone.utc))

def test_duplicate_event_attack_blocks_perception():
    """Duplicate-induced OHLCV changes: 0"""
    engine = PerceptionEngineV2()
    
    c1 = create_valid_candle(1, "2026-06-24T00:00:00")
    c2 = create_valid_candle(2, "2026-06-24T00:00:00") # Duplicate timestamp
    
    with pytest.raises(ValueError, match="Duplicate timestamps detected in candle sequence"):
        engine.analyze([c1, c2], decision_time=datetime.fromisoformat("2026-06-24T00:00:00").replace(tzinfo=timezone.utc))

def test_out_of_order_attack_blocks_perception():
    engine = PerceptionEngineV2()
    
    c1 = create_valid_candle(1, "2026-06-24T00:15:00")
    c2 = create_valid_candle(2, "2026-06-24T00:00:00") # Out of order
    
    with pytest.raises(ValueError, match="Candle sequence is not strictly chronologically ordered"):
        engine.analyze([c1, c2], decision_time=datetime.fromisoformat("2026-06-24T00:15:00").replace(tzinfo=timezone.utc))

def test_future_timestamp_attack_ignored_by_perception():
    engine = PerceptionEngineV2()
    
    c1 = create_valid_candle(1, "2026-06-24T00:00:00")
    c2 = create_valid_candle(2, "2026-06-24T01:00:00") # Future relative to decision time
    
    # Should not raise exception, but should ignore c2
    snapshot = engine.analyze([c1, c2], decision_time=datetime.fromisoformat("2026-06-24T00:30:00").replace(tzinfo=timezone.utc))
    assert snapshot.decision_time == datetime.fromisoformat("2026-06-24T00:30:00").replace(tzinfo=timezone.utc)

def test_unclosed_candle_attack():
    engine = PerceptionEngineV2()
    
    c1 = create_valid_candle(1, "2026-06-24T00:00:00")
    c1.is_closed = False
    
    with pytest.raises(ValueError, match="Cannot process unclosed candles in historical context"):
        engine.analyze([c1], decision_time=datetime.fromisoformat("2026-06-24T00:30:00").replace(tzinfo=timezone.utc))
