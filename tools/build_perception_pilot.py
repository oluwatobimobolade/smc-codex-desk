import os
import json
import random
import logging
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

from smc_desk.engine import load_ohlcv_csv
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.data.schemas import Candle
from decimal import Decimal
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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

def render_clean_chart(df: pd.DataFrame, output_path: str, venue: str, symbol: str, timeframe: str) -> None:
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor("#1a1a1a")
    ax.set_facecolor("#1a1a1a")
    ax.grid(color="#333333", linewidth=0.5, alpha=0.5)
    
    up, dn = "#4caf50", "#f44336"
    body_floor = (float(h.max()) - float(l.min())) * 1e-3
    
    for i in range(n):
        col = up if c[i] >= o[i] else dn
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
        lo_b, hi_b = min(o[i], c[i]), max(o[i], c[i])
        ax.add_patch(Rectangle((i - 0.34, lo_b), 0.68, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))
        
    ax.tick_params(axis='x', colors='#888888')
    ax.tick_params(axis='y', colors='#888888')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#333333')
    ax.spines['left'].set_color('#333333')
    
    # Title showing decision timestamp
    decision_ts = pd.to_datetime(df.iloc[-1]['timestamp'])
    title = f"{venue.upper()} | {symbol} | {timeframe} | Decision TS: {decision_ts.isoformat()} Z"
    ax.set_title(title, color="#ffffff", loc='left', pad=10)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=100, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)

def calculate_neutral_stratum(slice_df: pd.DataFrame) -> str:
    """Calculates a neutral stratum based on the preceding 50 bars."""
    tail = slice_df.iloc[-50:].copy()
    c = tail['close'].astype(float).values
    h = tail['high'].astype(float).values
    l = tail['low'].astype(float).values
    
    ret = (c[-1] - c[0]) / c[0]
    
    # ATR logic (simple)
    tr = np.maximum(h - l, np.abs(h - np.roll(c, 1)))
    tr[0] = h[0] - l[0]
    atr = np.mean(tr[-20:])
    
    # Efficiency ratio
    net_change = abs(c[-1] - c[0])
    sum_changes = np.sum(np.abs(np.diff(c)))
    er = net_change / sum_changes if sum_changes > 0 else 0
    
    # Stratification logic
    if er < 0.2:
        return "Ranging"
    elif atr / c[-1] > 0.015:  # Arbitrary high vol threshold for 15m crypto
        return "Volatile"
    elif ret > 0.02:
        return "Positive_Directional"
    elif ret < -0.02:
        return "Negative_Directional"
    else:
        return "Random"

