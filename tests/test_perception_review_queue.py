from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smc_desk.case_library import file_sha256
from tools.import_perception_labels import import_labels
from tools.prepare_perception_reviews import prepare_review_queue


class PerceptionReviewQueueTests(unittest.TestCase):
    def test_prepares_and_imports_adjudicated_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "BTCUSDT.csv"
            source.write_text("timestamp,open,high,low,close,volume\n2026-01-01T00:00:00,1,2,0,1,1\n", encoding="utf-8")
            screenshot = root / "chart.png"
            screenshot.write_bytes(b"png")
            case_dir = root / "BTCUSDT" / "case"
            case_dir.mkdir(parents=True)
            case_path = case_dir / "case.json"
            case_path.write_text(
                json.dumps(
                    {
                        "case_id": "BTCUSDT_case",
                        "symbol": "BTCUSDT",
                        "data": {"source_csv": str(source), "source_csv_sha256": file_sha256(source), "quality": {"gap_count": 0, "duplicate_timestamps": 0, "nan_ohlc_rows": 0}},
                        "chart_evidence": {"screenshots": {"15": str(screenshot)}},
                        "source_alignment": {"chart_exchange_matches_ohlcv": True},
                        "expert_label": {"review_status": "unreviewed"},
                    }
                ),
                encoding="utf-8",
            )
            queue_dir = root / "queue"
            manifest = prepare_review_queue(root, queue_dir)
            self.assertEqual(len(manifest["prepared"]), 1)
            labels_path = Path(manifest["prepared"][0]["labels"])
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            labels["perception_annotations"] = {
                "schema_version": "1.0",
                "label_status": "adjudicated",
                "reviewer_ids": ["a", "b"],
                "adjudicated_by": "c",
                "objects": [
                    {
                        "annotation_id": "bos-1",
                        "primitive": "bos",
                        "timeframe": "15m",
                        "direction": "bullish",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "price": 1.0,
                    }
                ],
            }
            labels_path.write_text(json.dumps(labels), encoding="utf-8")
            result = import_labels(case_path, labels_path)

            written = json.loads(case_path.read_text(encoding="utf-8"))
        self.assertEqual(result["annotation_count"], 1)
        self.assertEqual(written["expert_label"]["perception_annotations"]["label_status"], "adjudicated")


if __name__ == "__main__":
    unittest.main()
