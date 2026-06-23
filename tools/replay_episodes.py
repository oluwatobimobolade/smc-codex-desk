#!/usr/bin/env python3
"""Replay closed-candle price action through the SMC fusion layers.

This tool is observability only. It records episode transitions, visual
patterns, detected intents, and fusion verdicts without creating or
simulating trades.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.sequence_memory import BarSnapshot, SequenceMemory
from smc_desk.features import detect_failed_breakout, detect_vertical_spike_trap
from smc_desk.intent_detector import IntentDetector, MarketContext
from smc_desk.fusion_engine import FusionEngine
from smc_desk.models import AnalysisResult, TradePlan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay OHLCV through the SMC fusion layers."
    )
    parser.add_argument("--ohlcv", required=True, help="Path to OHLCV CSV.")
    parser.add_argument("--symbol", required=True, help="Symbol label.")
    parser.add_argument("--max-bars", type=int, default=1000, help="Closed candles to replay after warmup.")
    parser.add_argument("--warmup-bars", type=int, default=50, help="Initial bars skipped before episode detection starts.")
    parser.add_argument("--visual-window", type=int, default=120, help="Bars used for the Visual Cortex render.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--engine-bias", default="neutral", choices=["bullish", "bearish", "neutral"], help="Synthetic engine bias for fusion replay.")
    parser.add_argument("--engine-verdict", default="Watch", choices=["Pass", "Watch", "Execute"], help="Synthetic engine verdict for fusion replay.")
    parser.add_argument("--engine-confidence", type=float, default=0.6, help="Synthetic engine confidence for fusion replay.")
    parser.add_argument("--news-event", action="store_true", help="Inject a high-impact news event context for replay.")
    parser.add_argument("--news-time", type=int, help="Bar index at which the news event occurs.")
    return parser.parse_args()


def _load_ohlcv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    return df


def _row_to_snapshot(index: int, row: pd.Series) -> BarSnapshot:
    return BarSnapshot(
        index=index,
        timestamp=str(row.get("timestamp", index)),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
    )


def _run_replay(args: argparse.Namespace) -> dict[str, Any]:
    df = _load_ohlcv(args.ohlcv)
    df = df.iloc[: args.warmup_bars + args.max_bars].reset_index(drop=True)

    memory = SequenceMemory()
    intent_detector = IntentDetector()
    fusion = FusionEngine()
    context = MarketContext()

    transitions: list[dict[str, Any]] = []
    features_log: list[dict[str, Any]] = []
    intent_log: list[dict[str, Any]] = []
    fusion_log: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        snapshot = _row_to_snapshot(idx, row)
        memory.process_bar(snapshot)

        if idx >= args.warmup_bars:
            if args.news_event and args.news_time is not None and idx == args.news_time:
                # Mark the next major news event as imminent so the distortion rule fires.
                context.minutes_to_next_major_news = 0.0

            if idx % 5 == 0 and idx >= args.visual_window:
                window_records = df.iloc[idx - args.visual_window : idx + 1].to_dict("records")
                spike = detect_vertical_spike_trap(window_records)
                failed_breakout = detect_failed_breakout(window_records)
                if spike.get("detected"):
                    features_log.append({
                        "bar_index": idx,
                        "pattern_type": "vertical_spike_trap",
                        "direction": spike["direction"],
                        "confidence": spike["score"],
                        "metadata": spike.get("metadata", {}),
                    })
                if failed_breakout.get("detected"):
                    features_log.append({
                        "bar_index": idx,
                        "pattern_type": "failed_breakout",
                        "direction": failed_breakout["direction"],
                        "confidence": failed_breakout["score"],
                        "metadata": failed_breakout.get("metadata", {}),
                    })

            if idx % 5 == 0:
                recent_features = [f for f in features_log if f["bar_index"] >= idx - args.visual_window]
                intent_result = intent_detector.detect_intent(
                    sequence_memory=memory,
                    visual_patterns=recent_features[-10:],
                    context=context,
                )
                intents = intent_result.matches
                if intents:
                    intent_log.append(
                        {
                            "bar_index": idx,
                            "timestamp": snapshot.timestamp,
                            "intents": [i.to_dict() for i in intents],
                            "primary": intent_result.to_dict(),
                        }
                    )

                engine_result = AnalysisResult(
                    symbol=args.symbol,
                    timeframe="15m",
                    input_type="ohlcv",
                    generated_at=str(snapshot.timestamp),
                    metrics={},
                    session_context={},
                    trade_plan=TradePlan(
                        direction=args.engine_bias,
                        verdict=args.engine_verdict,
                        confidence=args.engine_confidence,
                        thesis="synthetic engine verdict for replay",
                    ),
                )
                fusion_result = fusion.fuse(
                    engine_result=engine_result,
                    sequence_memory=memory,
                    intent_result=intent_result,
                    visual_patterns=recent_features[-10:],
                )
                fusion_log.append(
                    {
                        "bar_index": idx,
                        "timestamp": snapshot.timestamp,
                        "result": fusion_result.to_dict(),
                    }
                )

            if memory.episodes and memory.episodes[-1].end_bar == idx:
                transitions.append(
                    {
                        "bar_index": idx,
                        "timestamp": snapshot.timestamp,
                        "episode": memory.episodes[-1].to_dict(),
                        "narrative": memory.get_current_narrative(),
                    }
                )

    return {
        "meta": {
            "symbol": args.symbol,
            "ohlcv": str(Path(args.ohlcv).resolve()),
            "warmup_bars": args.warmup_bars,
            "max_bars": args.max_bars,
            "visual_window": args.visual_window,
            "total_bars": len(df),
        },
        "final_state": {
            "episodes": [ep.to_dict() for ep in memory.episodes],
            "active_episode": memory.active_episode.to_dict() if memory.active_episode else None,
            "narrative": memory.get_current_narrative(),
        },
        "transitions": transitions,
        "features": features_log,
        "intents": intent_log,
        "fusion": fusion_log,
    }


def main() -> int:
    args = parse_args()
    result = _run_replay(args)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    print(f"Wrote replay log to {output_path}")
    print(f"Episodes: {len(result['final_state']['episodes'])}")
    print(f"Transitions: {len(result['transitions'])}")
    print(f"Features: {len(result['features'])}")
    print(f"Intent samples: {len(result['intents'])}")
    print(f"Fusion samples: {len(result['fusion'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
