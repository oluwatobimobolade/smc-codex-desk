from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from smc_desk.case_library import file_sha256
from tools.evaluate_perception_gold import evaluate


class PerceptionEvaluatorTests(unittest.TestCase):
    def test_scores_matching_adjudicated_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_csv = root / "BTCUSDT_15m.csv"
            source_csv.write_text("timestamp,open,high,low,close,volume\n2026-01-01T00:00:00,1,2,0.5,1.5,100\n", encoding="utf-8")
            screenshot = root / "chart.png"
            screenshot.write_bytes(b"png")
            case_dir = root / "BTCUSDT" / "gold_case"
            case_dir.mkdir(parents=True)
            case = {
                "case_id": "BTCUSDT_gold_perception",
                "symbol": "BTCUSDT",
                "exchange": "BINANCE",
                "data": {
                    "source_csv": str(source_csv),
                    "source_csv_sha256": file_sha256(source_csv),
                    "quality": {"gap_count": 0, "duplicate_timestamps": 0, "nan_ohlc_rows": 0},
                },
                "chart_evidence": {"tradingview_symbol": "BINANCE:BTCUSDT.P", "screenshots": {"15": str(screenshot)}},
                "source_alignment": {"chart_exchange_matches_ohlcv": True},
                "machine_analysis": {
                    "timeframe": "15m",
                    "events": [
                        {
                            "label": "BOS",
                            "direction": "bullish",
                            "timestamp": "2026-01-01T00:00:00+00:00",
                            "price": 100.0,
                            "structure_scope": "swing",
                            "strength": "strong",
                        }
                    ],
                    "zones": [],
                    "trade_plan": {"verdict": "Pass", "setup_grade": "C", "direction": "neutral", "risk_pct": 0.0, "confluence_score": 0.0, "checklist": {}},
                },
                "expert_label": {
                    "review_status": "gold_standard",
                    "perception_annotations": {
                        "schema_version": "1.0",
                        "label_status": "adjudicated",
                        "reviewer_ids": ["expert-a", "expert-b"],
                        "adjudicated_by": "lead-reviewer",
                        "objects": [
                            {
                                "annotation_id": "truth-bos",
                                "primitive": "bos",
                                "timeframe": "15m",
                                "direction": "bullish",
                                "structure_scope": "swing",
                                "timestamp": "2026-01-01T00:00:00+00:00",
                                "price": 100.0,
                            }
                        ],
                    },
                },
            }
            (case_dir / "case.json").write_text(json.dumps(case), encoding="utf-8")
            args = SimpleNamespace(
                root=str(root),
                min_cases=1,
                event_time_tolerance_minutes=15.0,
                event_price_tolerance_pct=0.001,
                min_zone_iou=0.5,
            )

            report = evaluate(args)

        self.assertEqual(report["status"], "ready_for_measurement")
        self.assertEqual(report["eligible_cases"], 1)
        self.assertEqual(report["per_primitive"]["bos"]["tp"], 1)
        self.assertEqual(report["per_primitive"]["bos"]["f1"], 1.0)


if __name__ == "__main__":
    unittest.main()
