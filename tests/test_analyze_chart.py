"""Tests for tools/analyze_chart.py."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.analyze_chart import _build_fusion_markdown, _run_fusion_analysis
from smc_desk.models import AnalysisResult, TradePlan


class AnalyzeChartFusionTests(unittest.TestCase):
    """Tests for the optional Fusion Engine integration in analyze_chart."""

    def _make_df(self, bars: int = 60) -> list[dict]:
        rows = []
        price = 100.0
        for i in range(bars):
            open_p = price
            close = price + (-1 if i % 2 else 1) * 0.3
            high = max(open_p, close) + 0.2
            low = min(open_p, close) - 0.2
            rows.append(
                {
                    "timestamp": f"2024-01-01T00:{i:02d}:00",
                    "open": open_p,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 1.0,
                }
            )
            price = close
        return rows

    def _make_analysis(self) -> AnalysisResult:
        return AnalysisResult(
            symbol="EURUSD",
            timeframe="15m",
            input_type="ohlcv",
            generated_at="2024-01-01T00:00:00",
            metrics={},
            session_context={},
            trade_plan=TradePlan(
                direction="bullish",
                verdict="Execute",
                confidence=0.8,
                thesis="synthetic",
            ),
        )

    def test_run_fusion_analysis_returns_expected_keys(self) -> None:
        import pandas as pd

        df = pd.DataFrame(self._make_df(80))
        analysis = self._make_analysis()
        payload = _run_fusion_analysis(analysis, df)

        self.assertIn("sequence", payload)
        self.assertIn("visual_patterns", payload)
        self.assertIn("intent", payload)
        self.assertIn("fusion", payload)
        self.assertIn("primary_intent", payload["intent"])
        self.assertIn("recommended_verdict", payload["fusion"])

    def test_build_fusion_markdown_contains_overrides_section(self) -> None:
        payload = {
            "sequence": {"narrative": "Test narrative."},
            "intent": {
                "primary_intent": "chop",
                "confidence": 0.5,
            },
            "fusion": {
                "engine_primary_verdict": "Execute",
                "engine_primary_bias": "bullish",
                "recommended_verdict": "Watch",
                "recommended_direction": "neutral",
                "fused_confidence": 0.6,
                "contested": True,
                "scores": {"bullish": 0.45, "bearish": 0.45},
                "bullish_plan_summary": {
                    "direction": "bullish",
                    "verdict": "Execute",
                    "grade": "A",
                    "entry_zone": "100.00000 - 100.50000",
                    "invalidation": 99.5,
                    "target": 103.0,
                    "risk_reward": 3.0,
                },
                "bearish_plan_summary": {
                    "direction": "bearish",
                    "verdict": "Pass",
                    "grade": "C",
                    "entry_zone": "N/A",
                    "invalidation": None,
                    "target": None,
                    "risk_reward": None,
                },
                "overrides": [
                    {
                        "source": "intent",
                        "field": "verdict",
                        "old_value": "Execute",
                        "new_value": "Watch",
                        "reason": "conflict",
                    }
                ],
                "conflicts": ["engine vs intent"],
            },
        }
        md = _build_fusion_markdown(payload)
        self.assertIn("Fusion Engine Observability", md)
        self.assertIn("Test narrative.", md)
        self.assertIn("Execute → Watch", md)
        self.assertIn("engine vs intent", md)

    def test_cli_fusion_flag_writes_fusion_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ohlcv = tmp_path / "bars.csv"
            rows = ["timestamp,open,high,low,close,volume"]
            for i in range(80):
                hour = i // 60
                minute = i % 60
                rows.append(
                    f"2024-01-01T{hour:02d}:{minute:02d}:00,100.0,100.5,99.5,100.1,1.0"
                )
            ohlcv.write_text("\n".join(rows))
            output_dir = tmp_path / "out"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/analyze_chart.py",
                    "--ohlcv",
                    str(ohlcv),
                    "--symbol",
                    "EURUSD",
                    "--timeframe",
                    "15m",
                    "--output-dir",
                    str(output_dir),
                    "--fusion",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "fusion.md").exists())
            analysis = json.loads((output_dir / "analysis.json").read_text())
            self.assertIn("fusion_observability", analysis)
            self.assertIn("fusion", analysis["fusion_observability"])

    def test_cli_without_fusion_flag_omits_fusion_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ohlcv = tmp_path / "bars.csv"
            rows = ["timestamp,open,high,low,close,volume"]
            for i in range(80):
                hour = i // 60
                minute = i % 60
                rows.append(
                    f"2024-01-01T{hour:02d}:{minute:02d}:00,100.0,100.5,99.5,100.1,1.0"
                )
            ohlcv.write_text("\n".join(rows))
            output_dir = tmp_path / "out"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/analyze_chart.py",
                    "--ohlcv",
                    str(ohlcv),
                    "--symbol",
                    "EURUSD",
                    "--timeframe",
                    "15m",
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((output_dir / "fusion.md").exists())
            analysis = json.loads((output_dir / "analysis.json").read_text())
            self.assertNotIn("fusion_observability", analysis)


if __name__ == "__main__":
    unittest.main()
