#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk import analyze_ohlcv, load_rule_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract detected SMC zones from OHLCV data.")
    parser.add_argument("--ohlcv", required=True, help="Path to OHLCV CSV.")
    parser.add_argument("--symbol", required=True, help="Instrument symbol.")
    parser.add_argument("--timeframe", required=True, help="Chart timeframe.")
    parser.add_argument("--rules", help="Optional rules JSON path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_rule_config(args.rules)
    analysis, _ = analyze_ohlcv(
        ohlcv_path=args.ohlcv,
        symbol=args.symbol,
        timeframe=args.timeframe,
        config=config,
    )
    print(json.dumps([zone.model_dump() for zone in analysis.zones], indent=2))


if __name__ == "__main__":
    main()
