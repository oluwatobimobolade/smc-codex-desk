#!/usr/bin/env python3
"""Diagnose and acquire verified closed Binance USD-M futures candles."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.data.live_ohlcv import acquire_verified_closed_ohlcv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Acquire verified closed Binance candles and emit route-level diagnostics."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--min-bars", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--base-url", default="https://fapi.binance.com")
    parser.add_argument("--no-browser-fallback", action="store_true")
    parser.add_argument("--session", default="smc-binance-market-truth")
    parser.add_argument("--output-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else ROOT
        / "analysis_runs"
        / f"live_ohlcv_diagnostic_{args.symbol.upper()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    try:
        manifest_path, manifest = acquire_verified_closed_ohlcv(
            symbol=args.symbol,
            output_dir=output_dir,
            interval=args.interval,
            limit=args.limit,
            min_bars=args.min_bars,
            timeout=args.timeout,
            base_url=args.base_url,
            webbridge_session=args.session,
            allow_browser_fallback=not args.no_browser_fallback,
        )
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc), "output_dir": str(output_dir)}, indent=2))
        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "status": manifest["status"],
                "provider": manifest["provider"],
                "symbol": manifest["symbol"],
                "interval": manifest["interval"],
                "rows": manifest["row_count"],
                "last_closed_candle_open": manifest["last_closed_candle_open"],
                "last_closed_candle_close": manifest["last_closed_candle_close"],
                "fetched_at": manifest["fetched_at"],
                "source_csv": manifest["source_csv"],
                "manifest": str(manifest_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
