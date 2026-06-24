import pytest
import random
import csv
import os
from datetime import datetime, timedelta, UTC
from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2

def generate_synthetic_candles(count: int, start_time: datetime, interval_minutes: int = 15) -> list[Candle]:
    candles = []
    current_time = start_time
    price = 50000.0
    for _ in range(count):
        close_time = current_time + timedelta(minutes=interval_minutes)
        # Random walk
        change = random.uniform(-100, 100)
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + random.uniform(0, 50)
        low_p = min(open_p, close_p) - random.uniform(0, 50)
        volume = random.uniform(10, 1000)
        
        c = Candle(
            venue="BINANCE",
            instrument="BTCUSDT",
            timeframe="15m",
            open_time=current_time,
            close_time=close_time,
            open=round(open_p, 2),
            high=round(high_p, 2),
            low=round(low_p, 2),
            close=round(close_p, 2),
            volume=round(volume, 2),
            trade_count=int(volume * 2),
            is_complete=True,
            is_closed=True,
            contains_gap=False
        )
        candles.append(c)
        price = close_p
        current_time = close_time
    return candles

import json

def strip_dynamic_fields(data):
    if isinstance(data, dict):
        return {k: strip_dynamic_fields(v) for k, v in data.items() if k != "last_updated_at"}
    elif isinstance(data, list):
        return [strip_dynamic_fields(v) for v in data]
    return data

def serialize_snapshot(snapshot) -> str:
    # We serialize the lengths and specific IDs for comparison, ignoring clock time
    data = snapshot.model_dump(mode="json")
    stripped = strip_dynamic_fields(data)
    return json.dumps(stripped, sort_keys=True)

def test_b1_causality():
    random.seed(42)
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    total_candles = 2000
    candles = generate_synthetic_candles(total_candles, start_time)
    
    engine = PerceptionEngineV2()
    
    # Pick 100 random decision timestamps that are exactly on close_time of some candles
    test_indices = random.sample(range(100, total_candles-1), 100)
    test_indices.sort()
    
    failures = []
    
    for idx in test_indices:
        decision_time = candles[idx].close_time
        
        # 1. Truncated history
        history_cut = candles[:idx+1]
        snap_cut = engine.analyze(history_cut, decision_time)
        str_cut = serialize_snapshot(snap_cut)
        
        # 2. Full history
        snap_full = engine.analyze(candles, decision_time)
        str_full = serialize_snapshot(snap_full)
        
        if str_cut != str_full:
            failures.append({
                "decision_time": decision_time,
                "reason": "Snapshot mismatch between truncated and full history"
            })
    
    os.makedirs("reports", exist_ok=True)
    with open("reports/causality_failures.csv", "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["decision_time", "reason"])
        writer.writeheader()
        writer.writerows(failures)
        
    assert len(failures) == 0, f"Future leakage detected in {len(failures)} timestamps"
