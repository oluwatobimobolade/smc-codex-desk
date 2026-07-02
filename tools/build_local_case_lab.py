#!/usr/bin/env python3
"""Build the local-first perception case lab from existing CSV data.

This is the one-command, no-model-API path for creating blind review cases.
It uses local Binance futures OHLCV files, writes clean charts plus sealed
engine weak labels, and requires adjudication before anything becomes gold.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY
from smc_desk.rules import load_rule_config
from tools.build_perception_gold_batch import build_batch
from tools.summarize_ohlcv_quality import DEFAULT_SYMBOLS


def normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local blind-review SMC perception cases.")
    parser.add_argument("--data-root", default=str(ROOT / "data/ohlcv/binance_futures"))
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--tag", default="4year")
    parser.add_argument("--output-root", default=str(ROOT / "case_library/local_first_lab"))
    parser.add_argument("--cases-per-symbol", type=int, default=20, help="Default 20 x 5 symbols = 100 cases.")
    parser.add_argument("--warmup-bars", type=int, default=400)
    parser.add_argument("--chart-bars", type=int, default=220)
    parser.add_argument("--reviewers", nargs="+", default=["reviewer_a", "reviewer_b"])
    parser.add_argument("--rules")
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--allow-holdout", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if len(args.reviewers) < 2:
        raise SystemExit("At least two independent reviewers are required.")
    data_root = Path(args.data_root)
    sources = []
    missing = []
    for raw_symbol in args.symbols:
        symbol = normalize_symbol(raw_symbol)
        path = data_root / symbol / f"{symbol}_15m_{args.tag}.csv"
        if not path.exists():
            missing.append(str(path))
        else:
            sources.append((symbol, path))
    if missing:
        raise SystemExit("Missing canonical 15m source file(s):\n" + "\n".join(missing))

    manifest = build_batch(
        sources,
        output_root=Path(args.output_root),
        cases_per_symbol=args.cases_per_symbol,
        warmup_bars=args.warmup_bars,
        chart_bars=args.chart_bars,
        config=load_rule_config(args.rules),
        reviewers=args.reviewers,
        holdout_policy=args.holdout_policy,
        allow_holdout=args.allow_holdout,
    )
    print(f"Built {manifest['case_count']} local-first perception cases at {Path(args.output_root).resolve()}")
    print("Engine labels were written as weak labels only. Nothing is gold until adjudicated.")


if __name__ == "__main__":
    main()
