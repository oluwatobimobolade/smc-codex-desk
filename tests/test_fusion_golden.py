"""Golden-output determinism test for the Fusion Engine.

The fusion stack must be byte-identically reproducible on a frozen fixture.
This catches unseeded randomness, LLM calls, timestamp dependencies, and
non-deterministic visual/feature extraction.
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
from smc_desk.visual_cortex import VisualCortex, render_chart_for_visual_cortex


GOLDEN_PATH = ROOT / "tests" / "fixtures" / "fusion_golden.json"


def _make_fixture_df() -> pd.DataFrame:
    rows = []
    price = 100.0
    for i in range(80):
        hour, minute = i // 60, i % 60
        open_p = price
        close = price + (-1 if i % 2 else 1) * 0.3
        high = max(open_p, close) + 0.2
        low = min(open_p, close) - 0.2
        rows.append({
            "timestamp": f"2026-01-01T{hour:02d}:{minute:02d}:00",
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
        })
        price = close
    return pd.DataFrame(rows)


def _run_fusion(df: pd.DataFrame) -> dict:
    config = RuleConfig()
    engine_result, _ = analyze_dataframe(df, "TEST", "15m", config)

    mem = SequenceMemory()
    for idx, row in df.iterrows():
        mem.process_bar(
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

    visual = VisualCortex()
    window_records = df.iloc[-60:].to_dict("records")
    img, _regions, _ = render_chart_for_visual_cortex(window_records)
    patterns = visual.analyze_image(img)
    pattern_dicts = [p.to_dict() for p in patterns]

    detector = IntentDetector()
    intent_result = detector.detect_intent(
        sequence_memory=mem,
        visual_patterns=pattern_dicts,
        context=MarketContext(symbol="TEST", timeframe="15m"),
    )

    fusion = FusionEngine()
    result = fusion.fuse(
        engine_result=engine_result,
        sequence_memory=mem,
        intent_result=intent_result,
        visual_patterns=pattern_dicts,
    )
    return result.to_dict()


class FusionGoldenOutputTests(unittest.TestCase):
    """Pin the fusion output on a frozen fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.df = _make_fixture_df()
        cls.generated = _run_fusion(cls.df)

    def test_fusion_output_is_deterministic(self) -> None:
        """Running the same fixture twice must produce identical output."""
        second_run = _run_fusion(self.df)
        self.assertEqual(self.generated, second_run)

    def test_fusion_output_matches_snapshot(self) -> None:
        """If a snapshot exists, the output must match it exactly."""
        if not GOLDEN_PATH.exists():
            self.skipTest(f"No golden snapshot at {GOLDEN_PATH}; run with --update-golden to create one.")
        snapshot = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(self.generated, snapshot)


if __name__ == "__main__":
    # Allow manual snapshot creation: python tests/test_fusion_golden.py --update-golden
    if "--update-golden" in sys.argv:
        sys.argv.remove("--update-golden")
        df = _make_fixture_df()
        snapshot = _run_fusion(df)
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Updated golden snapshot at {GOLDEN_PATH}")
    else:
        unittest.main()
