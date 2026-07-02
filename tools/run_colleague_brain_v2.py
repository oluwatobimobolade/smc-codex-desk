#!/usr/bin/env python3
"""Run the observe-only colleague brain v2 pipeline on local OHLCV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.orchestrator_v2 import run_colleague_brain_v2
from smc_desk.colleague.run_context import build_run_market_context, dataframe_to_candles
from smc_desk.rules import load_rule_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--source", required=True, help="Canonical 15m OHLCV CSV")
    parser.add_argument("--decision-time", default=None, help="Availability/as-of time. Defaults to latest closed candle.")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--memory-file", default=None, help="Optional JSONL decision memory path")
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    context = build_run_market_context(Path(args.source).expanduser().resolve(), args.decision_time)
    decision_time = context.decision_available_at.tz_localize("UTC").to_pydatetime() if context.decision_available_at.tzinfo is None else context.decision_available_at.to_pydatetime()
    candles_by_tf = {
        timeframe: dataframe_to_candles(
            df.tail(240).reset_index(drop=True),
            venue="BINANCE",
            instrument=args.symbol,
            timeframe=timeframe,
            reference_time=decision_time,
        )
        for timeframe, df in context.timeframe_dfs.items()
    }
    result = run_colleague_brain_v2(
        candles_by_timeframe=candles_by_tf,
        decision_time=decision_time,
        symbol=args.symbol,
        memory_path=args.memory_file,
        config=load_rule_config(),
    )
    payload = result.to_dict()
    (output / "brain_v2_result.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (output / "summary.md").write_text(
        "\n".join(
            [
                f"# Colleague Brain V2 - {args.symbol}",
                "",
                f"- Decision time: `{payload['decision_time']}`",
                f"- Truth status: `{payload['truth_report']['status']}`",
                f"- Perception status: `{payload['perception_status']}`",
                f"- Final action: `{payload['final_action']}`",
                "- Execution authority: `disabled`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "final_action": payload["final_action"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
