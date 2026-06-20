#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk import analyze_ohlcv, build_trade_plan_markdown, load_rule_config
from smc_desk.models import AnalysisResult, TradePlan
from smc_desk.render import render_annotated_chart, render_screenshot_review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SMC analysis on OHLCV data and optional screenshots.")
    parser.add_argument("--ohlcv", help="Path to an OHLCV CSV file.")
    parser.add_argument("--image", help="Optional screenshot path.")
    parser.add_argument("--symbol", required=True, help="Instrument symbol.")
    parser.add_argument("--timeframe", required=True, help="Chart timeframe.")
    parser.add_argument("--bias", help="Optional directional bias hint.")
    parser.add_argument("--notes", help="Optional manual notes.")
    parser.add_argument("--rules", help="Optional rules JSON path.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for generated artifacts.")
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def screenshot_only_result(symbol: str, timeframe: str, bias: str | None, notes: str | None) -> AnalysisResult:
    limitations = [
        "Screenshot-only mode does not infer SMC structure automatically in this version.",
        "Attach OHLCV data for deterministic structure analysis and annotated chart rendering.",
        "Use the screenshot review output as a discipline sheet, not as a stand-alone signal engine.",
    ]
    trade_plan = TradePlan(
        direction=bias.lower() if bias and bias.lower() in {"bullish", "bearish"} else "neutral",
        thesis="Screenshot captured. Supply OHLCV data or detailed notes for deeper deterministic analysis.",
        warnings=["No candle data supplied, so no live structure inference was performed."],
        confidence=0.2,
    )
    return AnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        input_type="screenshot",
        generated_at="manual-review",
        bias_hint=bias,
        notes=notes,
        metrics={"bars_analyzed": 0},
        session_context={"current_session": None},
        swings=[],
        zones=[],
        events=[],
        trade_plan=trade_plan,
        limitations=limitations,
    )


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.ohlcv and not args.image:
        raise SystemExit("Provide at least one input: --ohlcv or --image")

    if args.ohlcv:
        config = load_rule_config(args.rules)
        input_type = "hybrid" if args.image else "ohlcv"
        analysis, df = analyze_ohlcv(
            ohlcv_path=args.ohlcv,
            symbol=args.symbol,
            timeframe=args.timeframe,
            config=config,
            bias_hint=args.bias,
            notes=args.notes,
            input_type=input_type,
        )
        write_json(output_dir / "analysis.json", analysis.model_dump())
        (output_dir / "trade_plan.md").write_text(build_trade_plan_markdown(analysis), encoding="utf-8")
        render_annotated_chart(df, analysis, str(output_dir / "annotated_chart.png"))
        if args.image:
            render_screenshot_review(args.image, analysis, str(output_dir / "screenshot_review.png"))
    else:
        analysis = screenshot_only_result(args.symbol, args.timeframe, args.bias, args.notes)
        write_json(output_dir / "analysis.json", analysis.model_dump())
        (output_dir / "trade_plan.md").write_text(build_trade_plan_markdown(analysis), encoding="utf-8")
        render_screenshot_review(args.image, analysis, str(output_dir / "screenshot_review.png"))


if __name__ == "__main__":
    main()
