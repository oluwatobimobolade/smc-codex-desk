#!/usr/bin/env python3
"""Generate a TradingView Pine overlay from an SMC case.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.tradingview_overlay import write_tradingview_overlay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Pine Script overlay from an SMC case.")
    parser.add_argument("--case", required=True, help="Path to case.json.")
    parser.add_argument("--output", help="Output .pine file. Defaults to case folder/tradingview_overlay.pine.")
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = write_tradingview_overlay(
        case_path=Path(args.case),
        output_path=Path(args.output) if args.output else None,
    )
    print(f"Wrote TradingView Pine overlay: {manifest['pine_path']}")
    print(f"Wrote overlay manifest: {Path(manifest['pine_path']).with_suffix('.manifest.json')}")
    if args.print_summary:
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
