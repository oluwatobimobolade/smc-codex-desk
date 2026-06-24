import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pandas as pd

from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2

def create_candle(t: int, o: str, h: str, l: str, c: str) -> Candle:
    dt = datetime(2026, 6, 24, tzinfo=timezone.utc) + timedelta(minutes=15 * t)
    return Candle(
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=dt,
        close_time=dt + timedelta(minutes=14, seconds=59),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal("1000"),
        trade_count=100,
        is_closed=True,
        is_complete=True,
        contains_gap=False
    )

def test_causality_wall():
    """
    Stage 2 Causality Test:
    Verify that analyzing a truncated sequence yields the EXACT same PerceptionSnapshot
    as analyzing a full sequence with the same decision_time.
    """
    engine = PerceptionEngineV2()
    
    # Generate 100 candles of mock data with some structure
    candles = []
    current_price = Decimal("50000")
    for i in range(100):
        # Create an uptrend then downtrend
        if i < 30:
            current_price += Decimal("50")
        elif i < 70:
            current_price -= Decimal("70")
        else:
            current_price += Decimal("30")
            
        candles.append(create_candle(i, str(current_price), str(current_price + 20), str(current_price - 20), str(current_price)))
        
    # Decision time at T=50
    decision_idx = 50
    decision_time = candles[decision_idx].close_time
    
    # 1. Truncated history: Pass only candles up to decision_idx
    truncated_candles = candles[:decision_idx + 1]
    snapshot_truncated = engine.analyze(truncated_candles, decision_time=decision_time)
    
    # 2. Full history: Pass all 100 candles, but same decision_time
    # This proves the engine does not "peek" into the future array elements
    snapshot_full = engine.analyze(candles, decision_time=decision_time)
    
    # 3. Compare the dict dumps to ensure deep structural equality
    # We must exclude `last_updated_at` because it records the system clock time of the object generation.
    dict_truncated = snapshot_truncated.model_dump()
    dict_full = snapshot_full.model_dump()
    
    def remove_last_updated_at(d):
        if isinstance(d, dict):
            return {k: remove_last_updated_at(v) for k, v in d.items() if k != 'last_updated_at'}
        elif isinstance(d, list):
            return [remove_last_updated_at(v) for v in d]
        return d
        
    assert remove_last_updated_at(dict_truncated) == remove_last_updated_at(dict_full), \
        "Causality Wall Broken: Future data leaked into perception snapshot!"
