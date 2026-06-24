import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from decimal import Decimal

from smc_desk.engine import load_ohlcv_csv
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.data.schemas import Candle
from smc_desk.rendering.chart_renderer import SMCChartRenderer
from smc_desk.rendering.render_audit import RenderAuditor
from smc_desk.rendering.screenshot_manifest import ScreenshotManifest

def df_to_candles(df: pd.DataFrame, venue="binance", instrument="BTCUSDT", timeframe="15m") -> list[Candle]:
    candles = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        c = Candle(
            venue=venue,
            instrument=instrument,
            timeframe=timeframe,
            open_time=ts,
            close_time=ts + pd.Timedelta(timeframe),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            trade_count=0,
            is_closed=True,
            is_complete=True,
            contains_gap=False
        )
        candles.append(c)
    return candles

def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main():
    print("Building Rendering Examples...")
    output_dir = Path("rendering_examples")
    output_dir.mkdir(exist_ok=True)
    
    # Load data
    df = load_ohlcv_csv("data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv")
    
    # Take a slice of 150 candles
    slice_df = df.iloc[500:650].copy().reset_index(drop=True)
    
    engine_v2 = PerceptionEngineV2()
    candles = df_to_candles(slice_df)
    decision_time = candles[-1].close_time
    
    # Run analysis
    snapshot = engine_v2.analyze(candles, decision_time)
    
    renderer = SMCChartRenderer()
    config = {
        "figsize": (18, 9),
        "dpi": 120,
        "tick_size": 0.05,
        "symbol": "BTCUSDT",
        "timeframe": "15m"
    }
    
    dataset_hash = sha256_hash(slice_df.to_json().encode())
    perception_hash = sha256_hash(snapshot.model_dump_json().encode())
    
    modes = ["clean", "live", "audit", "review"]
    
    for mode in modes:
        print(f"Rendering mode: {mode}")
        img_path = output_dir / f"{mode}.png"
        sg_path = output_dir / f"scene_graph_{mode}.json"
        manifest_path = output_dir / f"screenshot_manifest_{mode}.json"
        audit_path = output_dir / f"render_audit_{mode}.json"
        
        # Render
        img_bytes, sg, transform = renderer.render(slice_df, snapshot, mode, config, str(img_path))
        
        # Run Audit
        auditor = RenderAuditor()
        audit_report = auditor.verify(slice_df, snapshot, sg, transform, Decimal("0.05"))
        
        # Save Scene Graph
        sg_data = sg.model_dump(mode="json")
        with open(sg_path, "w") as f:
            json.dump(sg_data, f, indent=2)
            
        # Save Audit Report
        with open(audit_path, "w") as f:
            json.dump(audit_report, f, indent=2)
            
        # Calculate Hashes
        image_hash = sha256_hash(img_bytes)
        sg_hash = sha256_hash(json.dumps(sg_data).encode())
        
        # Build Manifest
        manifest = ScreenshotManifest(
            case_id=None,
            venue="binance_futures",
            instrument="BTCUSDT",
            market_type="perpetual",
            timeframe="15m",
            decision_time=decision_time.isoformat(),
            latest_completed_candle=candles[-1].close_time.isoformat(),
            timezone="UTC",
            visible_start_time=candles[0].open_time.isoformat(),
            visible_end_time=candles[-1].close_time.isoformat(),
            visible_bar_count=len(candles),
            price_scale="linear",
            price_minimum=float(transform.minimum_visible_price),
            price_maximum=float(transform.maximum_visible_price),
            tick_size=0.05,
            chart_width=float(transform.chart_width_px),
            chart_height=float(transform.chart_height_px),
            plot_bounds={
                "left": transform.plot_left_px,
                "right": transform.plot_right_px,
                "top": transform.plot_top_px,
                "bottom": transform.plot_bottom_px
            },
            device_pixel_ratio=1.0,
            theme="dark",
            render_mode=mode,
            renderer_version="2.0.0",
            semantic_schema_version="1.0.0",
            configuration_hash=hashlib.sha256(b"render_v2").hexdigest()[:8],
            git_commit="HEAD",
            dataset_hash=dataset_hash,
            perception_snapshot_hash=perception_hash,
            scene_graph_hash=sg_hash,
            image_hash=image_hash,
            generation_timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        with open(manifest_path, "w") as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2)
            
    print("Examples successfully generated in rendering_examples/")

if __name__ == "__main__":
    main()
