#!/usr/bin/env python3
"""Generate chart-review packages for vision-model evaluation.

Each sample contains a raw chart for blind vision evaluation, a separate chart
with deterministic engine overlays, and an engine pseudo-label JSON file. The
pseudo-labels are useful for visual regression and explanation; they are not
expert ground truth and cannot establish engine or vision accuracy.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.mtf import build_mtf_snapshot, snapshot_to_dict
from smc_desk.render import render_annotated_chart, render_raw_chart
from smc_desk.rules import load_rule_config


def _extract_patterns(result: Any) -> dict[str, list[dict[str, Any]]]:
    patterns: dict[str, list[dict[str, Any]]] = {
        "bos": [],
        "choch": [],
        "fvg": [],
        "order_block": [],
        "liquidity_sweep": [],
        "equal_highs": [],
        "equal_lows": [],
    }
    for event in result.events:
        target = {"BOS": "bos", "CHoCH": "choch", "Liquidity Sweep": "liquidity_sweep"}.get(event.label)
        if target is None:
            continue
        item: dict[str, Any] = {
            "index": event.index,
            "timestamp": event.timestamp,
            "price": event.price,
            "direction": event.direction,
            "strength": event.strength,
            "structure_scope": event.structure_scope,
            "displacement_score": event.displacement_score,
        }
        if event.swept_level is not None:
            item["swept_level"] = event.swept_level
        patterns[target].append(item)

    for zone in result.zones:
        target = None
        if zone.kind == "fvg":
            target = "fvg"
        elif zone.kind == "order_block":
            target = "order_block"
        elif zone.label == "Equal Highs":
            target = "equal_highs"
        elif zone.label == "Equal Lows":
            target = "equal_lows"
        if target is None:
            continue
        patterns[target].append(
            {
                "label": zone.label,
                "low": zone.low,
                "high": zone.high,
                "direction": zone.direction,
                "status": zone.status,
                "score": zone.score,
            }
        )
    return patterns


def generate_training_sample(
    df: pd.DataFrame,
    index: int,
    config: Any,
    output_dir: Path,
    sample_id: int,
    symbol: str,
    chart_bars: int,
) -> dict[str, Any]:
    """Generate one raw chart, overlay chart, and pseudo-label package."""
    decision_time = pd.Timestamp(df.at[index, "timestamp"])
    history = df.iloc[: index + 1].copy()
    result, analyzed_df = analyze_dataframe(
        df=history,
        symbol=symbol,
        timeframe="15m",
        config=config,
        notes="vision_pseudo_label",
        input_type="ohlcv",
    )

    # Analyzer indices point at its own lookback window, so retain all analyzed bars.
    chart_df = analyzed_df.tail(max(chart_bars, len(analyzed_df))).reset_index(drop=True)
    raw_chart_path = output_dir / "raw" / f"sample_{sample_id:06d}.png"
    overlay_chart_path = output_dir / "overlay" / f"sample_{sample_id:06d}.png"
    render_raw_chart(chart_df, symbol=symbol, timeframe="15m", output_path=str(raw_chart_path))
    render_annotated_chart(chart_df, result, str(overlay_chart_path))

    label = {
        "dataset_version": "2.0",
        "sample_id": sample_id,
        "decision_time": decision_time.isoformat(),
        "decision_index": index,
        "symbol": symbol,
        "timeframe": "15m",
        "label_provenance": {
            "kind": "engine_pseudo_label",
            "authority": "deterministic OHLCV engine",
            "allowed_use": ["visual regression", "overlay explanation", "vision-to-engine agreement study"],
            "forbidden_use": ["engine accuracy claim", "vision accuracy claim", "expert ground truth"],
        },
        "artifacts": {
            "raw_chart": str(raw_chart_path),
            "engine_overlay": str(overlay_chart_path),
        },
        "patterns": _extract_patterns(result),
        "unsupported_primitives": ["inducement", "supply", "demand"],
        "trade_plan": {
            "direction": result.trade_plan.direction,
            "verdict": result.trade_plan.verdict,
            "setup_grade": result.trade_plan.setup_grade,
            "confluence_score": result.trade_plan.confluence_score,
            "entry_low": result.trade_plan.entry_low,
            "entry_high": result.trade_plan.entry_high,
            "invalidation": result.trade_plan.invalidation,
            "targets": result.trade_plan.targets,
        },
        "mtf_context": snapshot_to_dict(build_mtf_snapshot(history, decision_time, config)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    label_path = output_dir / "labels" / f"sample_{sample_id:06d}.json"
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text(json.dumps(label, indent=2), encoding="utf-8")
    return label


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate raw/overlay chart packages with engine pseudo-labels.")
    parser.add_argument("--ohlcv", required=True, help="15m OHLCV CSV path")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--output-dir", required=True, help="Output directory for sample packages")
    parser.add_argument("--max-samples", type=int, default=1000)
    parser.add_argument("--decision-step", type=int, default=10)
    parser.add_argument("--warmup-bars", type=int, default=400)
    parser.add_argument("--chart-bars", type=int, default=250, help="Minimum visible bars; the engine lookback is retained when larger.")
    parser.add_argument("--rules", help="Optional rules JSON path")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(args.ohlcv)
    symbol = args.symbol.upper()

    print(f"Generating pseudo-labelled chart packages from {args.ohlcv}")
    samples_generated = 0
    for index in range(args.warmup_bars, len(df) - 100, args.decision_step):
        if samples_generated >= args.max_samples:
            break
        generate_training_sample(
            df,
            index,
            config,
            output_dir,
            samples_generated,
            symbol=symbol,
            chart_bars=args.chart_bars,
        )
        samples_generated += 1
        if samples_generated % 100 == 0:
            print(f"Generated {samples_generated}/{args.max_samples} samples...")

    manifest = {
        "dataset_version": "2.0",
        "symbol": symbol,
        "samples_generated": samples_generated,
        "label_provenance": "engine_pseudo_label",
        "accuracy_note": "Not expert ground truth. Use tools/evaluate_perception_gold.py for real perception evaluation.",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {samples_generated} engine pseudo-labelled review samples")
    print(f"Raw charts: {output_dir / 'raw'}")
    print(f"Engine overlays: {output_dir / 'overlay'}")
    print(f"Gold evaluation: tools/evaluate_perception_gold.py --root case_library")


if __name__ == "__main__":
    main()
