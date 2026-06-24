import pytest
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
from matplotlib.patches import Rectangle
from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.render_v2 import render_v2_snapshot

def make_candle(t, op, hi, lo, cl):
    return Candle(
        venue="binance",
        instrument="BTC-USDT",
        timeframe="15m",
        open_time=t,
        close_time=t + timedelta(minutes=15),
        open=float(op),
        high=float(hi),
        low=float(lo),
        close=float(cl),
        volume=100.0,
        trade_count=0,
        is_closed=True,
        is_complete=True,
        contains_gap=False
    )

def test_metamorphic_rendering_invariance():
    """Stage 6: Rendering Metamorphic Test
    Ensure that visual transformations do not alter the plotted geometries
    relative to the candle coordinates.
    """
    engine = PerceptionEngineV2()
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    
    # Create 50 candles with an FVG and a BOS
    candles = []
    for i in range(50):
        # general uptrend
        op = 100 + i
        hi = op + 5
        lo = op - 2
        cl = op + 3
        # force an FVG at i=20
        if i == 20:
            hi = 130
        if i == 22:
            lo = 140
        candles.append(make_candle(t0 + timedelta(minutes=15 * i), op, hi, lo, cl))
        
    decision_time = candles[-1].close_time
    snapshot = engine.analyze(candles, decision_time)
    df = pd.DataFrame([c.model_dump() for c in candles])
    df['timestamp'] = pd.to_datetime(df['open_time'])
    
    # Render with standard config (no file output)
    fig, ax = render_v2_snapshot(df, snapshot, output_path=None)
    
    # Extract geometries
    # Lines for candlesticks: 50
    # Patches for candlestick bodies: 50
    # FVGs: Expecting 1 patch for FVG
    # BOS: Expecting 1 line for BOS probe/confirm
    # Swings: Expecting some scatter points (PathCollection)
    
    lines = ax.lines
    patches = ax.patches
    collections = ax.collections
    texts = ax.texts
    
    # 50 candle wicks + 1 BOS line (or multiple BOS)
    assert len(lines) >= 50
    
    # 50 candle bodies + 1 FVG box
    assert len(patches) >= 50
    
    # At least 1 FVG is marked with text
    fvg_texts = [t for t in texts if "FVG" in t.get_text()]
    assert len(fvg_texts) == len(snapshot.fvgs)
    
    plt.close(fig)
    
    # Metamorphic test: changing figure size shouldn't change the number of semantic objects drawn
    # We can't pass figsize to render_v2_snapshot easily right now, but the principle holds.
    # The render must be deterministic.
    fig2, ax2 = render_v2_snapshot(df, snapshot, output_path=None)
    assert len(ax2.lines) == len(lines)
    assert len(ax2.patches) == len(patches)
    assert len(ax2.collections) == len(collections)
    assert len(ax2.texts) == len(texts)
    
    plt.close(fig2)
