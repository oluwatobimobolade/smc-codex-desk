import pytest
import pandas as pd
import hashlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json

from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.perception.ontology import SwingObject, SwingEvidence, FairValueGapEvidence, StructureBreakEvidence, Direction, ConfirmationStatus
from smc_desk.perception.fvg import FairValueGapObject
from smc_desk.perception.structure import StructureBreakObject
from smc_desk.rendering.chart_renderer import SMCChartRenderer
from smc_desk.rendering.coordinate_transform import CoordinateTransform
from smc_desk.rendering.scene_graph import SceneGraph
from smc_desk.rendering.render_audit import RenderAuditor

@pytest.fixture
def sample_data():
    base_time = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(100):
        # Add FVG pattern at indices 5, 6, 7
        # Add swing high at index 20
        # Add swing low at index 30
        price = 100.0
        if i == 5:
            price = 110.0
        elif i == 6:
            price = 105.0
        elif i == 7:
            price = 95.0
        elif i == 20:
            price = 150.0
        elif i == 30:
            price = 50.0
        elif i == 40: # Break of swing low (50)
            price = 45.0
            
        c = Candle(
            venue="binance", instrument="BTCUSDT", timeframe="15m",
            open_time=base_time, close_time=base_time + timedelta(minutes=15),
            open=Decimal(str(price)), high=Decimal(str(price + 2)), low=Decimal(str(price - 2)), close=Decimal(str(price)),
            volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
        )
        candles.append(c)
        base_time += timedelta(minutes=15)
        
    df = pd.DataFrame([{
        "timestamp": c.open_time,
        "open": float(c.open),
        "high": float(c.high),
        "low": float(c.low),
        "close": float(c.close),
        "volume": float(c.volume)
    } for c in candles])
    
    return candles, df

@pytest.fixture
def sample_snapshot(sample_data):
    candles, df = sample_data
    decision_time = candles[-1].close_time
    
    # 1. Swings
    swing_high = SwingObject(
        object_id="sw_high_1", venue="binance", instrument="BTCUSDT", timeframe="15m",
        pivot_time=candles[20].open_time, candidate_at=candles[20].open_time,
        confirmed_at=candles[23].open_time, current_as_of=decision_time,
        detector_version="2.0", configuration_hash="abc", source_candle_ids=["c20"],
        last_updated_at=decision_time, confidence=1.0, direction=Direction.BEARISH,
        price_low=Decimal("148.0"), price_high=Decimal("152.0"),
        evidence=SwingEvidence(bars_left=3, bars_right=3, prominence_atr_pct=1.0, is_external=True)
    )
    
    swing_low = SwingObject(
        object_id="sw_low_1", venue="binance", instrument="BTCUSDT", timeframe="15m",
        pivot_time=candles[30].open_time, candidate_at=candles[30].open_time,
        confirmed_at=candles[33].open_time, current_as_of=decision_time,
        detector_version="2.0", configuration_hash="abc", source_candle_ids=["c30"],
        last_updated_at=decision_time, confidence=1.0, direction=Direction.BULLISH,
        price_low=Decimal("48.0"), price_high=Decimal("52.0"),
        evidence=SwingEvidence(bars_left=3, bars_right=3, prominence_atr_pct=1.0, is_external=True)
    )
    
    # 2. FVG
    fvg = FairValueGapObject(
        object_id="fvg_1", venue="binance", instrument="BTCUSDT", timeframe="15m",
        pivot_time=candles[6].open_time, candidate_at=candles[6].open_time,
        confirmed_at=candles[7].open_time, current_as_of=decision_time,
        detector_version="2.0", configuration_hash="abc", source_candle_ids=["c5", "c6", "c7"],
        last_updated_at=decision_time, confidence=1.0, direction=Direction.BEARISH,
        price_low=Decimal("97.0"), price_high=Decimal("108.0"),
        evidence=FairValueGapEvidence(gap_size_ticks=1100, gap_size_bps=0.1, atr_ratio=1.5, is_mitigated_on_creation=False)
    )
    
    # 3. Structure Break
    brk = StructureBreakObject(
        object_id="brk_1", venue="binance", instrument="BTCUSDT", timeframe="15m",
        pivot_time=candles[30].open_time, candidate_at=candles[40].open_time,
        confirmed_at=candles[40].close_time, current_as_of=decision_time,
        detector_version="2.0", configuration_hash="abc", source_candle_ids=["c40"],
        last_updated_at=decision_time, confidence=1.0, direction=Direction.BEARISH,
        price_low=Decimal("43.0"), price_high=Decimal("47.0"),
        is_choch=False, break_type="BOS",
        evidence=StructureBreakEvidence(
            broken_swing_id="sw_low_1", broken_price=Decimal("48.0"),
            wick_penetration=Decimal("5.0"), body_close_penetration=Decimal("3.0"),
            penetration_ticks=500, penetration_atr_pct=1.0, candle_body_ratio=0.8,
            displacement_strength=1.0, is_internal=False, is_unconfirmed_probe=False
        )
    )
    
    snapshot = PerceptionSnapshot(
        decision_time=decision_time,
        swings={"external": [swing_high, swing_low]},
        structure_state={
            "current_direction": "bearish",
            "protected_high_id": None,
            "protected_low_id": None,
            "last_confirmed_external_high": None,
            "last_confirmed_external_low": None,
            "last_external_break_id": None,
            "last_internal_break_id": None,
            "current_as_of": decision_time
        },
        structure_breaks=[brk],
        fvgs=[fvg]
    )
    return snapshot

