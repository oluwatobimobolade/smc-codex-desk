#!/usr/bin/env python3
"""Replay the setup state machine across the local Binance futures universe."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY
from tools.replay_setup_states import replay
from tools.summarize_ohlcv_quality import DEFAULT_SYMBOLS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay local setup states for the full crypto futures universe.")
    parser.add_argument("--data-root", default=str(ROOT / "data/ohlcv/binance_futures"))
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--tag", default="4year")
    parser.add_argument("--rules")
    parser.add_argument("--warmup-bars", type=int, default=400)
    parser.add_argument("--max-bars", type=int, default=500)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--displacement-timeout-bars", type=int, default=3)
    parser.add_argument("--retrace-timeout-bars", type=int, default=48)
    parser.add_argument("--confirmation-timeout-bars", type=int, default=24)
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--allow-holdout", action="store_true")
    return parser.parse_args()


def normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Setup State-Machine Universe Replay",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "This is observability only. It creates no trade plans, paper orders, or live execution authority.",
        "",
        "## Summary",
        f"- Symbols: {', '.join(report['symbols'])}",
        f"- Bars replayed: {report['totals']['bars_replayed']}",
        f"- Attempts started: {report['totals']['attempts_started']}",
        "",
        "## By Symbol",
        "",
        "| Symbol | Bars | Attempts | State Counts | Terminal Reasons |",
        "|---|---:|---:|---|---|",
    ]
    for item in report["symbols_report"]:
        lines.append(
            f"| {item['symbol']} | {item['window']['bars_replayed']} | {item['attempts_started']} | "
            f"`{json.dumps(item['state_counts'], sort_keys=True)}` | "
            f"`{json.dumps(item['terminal_reasons'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Outputs",
        ]
    )
    for item in report["symbols_report"]:
        lines.append(f"- {item['symbol']}: `{item['output_dir']}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    symbols = [normalize_symbol(symbol) for symbol in args.symbols]
    reports: list[dict[str, Any]] = []
    totals = {
        "bars_replayed": 0,
        "attempts_started": 0,
        "state_counts": Counter(),
        "terminal_reasons": Counter(),
    }

    for symbol in symbols:
        ohlcv = Path(args.data_root) / symbol / f"{symbol}_15m_{args.tag}.csv"
        if not ohlcv.exists():
            raise SystemExit(f"Missing local 15m file for {symbol}: {ohlcv}")
        symbol_dir = output_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        replay_args = SimpleNamespace(
            ohlcv=str(ohlcv),
            symbol=symbol,
            rules=args.rules,
            warmup_bars=args.warmup_bars,
            max_bars=args.max_bars,
            output_dir=str(symbol_dir),
            displacement_timeout_bars=args.displacement_timeout_bars,
            retrace_timeout_bars=args.retrace_timeout_bars,
            confirmation_timeout_bars=args.confirmation_timeout_bars,
            holdout_policy=args.holdout_policy,
            allow_holdout=args.allow_holdout,
        )
        result = replay(replay_args)
        (symbol_dir / "state_machine_replay.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        pd.DataFrame(result["state_observations"]).to_csv(symbol_dir / "state_observations.csv", index=False)
        pd.DataFrame(result["transitions"]).to_csv(symbol_dir / "state_transitions.csv", index=False)
        compact = {
            "symbol": symbol,
            "output_dir": str(symbol_dir.resolve()),
            "window": result["window"],
            "attempts_started": result["attempts_started"],
            "state_counts": result["state_counts"],
            "terminal_reasons": result["terminal_reasons"],
        }
        reports.append(compact)
        totals["bars_replayed"] += int(result["window"]["bars_replayed"])
        totals["attempts_started"] += int(result["attempts_started"])
        totals["state_counts"].update(result["state_counts"])
        totals["terminal_reasons"].update(result["terminal_reasons"])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "universe_state_machine_observability_only",
        "symbols": symbols,
        "data_root": str(Path(args.data_root).resolve()),
        "tag": args.tag,
        "totals": {
            "bars_replayed": totals["bars_replayed"],
            "attempts_started": totals["attempts_started"],
            "state_counts": dict(totals["state_counts"]),
            "terminal_reasons": dict(totals["terminal_reasons"]),
        },
        "symbols_report": reports,
    }
    (output_dir / "universe_state_machine_replay.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "universe_state_machine_replay.md").write_text(_render_markdown(report), encoding="utf-8")
    print(f"Replayed {len(symbols)} symbols. Wrote {output_dir / 'universe_state_machine_replay.md'}")


if __name__ == "__main__":
    main()
