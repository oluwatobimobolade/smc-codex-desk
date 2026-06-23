#!/usr/bin/env python3
"""Build fusion gold-set candidates for blind human labeling.

This tool harvests charts where the fusion layer produced a non-trivial verdict
(Execute, Watch, contested, or override) and generates blind review templates
for the human to label. The labels are the measurement instrument: without them
every confidence number in the system is fiction.

Label schema (per case):
    direction: "long" | "short" | "no_trade"
    conviction: "high" | "medium" | "low"
    why: one-line rationale
    key_feature: the one visual/structural feature that decided it

The human labels BEFORE seeing what the engine or fusion said. If the model
labels them, it is grading itself against itself, which measures nothing.
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
from smc_desk.episode_narrative import EpisodeNarrativeBuilder
from smc_desk.features import detect_failed_breakout, detect_vertical_spike_trap, regime_features
from smc_desk.fusion_engine import FusionEngine
from smc_desk.intent_detector import IntentDetector, MarketContext
from smc_desk.render import render_annotated_chart
from smc_desk.rules import RuleConfig, load_rule_config
from smc_desk.sequence_memory import BarSnapshot


LABEL_SCHEMA = {
    "direction": "long | short | no_trade",
    "conviction": "high | medium | low",
    "why": "one-line rationale (before seeing engine output)",
    "key_feature": "the one visual/structural feature that decided it",
    "reviewer": "your name",
    "review_date": "YYYY-MM-DD",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Harvest fusion gold-set candidates for blind human labeling."
    )
    parser.add_argument("--ohlcv", required=True, help="OHLCV CSV path.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--rules", help="Optional rules JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for candidate cases.")
    parser.add_argument("--warmup-bars", type=int, default=250)
    parser.add_argument("--step-bars", type=int, default=48, help="Evaluate every N bars.")
    parser.add_argument("--max-cases", type=int, default=20, help="Maximum candidates to harvest.")
    parser.add_argument(
        "--filter",
        choices=["all", "non_pass", "overrides", "contested"],
        default="non_pass",
        help="Only harvest cases where fusion produced this type of output.",
    )
    return parser.parse_args()


def _bar_from_row(idx: int, row: pd.Series) -> BarSnapshot:
    ts = row["timestamp"]
    if isinstance(ts, pd.Timestamp):
        ts = ts.isoformat()
    return BarSnapshot(
        index=idx,
        timestamp=str(ts),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume", 0.0)),
    )


def _should_harvest(fusion_result, filter_mode: str) -> bool:
    """Decide whether a fusion result is worth harvesting as a gold candidate."""
    if filter_mode == "all":
        return True
    if filter_mode == "non_pass":
        return fusion_result.recommended_verdict != "Pass"
    if filter_mode == "overrides":
        return len(fusion_result.overrides) > 0
    if filter_mode == "contested":
        return fusion_result.contested
    return False


def _build_fusion_at_decision(
    df: pd.DataFrame,
    config: RuleConfig,
    symbol: str,
    timeframe: str,
    decision_idx: int,
) -> dict[str, Any]:
    """Run the full fusion stack on data up to decision_idx."""
    visible = df.iloc[: decision_idx + 1].copy()
    analysis, _ = analyze_dataframe(
        df=visible,
        symbol=symbol,
        timeframe=timeframe,
        config=config,
        input_type="ohlcv",
    )

    # Episode narrative from engine events.
    builder = EpisodeNarrativeBuilder()
    events_by_index: dict[int, list] = {}
    for event in analysis.events:
        events_by_index.setdefault(event.index, []).append(event)
    for idx, row in visible.iterrows():
        builder.process_bar(_bar_from_row(idx, row), events_by_index.get(idx, []))

    # OHLCV features.
    records = visible.to_dict("records")
    spike = detect_vertical_spike_trap(records)
    failed_breakout = detect_failed_breakout(records)
    pattern_dicts: list[dict] = []
    if spike.get("detected"):
        pattern_dicts.append({
            "pattern_type": "vertical_spike_trap",
            "direction": spike["direction"],
            "confidence": spike["score"],
            "invalidates_bias": "bullish" if spike["direction"] == "bullish" else "bearish",
        })
    if failed_breakout.get("detected"):
        pattern_dicts.append({
            "pattern_type": "failed_breakout",
            "direction": failed_breakout["direction"],
            "confidence": failed_breakout["score"],
        })

    regime = regime_features(records)
    context = MarketContext(symbol=symbol, timeframe=timeframe, regime_label=regime.get("regime_label", "unknown"))
    intent_detector = IntentDetector()
    intent_result = intent_detector.detect_intent(
        sequence_memory=builder,
        visual_patterns=pattern_dicts,
        context=context,
    )

    fusion = FusionEngine()
    fusion_result = fusion.fuse(
        engine_result=analysis,
        sequence_memory=builder,
        intent_result=intent_result,
        visual_patterns=pattern_dicts,
        context=context,
    )

    return {
        "decision_bar": decision_idx,
        "timestamp": str(visible.iloc[-1]["timestamp"]),
        "engine_primary_verdict": analysis.trade_plan.verdict,
        "engine_primary_direction": analysis.trade_plan.direction,
        "fusion_recommended_verdict": fusion_result.recommended_verdict,
        "fusion_recommended_direction": fusion_result.recommended_direction,
        "fusion_contested": fusion_result.contested,
        "fusion_overrides": [o.to_dict() for o in fusion_result.overrides],
        "fusion_conflicts": fusion_result.conflicts,
        "fusion_confidence": fusion_result.fused_confidence,
        "narrative": builder.get_current_narrative(),
        # Machine analysis is retained for later scoring but is NOT shown
        # in the blind review brief.
        "_machine_analysis": analysis.model_dump(),
        "_fusion_result": fusion_result.to_dict(),
    }


def _write_case(output_dir: Path, case_id: str, case_data: dict, df: pd.DataFrame, config: RuleConfig) -> None:
    """Write a single gold-set candidate case."""
    case_dir = output_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    # Blind review template (no machine output).
    review_template = {
        "case_id": case_id,
        "symbol": case_data["symbol"],
        "timeframe": case_data["timeframe"],
        "decision_bar": case_data["decision_bar"],
        "timestamp": case_data["timestamp"],
        "instructions": (
            "Label this chart BEFORE looking at any machine output. "
            "Your label is the ground truth. If you are unsure, label it "
            "'no_trade' with 'low' conviction."
        ),
        "label_schema": LABEL_SCHEMA,
        "label": {
            "direction": "",
            "conviction": "",
            "why": "",
            "key_feature": "",
            "reviewer": "",
            "review_date": "",
        },
    }
    (case_dir / "label.json").write_text(
        json.dumps(review_template, indent=2), encoding="utf-8"
    )

    # Annotated chart for the human to look at.
    visible = df.iloc[: case_data["decision_bar"] + 1]
    analysis, _ = analyze_dataframe(
        df=visible,
        symbol=case_data["symbol"],
        timeframe=case_data["timeframe"],
        config=config,
        input_type="ohlcv",
    )
    render_annotated_chart(visible, analysis, str(case_dir / "chart.png"))

    # Machine output (sealed — not linked from the review template).
    (case_dir / "machine_sealed.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "fusion": case_data["_fusion_result"],
                "engine": case_data["_machine_analysis"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(args.ohlcv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[dict[str, Any]] = []
    warmup = args.warmup_bars
    step = args.step_bars

    for decision_idx in range(warmup, len(df), step):
        if len(candidates) >= args.max_cases:
            break

        try:
            fusion_data = _build_fusion_at_decision(
                df, config, args.symbol, args.timeframe, decision_idx
            )
        except Exception:
            continue

        # Reconstruct a FusionResult-like object for filtering.
        from smc_desk.fusion_engine import FusionResult
        fr = FusionResult(
            engine_primary_verdict=fusion_data["engine_primary_verdict"],
            engine_primary_bias=fusion_data["engine_primary_direction"],
            engine_primary_grade="C",
            engine_primary_confidence=0.0,
            recommended_verdict=fusion_data["fusion_recommended_verdict"],
            recommended_direction=fusion_data["fusion_recommended_direction"],
            recommended_grade="C",
            fused_confidence=fusion_data["fusion_confidence"],
            contested=fusion_data["fusion_contested"],
        )
        # Populate overrides for filtering.
        from smc_desk.fusion_engine import FusionOverride
        fr.overrides = [FusionOverride(**o) for o in fusion_data["fusion_overrides"]]

        if not _should_harvest(fr, args.filter):
            continue

        case_id = f"{args.symbol}_{decision_idx:05d}"
        fusion_data["symbol"] = args.symbol
        fusion_data["timeframe"] = args.timeframe
        _write_case(output_dir, case_id, fusion_data, df, config)
        candidates.append({"case_id": case_id, **{k: v for k, v in fusion_data.items() if not k.startswith("_")}})

    # Write manifest.
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "ohlcv": str(Path(args.ohlcv).resolve()),
        "filter": args.filter,
        "total_candidates": len(candidates),
        "candidates": candidates,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"Harvested {len(candidates)} gold-set candidates to {output_dir}")
    print(f"Filter: {args.filter}")
    for c in candidates:
        print(f"  {c['case_id']}: fusion={c['fusion_recommended_verdict']} ({c['fusion_recommended_direction']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
