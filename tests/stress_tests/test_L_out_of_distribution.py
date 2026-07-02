import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.data.schemas import Candle

def generate_candles(symbol: str, timeframe: str) -> list[Candle]:
    base_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return [
        Candle(
            venue="BINANCE",
            instrument=symbol,
            timeframe=timeframe,
            open_time=base_time,
            close_time=base_time + timedelta(minutes=15),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
            trade_count=100,
            is_closed=True,
            is_complete=True,
            contains_gap=False
        )
    ]

def test_l1_ood_detection_symbol_mismatch():
    """
    Test L1: Out-of-Distribution - Symbol Mismatch
    Assert that feeding an alternative symbol into a system expecting BTCUSDT
    causes an explicit failure instead of arbitrary processing.
    """
    engine = PerceptionEngineV2(expected_instrument="BTCUSDT", expected_timeframe="15m")
    
    # Generate OOD candles
    eth_candles = generate_candles("ETHUSDT", "15m")
    
    dt = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="OOD mismatch: expected instrument BTCUSDT"):
        engine.analyze(eth_candles, dt)

def test_l1_ood_detection_timeframe_mismatch():
    """
    Test L1: Out-of-Distribution - Timeframe Mismatch
    Assert that feeding 1H data into a 15m system causes an explicit failure.
    """
    engine = PerceptionEngineV2(expected_instrument="BTCUSDT", expected_timeframe="15m")
    
    # Generate OOD candles
    htf_candles = generate_candles("BTCUSDT", "1H")
    
    dt = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="OOD mismatch: expected timeframe 15m"):
        engine.analyze(htf_candles, dt)

def test_l1_ood_detection_pass_valid_distribution():
    """
    Test L1: In-Distribution passes successfully.
    """
    engine = PerceptionEngineV2(expected_instrument="BTCUSDT", expected_timeframe="15m")
    
    # Generate valid candles
    valid_candles = generate_candles("BTCUSDT", "15m")
    
    dt = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    
    # Should not raise
    snapshot = engine.analyze(valid_candles, dt)
    assert snapshot.decision_time == dt
