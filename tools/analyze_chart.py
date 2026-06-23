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
from smc_desk.dual_lens import reconcile, render_markdown
from smc_desk.episode_narrative import EpisodeNarrativeBuilder
from smc_desk.features import detect_failed_breakout, detect_vertical_spike_trap, regime_features
from smc_desk.fusion_engine import FusionEngine
from smc_desk.intent_detector import IntentDetector, MarketContext
from smc_desk.models import AnalysisResult, TradePlan
from smc_desk.render import render_annotated_chart, render_screenshot_review
from smc_desk.sequence_memory import BarSnapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SMC analysis on OHLCV data and optional screenshots.")
    parser.add_argument("--ohlcv", help="Path to an OHLCV CSV file.")
    parser.add_argument("--image", help="Optional screenshot path.")
    parser.add_argument("--symbol", required=True, help="Instrument symbol.")
    parser.add_argument("--timeframe", required=True, help="Chart timeframe.")
    parser.add_argument("--bias", help="Optional directional bias hint.")
    parser.add_argument("--notes", help="Optional manual notes.")
    parser.add_argument("--rules", help="Optional rules JSON path.")
    parser.add_argument("--vision", help="Optional path to a vision_read.json for the Dual Lens Macro Sanity Check.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for generated artifacts.")
    parser.add_argument(
        "--fusion",
        action="store_true",
        help="Run the experimental Fusion Engine in shadow mode. Logs observability output only; "
             "the engine verdict and trade plan remain authoritative.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _dataframe_to_episode_narrative(df, events):
    """Build an EpisodeNarrativeBuilder from bars + engine structure events."""
    builder = EpisodeNarrativeBuilder()
    events_by_index: dict[int, list] = {}
    for event in events:
        events_by_index.setdefault(event.index, []).append(event)
    for idx, row in df.iterrows():
        bar = BarSnapshot(
            index=idx,
            timestamp=str(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
        )
        builder.process_bar(bar, events_by_index.get(idx, []))
    return builder


def _run_fusion_analysis(analysis: AnalysisResult, df) -> dict:
    """Run the four-layer fusion stack for observability only.

    The visual layer is replaced by deterministic OHLCV features (numpy/pandas)
    so every detection is exact, reproducible, and leakage-free. Episodes are
    derived from engine structure events (the same evidence the state machine
    uses), not from an independent bar processor.
    """
    memory = _dataframe_to_episode_narrative(df, analysis.events)

    # OHLCV-derivable features (exact, no cv2).
    records = df.to_dict("records")
    spike = detect_vertical_spike_trap(records)
    failed_breakout = detect_failed_breakout(records)
    pattern_dicts: list[dict] = []
    if spike.get("detected"):
        pattern_dicts.append({
            "pattern_type": "vertical_spike_trap",
            "direction": spike["direction"],
            "confidence": spike["score"],
            "invalidates_bias": "bullish" if spike["direction"] == "bullish" else "bearish",
            "metadata": spike.get("metadata", {}),
        })
    if failed_breakout.get("detected"):
        pattern_dicts.append({
            "pattern_type": "failed_breakout",
            "direction": failed_breakout["direction"],
            "confidence": failed_breakout["score"],
            "invalidates_bias": failed_breakout["direction"],
            "metadata": failed_breakout.get("metadata", {}),
        })

    regime = regime_features(records)
    context = MarketContext(
        symbol=analysis.symbol,
        timeframe=analysis.timeframe,
        regime_label=regime.get("regime_label", "unknown"),
    )
    intent_detector = IntentDetector()
    intent_result = intent_detector.detect_intent(
        sequence_memory=memory,
        visual_patterns=pattern_dicts,
        context=context,
    )

    fusion = FusionEngine()
    fusion_result = fusion.fuse(
        engine_result=analysis,
        sequence_memory=memory,
        intent_result=intent_result,
        visual_patterns=pattern_dicts,
        context=context,
    )

    return {
        "sequence": {
            "episodes": [ep.to_dict() for ep in memory.episodes],
            "active_episode": memory.active_episode.to_dict() if memory.active_episode else None,
            "narrative": memory.get_current_narrative(),
        },
        "features": pattern_dicts,
        "intent": intent_result.to_dict(),
        "fusion": fusion_result.to_dict(),
    }


def _build_fusion_markdown(fusion_payload: dict) -> str:
    lines = [
        "# Fusion Engine Observability",
        "",
        "> **WARNING: SHADOW MODE.** This output is for research and review only.",
        "> The deterministic engine owns all prices, stops, targets, and invalidations.",
        "> The fused verdict shown here does **not** change the live trade plan.",
        "",
    ]
    fusion = fusion_payload["fusion"]
    lines.append(
        f"**Engine primary verdict:** {fusion['engine_primary_verdict']} "
        f"({fusion['engine_primary_bias']})"
    )
    lines.append(
        f"**Fused verdict:** {fusion['recommended_verdict']} "
        f"({fusion['recommended_direction']})"
    )
    if fusion.get("contested"):
        lines.append("**State:** CONTESTED — neither direction won by a clear margin.")
    lines.append(f"**Fused confidence:** {fusion['fused_confidence']}")
    lines.append("")
    lines.append("## Narrative")
    lines.append(fusion_payload["sequence"]["narrative"] or "No narrative yet.")
    lines.append("")
    lines.append("## Primary intent")
    intent = fusion_payload["intent"]
    lines.append(f"- {intent['primary_intent']} (confidence {intent['confidence']})")
    lines.append("")
    lines.append("## Dual-direction scores")
    for direction, score in fusion.get("scores", {}).items():
        lines.append(f"- {direction}: {score}")
    lines.append("")
    lines.append("## OHLCV features")
    features = fusion_payload.get("features", [])
    if features:
        for feature in features:
            lines.append(f"- {feature['pattern_type']} ({feature['direction']}, conf {feature['confidence']})")
    else:
        lines.append("- No salient features.")
    lines.append("")
    lines.append("## Bullish plan summary")
    bullish = fusion.get("bullish_plan_summary", {})
    if bullish:
        lines.append(f"- verdict: {bullish.get('verdict')} / grade {bullish.get('grade')}")
        lines.append(f"- entry: {bullish.get('entry_zone')}")
        lines.append(f"- stop: {bullish.get('invalidation')}")
        lines.append(f"- target: {bullish.get('target')}")
        lines.append(f"- R:R: {bullish.get('risk_reward')}")
    else:
        lines.append("- No bullish candidate.")
    lines.append("")
    lines.append("## Bearish plan summary")
    bearish = fusion.get("bearish_plan_summary", {})
    if bearish:
        lines.append(f"- verdict: {bearish.get('verdict')} / grade {bearish.get('grade')}")
        lines.append(f"- entry: {bearish.get('entry_zone')}")
        lines.append(f"- stop: {bearish.get('invalidation')}")
        lines.append(f"- target: {bearish.get('target')}")
        lines.append(f"- R:R: {bearish.get('risk_reward')}")
    else:
        lines.append("- No bearish candidate.")
    lines.append("")
    lines.append("## Overrides")
    if fusion["overrides"]:
        for override in fusion["overrides"]:
            lines.append(
                f"- {override['source']}: {override['field']} "
                f"{override['old_value']} → {override['new_value']} "
                f"({override['reason']})"
            )
    else:
        lines.append("- No overrides.")
    lines.append("")
    lines.append("## Conflicts")
    if fusion["conflicts"]:
        for conflict in fusion["conflicts"]:
            lines.append(f"- {conflict}")
    else:
        lines.append("- No conflicts.")
    lines.append("")
    lines.append(
        "*This is observability-only output. The deterministic engine still owns all prices."
    )
    return "\n".join(lines)


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
        if args.fusion:
            fusion_payload = _run_fusion_analysis(analysis, df)
            analysis_payload = analysis.model_dump()
            analysis_payload["fusion_observability"] = fusion_payload
            write_json(output_dir / "analysis.json", analysis_payload)
            (output_dir / "fusion.md").write_text(
                _build_fusion_markdown(fusion_payload), encoding="utf-8"
            )
        if args.vision:
            vision_data = json.loads(Path(args.vision).read_text(encoding="utf-8"))
            recon = reconcile(analysis.model_dump(), vision_data)
            write_json(output_dir / "reconciliation.json", recon)
            (output_dir / "reconciliation.md").write_text(render_markdown(recon), encoding="utf-8")
        if args.image:
            render_screenshot_review(args.image, analysis, str(output_dir / "screenshot_review.png"))
    else:
        analysis = screenshot_only_result(args.symbol, args.timeframe, args.bias, args.notes)
        write_json(output_dir / "analysis.json", analysis.model_dump())
        (output_dir / "trade_plan.md").write_text(build_trade_plan_markdown(analysis), encoding="utf-8")
        render_screenshot_review(args.image, analysis, str(output_dir / "screenshot_review.png"))


if __name__ == "__main__":
    main()
