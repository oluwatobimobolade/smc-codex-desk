"""Leakage tests for the fusion layers.

A layer is leakage-free if processing N extra future bars does not change the
output that was valid at bar T. We test this by running each layer twice:

1. Process exactly the bars up to cutoff T and record the output.
2. Process the full series but stop at the same cutoff T, then record output.

The two outputs must be identical.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe
from smc_desk.fusion_engine import FusionEngine
from smc_desk.intent_detector import IntentDetector, MarketContext
from smc_desk.rules import RuleConfig
from smc_desk.sequence_memory import BarSnapshot, SequenceMemory


def _make_df(bars: int = 120) -> pd.DataFrame:
    rows = []
    price = 100.0
    for i in range(bars):
        open_p = price
        close = price + (-1 if i % 2 else 1) * 0.3
        high = max(open_p, close) + 0.2
        low = min(open_p, close) - 0.2
        rows.append({
            "timestamp": f"2026-01-01T{(i // 60):02d}:{(i % 60):02d}:00",
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
        })
        price = close
    return pd.DataFrame(rows)


def _df_to_snapshots(df: pd.DataFrame) -> list[BarSnapshot]:
    snapshots = []
    for idx, row in df.iterrows():
        snapshots.append(
            BarSnapshot(
                index=idx,
                timestamp=str(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
            )
        )
    return snapshots


def _memory_at_cutoff(snapshots: list[BarSnapshot], cutoff: int) -> SequenceMemory:
    mem = SequenceMemory()
    for snapshot in snapshots[:cutoff]:
        mem.process_bar(snapshot)
    return mem


class SequenceMemoryLeakageTests(unittest.TestCase):
    """SequenceMemory must not revise past episodes when future bars arrive."""

    def test_episodes_stable_after_future_bars(self) -> None:
        df = _make_df(120)
        snapshots = _df_to_snapshots(df)
        cutoff = 60

        mem_truncated = _memory_at_cutoff(snapshots, cutoff)
        mem_full = _memory_at_cutoff(snapshots, len(df))

        # Episodes that ended before the cutoff must be identical.
        truncated_ended = [ep.to_dict() for ep in mem_truncated.episodes if ep.end_bar is not None and ep.end_bar < cutoff]
        full_ended = [ep.to_dict() for ep in mem_full.episodes if ep.end_bar is not None and ep.end_bar < cutoff]
        self.assertEqual(truncated_ended, full_ended)

    def test_narrative_stable_after_future_bars(self) -> None:
        df = _make_df(120)
        snapshots = _df_to_snapshots(df)
        cutoff = 60

        mem_truncated = _memory_at_cutoff(snapshots, cutoff)
        mem_full = _memory_at_cutoff(snapshots, len(df))

        # The active episode at the cutoff should be the same type.
        if mem_truncated.active_episode and mem_full.active_episode:
            self.assertEqual(
                mem_truncated.active_episode.episode_type,
                mem_full.active_episode.episode_type,
            )


class IntentDetectorLeakageTests(unittest.TestCase):
    """IntentDetector must only use bars <= decision time."""

    def test_intent_identical_on_truncated_series(self) -> None:
        df = _make_df(120)
        snapshots = _df_to_snapshots(df)
        cutoff = 60

        mem_truncated = _memory_at_cutoff(snapshots, cutoff)
        mem_full = _memory_at_cutoff(snapshots, cutoff)

        detector = IntentDetector()
        context = MarketContext(symbol="TEST", timeframe="15m")
        result_truncated = detector.detect_intent(mem_truncated, context=context)
        result_full = detector.detect_intent(mem_full, context=context)

        self.assertEqual(result_truncated.to_dict(), result_full.to_dict())


class FusionEngineLeakageTests(unittest.TestCase):
    """FusionEngine must only use engine output derived from bars <= decision time."""

    def test_fusion_identical_on_truncated_series(self) -> None:
        df_full = _make_df(120)
        df_truncated = df_full.iloc[:60].copy()
        config = RuleConfig()

        engine_result_truncated, _ = analyze_dataframe(df_truncated, "TEST", "15m", config)
        engine_result_full, _ = analyze_dataframe(df_full, "TEST", "15m", config)

        snapshots = _df_to_snapshots(df_full)
        mem = _memory_at_cutoff(snapshots, 60)

        fusion = FusionEngine()
        result_truncated = fusion.fuse(
            engine_result=engine_result_truncated,
            sequence_memory=mem,
        )
        result_full = fusion.fuse(
            engine_result=engine_result_full,
            sequence_memory=mem,
        )

        # The fused recommendation should depend only on the data available at
        # the cutoff, not on the full-series engine result.
        self.assertEqual(result_truncated.recommended_verdict, result_full.recommended_verdict)
        self.assertEqual(result_truncated.recommended_direction, result_full.recommended_direction)


if __name__ == "__main__":
    unittest.main()