def test_v3_rendering_round_trips(sample_data, sample_snapshot):
    _, df = sample_data
    renderer = SMCChartRenderer()
    config = {"figsize": (18, 9), "dpi": 100, "tick_size": 0.01, "symbol": "BTCUSDT", "timeframe": "15m"}
    
    img_bytes, sg, transform = renderer.render(df, sample_snapshot, "audit", config)
    
    # 1. Price-to-pixel and pixel-to-price round trips
    p = Decimal("100.0")
    y = transform.price_to_y(p)
    p2 = transform.y_to_price(y)
    assert abs(p2 - p) <= Decimal("0.05")
    
    # 2. Time-to-pixel and pixel-to-time round trips
    t = df.iloc[50]["timestamp"].to_pydatetime().replace(tzinfo=timezone.utc)
    x = transform.time_to_x(t)
    t2 = transform.x_to_time(x)
    assert abs((t2 - t).total_seconds()) <= 900 # within 1 candle tolerance

def test_v3_rendering_fvg_accuracy(sample_data, sample_snapshot):
    _, df = sample_data
    renderer = SMCChartRenderer()
    config = {"figsize": (18, 9), "dpi": 100, "tick_size": 0.01, "symbol": "BTCUSDT", "timeframe": "15m"}
    img_bytes, sg, transform = renderer.render(df, sample_snapshot, "audit", config)
    
    # 3. FVG rectangle boundary accuracy
    fvg_obj = [o for o in sg.objects if o.semantic_object_type == "fvg"][0]
    # Check if bounds match ontology
    assert fvg_obj.market_geometry.price_low == Decimal("97.0")
    assert fvg_obj.market_geometry.price_high == Decimal("108.0")
    
    # Verify exact Decimal or tick-price preservation
    assert isinstance(fvg_obj.market_geometry.price_low, Decimal)

def test_v3_rendering_structure_break(sample_data, sample_snapshot):
    _, df = sample_data
    renderer = SMCChartRenderer()
    config = {"figsize": (18, 9), "dpi": 100, "tick_size": 0.01, "symbol": "BTCUSDT", "timeframe": "15m"}
    img_bytes, sg, transform = renderer.render(df, sample_snapshot, "audit", config)
    
    # 4 & 5 & 6 & 7: Connectors and Break styling
    break_objs = [o for o in sg.objects if o.semantic_object_id == "brk_1"]
    assert len(break_objs) > 0
    # The break line
    brk_line = [o for o in break_objs if o.shape_type == "horizontal_line"][0]
    assert brk_line.market_geometry.price_low == Decimal("48.0") # broken swing price

def test_v3_rendering_modes(sample_data, sample_snapshot):
    _, df = sample_data
    renderer = SMCChartRenderer()
    config = {"figsize": (18, 9), "dpi": 100, "tick_size": 0.01, "symbol": "BTCUSDT", "timeframe": "15m"}
    
    # 15. Review mode contains no engine annotations
    img_review, sg_review, _ = renderer.render(df, sample_snapshot, "review", config)
    annotated_review_objs = [o for o in sg_review.objects if o.semantic_object_id is not None]
    assert len(annotated_review_objs) == 0
    
    # 16. Clean mode contains no perception annotations
    img_clean, sg_clean, _ = renderer.render(df, sample_snapshot, "clean", config)
    annotated_clean_objs = [o for o in sg_clean.objects if o.semantic_object_id is not None]
    assert len(annotated_clean_objs) == 0

def test_v3_rendering_determinism(sample_data, sample_snapshot):
    _, df = sample_data
    renderer = SMCChartRenderer()
    config = {"figsize": (18, 9), "dpi": 100, "tick_size": 0.01, "symbol": "BTCUSDT", "timeframe": "15m"}
    
    img1, sg1, _ = renderer.render(df, sample_snapshot, "audit", config)
    img2, sg2, _ = renderer.render(df, sample_snapshot, "audit", config)
    
    # 11 & 12: Deterministic scene graph and image output
    sg1.scene_graph_id = "test"
    sg2.scene_graph_id = "test"
    sg1.generated_at = sg2.generated_at
    assert sg1.model_dump_json() == sg2.model_dump_json()
    assert img1 == img2

def test_v3_rendering_auditor(sample_data, sample_snapshot):
    _, df = sample_data
    renderer = SMCChartRenderer()
    config = {"figsize": (18, 9), "dpi": 100, "tick_size": 0.01, "symbol": "BTCUSDT", "timeframe": "15m"}
    
    img_bytes, sg, transform = renderer.render(df, sample_snapshot, "audit", config)
    
    auditor = RenderAuditor()
    report = auditor.verify(df, sample_snapshot, sg, transform, Decimal("0.01"))
    
    # 13 & 14 & 17 & 18 & 19: Referential integrity, no future candles, exact decimal preservation
    assert report["success"] == True
