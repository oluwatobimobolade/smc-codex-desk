#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import load_ohlcv_csv
from smc_desk.models import AnalysisResult
from smc_desk.render import render_bias_comparison_chart


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare user bias inputs with the model trade plan.")
    parser.add_argument("--analysis", required=True, help="Path to analysis.json.")
    parser.add_argument("--ohlcv", help="Path to OHLCV CSV for chart rendering.")
    parser.add_argument("--user-direction", help="Your direction: bullish or bearish.")
    parser.add_argument("--user-entry", type=float, help="Your entry price.")
    parser.add_argument("--user-stop", type=float, help="Your invalidation or stop.")
    parser.add_argument("--user-target", type=float, help="Your primary target.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for comparison files.")
    return parser.parse_args()


def assess_alignment(analysis: AnalysisResult, user_direction: str | None, user_entry: float | None, user_stop: float | None, user_target: float | None) -> str:
    plan = analysis.trade_plan
    lines = [
        f"# Bias Comparison: {analysis.symbol} {analysis.timeframe}",
        "",
        f"Model direction: {plan.direction}",
        f"User direction: {user_direction or 'N/A'}",
        "",
        "## Agreement",
    ]

    agreement: list[str] = []
    disagreement: list[str] = []

    if user_direction and user_direction.lower() == plan.direction:
        agreement.append("Directional bias matches the model.")
    elif user_direction:
        disagreement.append("Directional bias conflicts with the model.")

    if user_entry is not None and plan.entry_low is not None and plan.entry_high is not None:
        if plan.entry_low <= user_entry <= plan.entry_high:
            agreement.append("Entry sits inside the model entry zone.")
        else:
            disagreement.append("Entry sits outside the model entry zone.")

    if user_stop is not None and plan.invalidation is not None:
        relative_gap = abs(user_stop - plan.invalidation) / max(abs(plan.invalidation), 1e-9)
        if relative_gap <= 0.003:
            agreement.append("Invalidation is close to the model invalidation.")
        else:
            disagreement.append("Invalidation differs materially from the model invalidation.")

    if user_target is not None and plan.targets:
        relative_gap = abs(user_target - plan.targets[0]) / max(abs(plan.targets[0]), 1e-9)
        if relative_gap <= 0.005:
            agreement.append("Primary target is close to the model target.")
        else:
            disagreement.append("Primary target differs materially from the model target.")

    if not agreement:
        lines.append("- No strong alignment detected.")
    else:
        lines.extend(f"- {item}" for item in agreement)

    lines.extend(["", "## Disagreement"])
    if not disagreement:
        lines.append("- No major disagreement detected from the supplied inputs.")
    else:
        lines.extend(f"- {item}" for item in disagreement)

    lines.extend(
        [
            "",
            "## Model Thesis",
            analysis.trade_plan.thesis,
            "",
            "## Model Levels",
            f"- Entry zone: {plan.entry_low} - {plan.entry_high}",
            f"- Execution SL / invalidation: {plan.invalidation}",
            f"- Structural invalidation: {plan.structural_invalidation}",
            f"- Stop quality: {plan.stop_quality} ({plan.stop_buffer_atr} ATR)",
            f"- Targets: {', '.join(str(target) for target in plan.targets) or 'N/A'}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    analysis = AnalysisResult.model_validate(payload)

    report = assess_alignment(
        analysis,
        user_direction=args.user_direction,
        user_entry=args.user_entry,
        user_stop=args.user_stop,
        user_target=args.user_target,
    )
    (output_dir / "bias_comparison.md").write_text(report, encoding="utf-8")

    if args.ohlcv:
        df = load_ohlcv_csv(args.ohlcv)
        render_bias_comparison_chart(
            df,
            analysis,
            str(output_dir / "bias_comparison.png"),
            user_direction=args.user_direction,
            user_entry=args.user_entry,
            user_stop=args.user_stop,
            user_target=args.user_target,
        )


if __name__ == "__main__":
    main()
