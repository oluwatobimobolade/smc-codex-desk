#!/usr/bin/env python3
"""Run observe-only live Market Colleague packages across a symbol universe."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.live_shadow import run_live_shadow_universe
from smc_desk.rules import load_rule_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build observe-only live shadow colleague runs for multiple Binance perp symbols.")
    parser.add_argument("symbols", nargs="+", help="Example: BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT")
    parser.add_argument("--output-root", help="Default: analysis_runs/live_shadow_universe_<UTC timestamp>")
    parser.add_argument("--rules")
    parser.add_argument("--bars", type=int, default=500, help="Bars to request from TradingView per timeframe.")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--session-prefix", default="smc-tv-live-shadow")
    parser.add_argument("--fail-fast", action="store_true", help="Abort the universe on the first symbol failure.")
    parser.add_argument("--disallow-holdout", action="store_true", help="Live shadow normally allows holdout because it is observe-only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = (
        Path(args.output_root).expanduser()
        if args.output_root
        else ROOT / "analysis_runs" / f"live_shadow_universe_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    summary = run_live_shadow_universe(
        symbols=args.symbols,
        output_root=output_root,
        config=load_rule_config(args.rules),
        bars=args.bars,
        timeout_ms=args.timeout_ms,
        session_prefix=args.session_prefix,
        allow_holdout=not args.disallow_holdout,
        continue_on_error=not args.fail_fast,
    )
    print(json.dumps({"status": summary["status"], "output_root": summary["output_root"], "symbols": summary["symbols_completed"]}, indent=2))
    print(f"Summary: {Path(summary['output_root']) / 'summary.md'}")


if __name__ == "__main__":
    main()
