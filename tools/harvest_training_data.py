#!/usr/bin/env python3
"""Harvest training data across all Binance futures symbols.

Runs the enriched feature extractor on each symbol's 4-year dataset,
producing a massive labeled CSV for ML model training.

Output:
- data/ml/train.csv (2022-07 to 2025-12)
- data/ml/holdout.csv (2026-01 to 2026-06)
- data/ml/manifest.json (metadata)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PYTHON = ROOT / ".venv" / "bin" / "python"
EXTRACTOR = ROOT / "tools" / "build_research_dataset.py"
DATA_ROOT = ROOT / "data" / "ohlcv" / "binance_futures"
OUTPUT_ROOT = ROOT / "data" / "ml"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]

# Train: 2022-07-01 to 2025-12-31
# Holdout: 2026-01-01 to 2026-06-19
TRAIN_START = "2022-07-01T00:00:00+00:00"
TRAIN_END = "2025-12-31T23:59:59+00:00"
HOLDOUT_START = "2026-01-01T00:00:00+00:00"
HOLDOUT_END = "2026-06-19T23:59:59+00:00"


def run_extractor(symbol: str, csv_path: Path, output_path: Path, decision_start: str, decision_end: str) -> dict:
    """Run the feature extractor for one symbol/period combination."""
    cmd = [
        str(PYTHON),
        str(EXTRACTOR),
        "--ohlcv", str(csv_path),
        "--symbol", symbol,
        "--timeframe", "15m",
        "--output", str(output_path),
        "--decision-start", decision_start,
        "--decision-end", decision_end,
        "--decision-step", "4",
        "--use-htf-bias", "on",
        "--poi-selection", "balanced",
        "--entry-wait-bars", "24",
        "--max-hold-bars", "96",
        "--cost-bps", "4.0",
        "--entry-mode", "boundary",
        "--warmup-bars", "400",
    ]
    
    print(f"  Running: {symbol} ({decision_start} to {decision_end})")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return {"symbol": symbol, "status": "error", "error": result.stderr}
    
    # Parse output to get trade count
    output_lines = result.stdout.strip().split("\n")
    last_line = output_lines[-1] if output_lines else ""
    
    return {
        "symbol": symbol,
        "status": "ok",
        "output": last_line,
        "csv": str(output_path),
    }


def main() -> None:
    print("=" * 80)
    print("SMC Elite Training Data Harvester")
    print("=" * 80)
    print()
    
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": SYMBOLS,
        "train_period": {"start": TRAIN_START, "end": TRAIN_END},
        "holdout_period": {"start": HOLDOUT_START, "end": HOLDOUT_END},
        "decision_step": 4,
        "use_htf_bias": "on",
        "poi_selection": "balanced",
        "features": [
            "symbol", "decision_index", "decision_time", "session", "direction",
            "verdict", "setup_grade", "confluence_score", "poi_kind", "poi_status",
            "poi_score", "poi_low", "poi_high", "poi_width_pct", "poi_age_bars",
            "poi_competing_count", "planned_rr", "htf_alignment", "htf_agreement_ratio",
            "htf_aligned", "htf_1h_bias", "htf_4h_bias", "htf_1d_bias", "htf_trend_strength",
            "triggered", "outcome", "r_multiple", "mfe_r", "mae_r", "entry_index",
            "displacement_score", "break_strength", "atr_at_decision", "atr_pct",
            "adx_at_decision", "premium_discount_ratio", "sweep_depth_atr",
            "sweep_recency_bars", "structure_event_density", "body_ratio_at_decision",
            "range_pct_at_decision", "hour_utc", "day_of_week", "minute_of_session",
            "is_killzone",
            "chk_directional_bias", "chk_fresh_or_partial_poi", "chk_premium_discount_aligned",
            "chk_liquidity_sweep", "chk_displacement_break", "chk_sweep_before_break",
            "chk_price_at_or_near_poi", "chk_stop_has_volatility_buffer", "chk_risk_reward_floor",
        ],
        "train_results": [],
        "holdout_results": [],
    }
    
    # Harvest train data
    print("PHASE 1: Harvesting TRAIN data (2022-07 to 2025-12)")
    print("-" * 80)
    train_csvs = []
    for symbol in SYMBOLS:
        csv_path = DATA_ROOT / symbol / f"{symbol}_15m_4year.csv"
        if not csv_path.exists():
            print(f"  SKIP: {csv_path} not found")
            continue
        
        output_path = OUTPUT_ROOT / f"{symbol}_train.csv"
        result = run_extractor(symbol, csv_path, output_path, TRAIN_START, TRAIN_END)
        manifest["train_results"].append(result)
        if result["status"] == "ok":
            train_csvs.append(output_path)
        print()
    
    # Harvest holdout data
    print("PHASE 2: Harvesting HOLDOUT data (2026-01 to 2026-06)")
    print("-" * 80)
    holdout_csvs = []
    for symbol in SYMBOLS:
        csv_path = DATA_ROOT / symbol / f"{symbol}_15m_4year.csv"
        if not csv_path.exists():
            print(f"  SKIP: {csv_path} not found")
            continue
        
        output_path = OUTPUT_ROOT / f"{symbol}_holdout.csv"
        result = run_extractor(symbol, csv_path, output_path, HOLDOUT_START, HOLDOUT_END)
        manifest["holdout_results"].append(result)
        if result["status"] == "ok":
            holdout_csvs.append(output_path)
        print()
    
    # Concatenate all train CSVs into one master file
    print("PHASE 3: Concatenating train CSVs")
    print("-" * 80)
    if train_csvs:
        import pandas as pd
        train_dfs = [pd.read_csv(csv) for csv in train_csvs]
        train_master = pd.concat(train_dfs, ignore_index=True)
        train_master_path = OUTPUT_ROOT / "train.csv"
        train_master.to_csv(train_master_path, index=False)
        print(f"  Wrote {train_master_path} ({len(train_master)} rows)")
        manifest["train_master"] = str(train_master_path)
        manifest["train_total_rows"] = len(train_master)
    else:
        print("  WARNING: No train CSVs produced")
    
    # Concatenate all holdout CSVs into one master file
    print("PHASE 4: Concatenating holdout CSVs")
    print("-" * 80)
    if holdout_csvs:
        import pandas as pd
        holdout_dfs = [pd.read_csv(csv) for csv in holdout_csvs]
        holdout_master = pd.concat(holdout_dfs, ignore_index=True)
        holdout_master_path = OUTPUT_ROOT / "holdout.csv"
        holdout_master.to_csv(holdout_master_path, index=False)
        print(f"  Wrote {holdout_master_path} ({len(holdout_master)} rows)")
        manifest["holdout_master"] = str(holdout_master_path)
        manifest["holdout_total_rows"] = len(holdout_master)
    else:
        print("  WARNING: No holdout CSVs produced")
    
    # Write manifest
    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print()
    print(f"Manifest written to {manifest_path}")
    print()
    print("=" * 80)
    print("HARVEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