def parse_args():
    parser = argparse.ArgumentParser(description="Build SMC Perception Pilot Cohort")
    parser.add_argument("--venue", type=str, default="binance")
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    parser.add_argument("--market-type", type=str, default="perpetual")
    parser.add_argument("--timeframe", type=str, default="15m")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--visible-bars", type=int, default=200)
    parser.add_argument("--minimum-separation-bars", type=int, default=250)
    parser.add_argument("--seed", type=int, default=260624)
    parser.add_argument("--release", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    return parser.parse_args()

def main():
    args = parse_args()
    logger.info(f"Building SMC Perception Pilot: {args.output}")
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load Data
    # For simplicity of this script, we hardcode the path based on args
    data_path = f"data/ohlcv/{args.venue}_futures/{args.symbol}/{args.symbol}_{args.timeframe}_4year.csv"
    df = load_ohlcv_csv(data_path)
    if len(df) < args.visible_bars * 2:
        logger.error(f"Insufficient data in {data_path}")
        return
        
    random.seed(args.seed)
    np.random.seed(args.seed)
    
    # 2. Candidate Selection
    valid_indices = []
    # Evaluate candidates
    for i in range(args.visible_bars, len(df)):
        # Ensure complete candles (assuming our data is pre-cleaned)
        valid_indices.append(i)
        
    # We want to stratify. Let's pre-calculate a random large sample to find our strata
    # to avoid calculating on 100k rows
    pool = random.sample(valid_indices, min(10000, len(valid_indices)))
    
    # 5 Strata targets
    target_per_strata = args.count // 5
    remainder = args.count % 5
    
    strata_counts = {
        "Positive_Directional": 0,
        "Negative_Directional": 0,
        "Ranging": 0,
        "Volatile": 0,
        "Random": 0
    }
    
    selected_indices = []
    
    for idx in pool:
        if len(selected_indices) >= args.count:
            break
            
        # Check separation
        overlap = False
        for s_tuple in selected_indices:
            if abs(idx - s_tuple[0]) < args.minimum_separation_bars:
                overlap = True
                break
        if overlap:
            continue
            
        slice_df = df.iloc[idx - args.visible_bars + 1 : idx + 1]
        stratum = calculate_neutral_stratum(slice_df)
        
        # Balance strata
        if strata_counts[stratum] < target_per_strata:
            strata_counts[stratum] += 1
            selected_indices.append((idx, stratum))
        elif sum(strata_counts.values()) >= (args.count - remainder):
            # Fill remaining with random
            if strata_counts["Random"] < target_per_strata + remainder:
                strata_counts["Random"] += 1
                selected_indices.append((idx, "Random"))
                
    selected_indices.sort(key=lambda x: x[0])
    
    logger.info(f"Selected {len(selected_indices)} cases. Strata distribution: {strata_counts}")
    
    # 3. Create Case Packages
    engine_v2 = PerceptionEngineV2()
    
    cohort_manifest = {
        "generated_at": datetime.utcnow().isoformat(),
        "release_tag": args.release,
        "parameters": vars(args),
        "cases": []
    }
    
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(exist_ok=True)
    
    overlap_report = []
    
    # Pre-check overlaps (should be 0 by definition above, but we explicitly report it)
    for i in range(len(selected_indices)):
        for j in range(i+1, len(selected_indices)):
            overlap = max(0, args.visible_bars - (selected_indices[j][0] - selected_indices[i][0]))
            overlap_report.append(f"CASE-{i+1:03d},CASE-{j+1:03d},{overlap}")
            
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(exist_ok=True)
    with open(reports_dir / "window_overlap_report.csv", "w") as f:
        f.write("case_a,case_b,overlap_bars\n")
        f.write("\n".join(overlap_report))
    
    for i, (idx, stratum) in enumerate(selected_indices):
        case_id = f"CASE-{i+1:03d}"
        case_dir = cases_dir / case_id
        case_dir.mkdir(exist_ok=True)
        
        slice_df = df.iloc[idx - args.visible_bars + 1 : idx + 1].copy()
        slice_df.reset_index(drop=True, inplace=True)
        
        ts_str = str(slice_df.iloc[-1]['timestamp'])
        
        # Public
        public_manifest = {
            "case_id": case_id,
            "venue": args.venue,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "decision_timestamp": ts_str,
            "visible_bars": args.visible_bars
        }
        with open(case_dir / "public_manifest.json", "w") as f:
            json.dump(public_manifest, f, indent=2)
            
        render_clean_chart(slice_df, str(case_dir / "clean_review.png"), args.venue, args.symbol, args.timeframe)
        
        # Save exact OHLCV
        slice_df.to_json(case_dir / "candles.json", orient="records", date_format="iso")
        
        # Engine execution (Sealed)
        candles = df_to_candles(slice_df, args.venue, args.symbol, args.timeframe)
        v2_res = engine_v2.analyze(candles, candles[-1].close_time)
        
        with open(case_dir / "v2_objects.json", "w") as f:
            json.dump(v2_res.model_dump(mode='json'), f, indent=2)
            
        sealed_manifest = {
            "stratum": stratum,
            "index_offset": int(idx),
            "close_price": float(slice_df.iloc[-1]['close'])
        }
        with open(case_dir / "sealed_manifest.json", "w") as f:
            json.dump(sealed_manifest, f, indent=2)
            
        cohort_manifest["cases"].append({
            "case_id": case_id,
            "decision_timestamp": ts_str
        })
        
    with open(output_dir / "cohort_manifest.json", "w") as f:
        json.dump(cohort_manifest, f, indent=2)
        
    # Reviewer Folders
    for r_id in ["reviewer_a", "reviewer_b", "adjudicator"]:
        r_dir = output_dir / "reviewer_exports" / r_id
        r_dir.mkdir(parents=True, exist_ok=True)
        
        # Empty template
        template = {
            "case_id": "FILL_ME",
            "reviewer_id": r_id,
            "manual_version": "1.0.0",
            "started_at": "",
            "submitted_at": "",
            "chart_valid": True,
            "context_sufficient": True,
            "external_direction": "",
            "internal_direction": "",
            "objects": [],
            "ambiguities": [],
            "overall_confidence": 1.0,
            "locked": False
        }
        with open(r_dir / "annotation_template.json", "w") as f:
            json.dump(template, f, indent=2)

    logger.info("Cohort built successfully.")

if __name__ == "__main__":
    main()

