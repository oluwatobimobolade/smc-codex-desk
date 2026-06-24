import pytest
import pandas as pd
from smc_desk.engine import analyze_dataframe
from smc_desk.rules import RuleConfig

def test_out_of_distribution_data():
    """Stage 12: Out-of-Distribution Test
    Run the perception engine on an entirely different asset class
    or very low quality / thinly traded data to ensure it doesn't crash
    and appropriately handles the noise (e.g. no valid setups found).
    """
    # Create thinly traded, gappy data (e.g. illiquid altcoin or strange commodity)
    data = []
    base_price = 0.0001
    for i in range(100):
        # Huge gaps, sometimes open == close, huge wicks
        gap = (i % 5) * 0.00005
        open_p = base_price + gap
        close_p = open_p + (0.00001 if i % 2 == 0 else -0.00001)
        high_p = max(open_p, close_p) + 0.00008
        low_p = min(open_p, close_p) - 0.00008
        
        data.append({
            "timestamp": 1600000000 + i * 3600,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": 0.0 if i % 3 == 0 else 100.0 # Lots of zero volume
        })

    df = pd.DataFrame(data)
    # The engine should process this without crashing
    analysis_result, _ = analyze_dataframe(df, "OOD_COIN", "15m", RuleConfig())
    
    assert analysis_result is not None
    # We expect very messy structure, or at least no clean setups
    # The pipeline should safely return the snapshot.
    assert hasattr(analysis_result, 'swings')
    assert hasattr(analysis_result, 'zones')
    assert hasattr(analysis_result, 'events')
    assert analysis_result.trade_plan.verdict == "Pass"

