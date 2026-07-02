#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.tradingview_live_manifest import build_live_alignment_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a verified TradingView/WebBridge alignment manifest.")
    parser.add_argument("--symbol", required=True, help="Example: BTCUSDT, ETHUSDT, SOLUSDT.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--session", default="smc-tv-align")
    parser.add_argument("--bars", type=int, default=500)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path, manifest = build_live_alignment_manifest(
        symbol=args.symbol,
        output_dir=Path(args.output_dir),
        session=args.session,
        bars=args.bars,
        timeout_ms=args.timeout_ms,
    )
    print(json.dumps({"manifest": str(path), "symbol": manifest["instrument"], "tradingview_symbol": manifest["tradingview_symbol"]}, indent=2))


if __name__ == "__main__":
    main()
