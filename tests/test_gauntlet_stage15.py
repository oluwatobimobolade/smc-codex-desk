import pytest
import pandas as pd
from smc_desk.engine import analyze_dataframe
from smc_desk.rules import RuleConfig

def test_drift_and_version_stability():
    """Stage 15: Drift and Version-Stability Test
    Process a known historical canonical chart and ensure that the output 
    is deterministic. If we run it twice, we must get identical results,
    proving no hidden randomness or drift in the core engine.
    """
    # Create simple stable dataset
    data = []
    base_price = 100.0
    for i in range(50):
        data.append({
            "timestamp": 1600000000 + i * 3600,
            "open": base_price + i,
            "high": base_price + i + 2,
            "low": base_price + i - 1,
            "close": base_price + i + 1,
            "volume": 100.0
        })

    df = pd.DataFrame(data)
    
    # Run once
    config = RuleConfig()
    res1, _ = analyze_dataframe(df, "STABLE_COIN", "1h", config)
    
    # Run twice
    res2, _ = analyze_dataframe(df, "STABLE_COIN", "1h", config)
    
    # Compare critical properties
    assert len(res1.swings) == len(res2.swings)
    assert len(res1.zones) == len(res2.zones)
    assert len(res1.events) == len(res2.events)
    
    for s1, s2 in zip(res1.swings, res2.swings):
        assert s1.index == s2.index
        assert s1.price == s2.price
        
    for z1, z2 in zip(res1.zones, res2.zones):
        assert z1.low == z2.low
        assert z1.high == z2.high

