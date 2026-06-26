#!/usr/bin/env python3
"""Resolve a colleague run's pending outcome contract from future 15m candles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.outcome_resolution import resolve_run_outcome


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill outcome/resolution.json from future OHLCV candles.")
    parser.add_argument("--run-dir", required=True, help="Path to an analysis_runs/<run_id> package.")
    parser.add_argument("--ohlcv", help="15m OHLCV CSV containing candles after decision_available_at. Defaults to source_manifest.json source_path.")
    parser.add_argument("--output", help="Override output path. Default: <run-dir>/outcome/resolution.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    resolution = resolve_run_outcome(
        run_dir=Path(args.run_dir),
        ohlcv_path=Path(args.ohlcv) if args.ohlcv else None,
        output_path=Path(args.output) if args.output else None,
    )
    print(
        json.dumps(
            {
                "status": resolution["status"],
                "symbol": resolution["symbol"],
                "available_bars": resolution["future_window"]["available_bars"],
                "required_bars": resolution["future_window"]["required_bars"],
                "market_edge_claimed": resolution["market_edge_claimed"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
