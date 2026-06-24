import pytest
from datetime import datetime, timezone
from decimal import Decimal

from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.perception.ontology import ConfirmationStatus, Direction

def test_perception_engine_v2_basic():
    engine = PerceptionEngineV2()
    
    # Create 20 mock candles
    candles = []
    base_time = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    for i in range(20):
        # We simulate a peak at index 5 and a trough at index 10
        price = 100
        if i == 5:
            price = 150
        elif i == 10:
            price = 50
        else:
            price = 100
            
        c = Candle(
            venue="binance", instrument="BTCUSDT", timeframe="15m",
            open_time=base_time, close_time=base_time, # Simplify times
            open=Decimal(str(price)), high=Decimal(str(price+5)), low=Decimal(str(price-5)), close=Decimal(str(price)),
            volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
        )
        candles.append(c)
        base_time = datetime.fromtimestamp(base_time.timestamp() + 900, tz=timezone.utc)
        
    decision_time = candles[-1].close_time
    
    snapshot = engine.analyze(candles, decision_time)
    
    # Assert swings detected
    assert len(snapshot.swings["local"]) > 0
    
    # Assert ontology structure
    first_swing = snapshot.swings["local"][0]
    assert first_swing.confirmation_status == ConfirmationStatus.CONFIRMED
    assert len(first_swing.events) == 2  # Created, Confirmed
    assert first_swing.direction in [Direction.BULLISH, Direction.BEARISH]
    
    # Verify no strategy imports leaked in
    import sys
    assert "smc_desk.strategy" not in sys.modules, "Strategy layer leaked into perception!"

def test_perception_engine_v2_causality():
    engine = PerceptionEngineV2()
    
    # Create mock candles
    candles = []
    base_time = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    for i in range(20):
        c = Candle(
            venue="binance", instrument="BTCUSDT", timeframe="15m",
            open_time=base_time, close_time=base_time,
            open=Decimal("100"), high=Decimal(str(100+i)), low=Decimal(str(100-i)), close=Decimal("100"),
            volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
        )
        candles.append(c)
        base_time = datetime.fromtimestamp(base_time.timestamp() + 900, tz=timezone.utc)
        
    t_decision = candles[10].close_time
    
    # 1. Analyze full dataset with decision_time capped at index 10
    snap_full = engine.analyze(candles, t_decision)
    
    # 2. Analyze truncated dataset
    snap_truncated = engine.analyze(candles[:11], t_decision)
    
    # The output structure should match exactly
    # We can check specific items to avoid missing deep equivalence
    assert snap_full.fvgs == snap_truncated.fvgs
    assert snap_full.structure_breaks == snap_truncated.structure_breaks
    
    # Check swings by scale
    for scale in snap_full.swings:
        assert len(snap_full.swings[scale]) == len(snap_truncated.swings[scale])
