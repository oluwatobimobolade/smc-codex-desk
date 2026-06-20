#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a synthetic OHLCV sample for local testing.")
    parser.add_argument("--output", default="sample_ohlcv.csv", help="Output CSV path.")
    parser.add_argument("--bars", type=int, default=220, help="Number of bars to generate.")
    parser.add_argument("--start", type=float, default=2320.0, help="Starting price.")
    parser.add_argument("--timeframe-minutes", type=int, default=15, help="Minutes per bar.")
    parser.add_argument("--shock-pct", type=float, help="Optional volatility as a fraction of price, for example 0.001 for BTC.")
    parser.add_argument("--wick-pct", type=float, help="Optional wick size as a fraction of price, for example 0.00035 for BTC.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(42)
    timestamps = []
    rows = []
    price = args.start
    start_time = datetime.now(timezone.utc) - timedelta(minutes=args.bars * args.timeframe_minutes)

    for index in range(args.bars):
        timestamp = start_time + timedelta(minutes=index * args.timeframe_minutes)
        drift = 0.08 if index < args.bars * 0.45 else (-0.04 if index < args.bars * 0.7 else 0.05)
        if args.shock_pct:
            drift = price * (0.00005 if index < args.bars * 0.45 else (-0.00003 if index < args.bars * 0.7 else 0.00004))
            shock = float(rng.normal(0, price * args.shock_pct))
        else:
            shock = float(rng.normal(0, 0.9))
        open_price = price
        close_price = max(1.0, open_price + drift + shock)
        if args.wick_pct:
            wick_up = abs(float(rng.normal(price * args.wick_pct, price * args.wick_pct * 0.45)))
            wick_down = abs(float(rng.normal(price * args.wick_pct, price * args.wick_pct * 0.45)))
        else:
            wick_up = abs(float(rng.normal(0.7, 0.35)))
            wick_down = abs(float(rng.normal(0.6, 0.30)))
        high_price = max(open_price, close_price) + wick_up
        low_price = min(open_price, close_price) - wick_down
        volume = abs(float(rng.normal(1200, 280)))
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": round(open_price, 5),
                "high": round(high_price, 5),
                "low": round(low_price, 5),
                "close": round(close_price, 5),
                "volume": round(volume, 2),
            }
        )
        price = close_price
        timestamps.append(timestamp)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)


if __name__ == "__main__":
    main()
