#!/usr/bin/env python3
"""Build a single SMC analyst case from OHLCV plus optional TradingView screenshots.

The output is a training/review folder, not a trade signal:
- case.json: machine-readable data, screenshots, MTF context, analysis, label scaffold
- machine_report.md: readable model thesis and checklist
- human_label.md: expert review template for turning the case into training data
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.case_library import build_case_payload, load_screenshot_metadata, write_case_files
from smc_desk.engine import load_ohlcv_csv
from smc_desk.rules import load_rule_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an SMC case-study folder from OHLCV and optional screenshots.")
    parser.add_argument("--symbol", required=True, help="Instrument symbol, e.g. BTCUSDT.")
    parser.add_argument("--exchange", default="BINANCE", help="Exchange/source prefix, e.g. BINANCE, BITSTAMP, or OANDA.")
    parser.add_argument("--ohlcv", required=True, help="15m OHLCV CSV used for deterministic analysis.")
    parser.add_argument("--screenshots-meta", help="screenshots.json from tools/smc_webbridge_analyst.py.")
    parser.add_argument("--decision-time", help="ISO timestamp. Defaults to the last candle in --ohlcv.")
    parser.add_argument("--rules", help="Optional rules JSON path.")
    parser.add_argument("--notes", help="Optional analyst notes to embed in the machine case.")
    parser.add_argument("--case-kind", default="live_analysis", help="Case type label, e.g. live_analysis, backtest_trade, near_miss.")
    parser.add_argument("--data-source-name", default="Binance USD-M Futures OHLCV")
    parser.add_argument("--expected-step-minutes", type=int, default=15)
    parser.add_argument("--output-dir", help="Output folder. Defaults to case_library/<SYMBOL>/<timestamp>_<case-kind>.")
    return parser.parse_args()


def default_output_dir(symbol: str, case_kind: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return ROOT / "case_library" / symbol.upper() / f"{stamp}_{case_kind}"


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper().replace("/", "").replace("-", "")
    ohlcv_path = Path(args.ohlcv)
    screenshot_meta = load_screenshot_metadata(Path(args.screenshots_meta)) if args.screenshots_meta else None
    cfg = load_rule_config(args.rules)
    df = load_ohlcv_csv(str(ohlcv_path))

    payload = build_case_payload(
        symbol=symbol,
        exchange=args.exchange,
        ohlcv_path=ohlcv_path,
        df=df,
        config=cfg,
        decision_time=args.decision_time,
        screenshot_meta=screenshot_meta,
        notes=args.notes,
        case_kind=args.case_kind,
        data_source_name=args.data_source_name,
        expected_step_minutes=args.expected_step_minutes,
    )

    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(symbol, args.case_kind)
    paths = write_case_files(output_dir, payload)
    print(f"Wrote SMC case: {output_dir}")
    for label, path in paths.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
