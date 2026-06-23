from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from smc_desk.case_audit import audit_case
from smc_desk.rules import RuleConfig
from tools.build_perception_gold_batch import build_batch, reviewer_payload, select_decision_indices


def candles(count: int = 600) -> pd.DataFrame:
    close = [100.0 + index * 0.03 for index in range(count)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=count, freq="15min"),
            "open": close,
            "high": [value + 0.4 for value in close],
            "low": [value - 0.4 for value in close],
            "close": [value + 0.1 for value in close],
            "volume": [1_000.0] * count,
        }
    )


class PerceptionGoldBatchTests(unittest.TestCase):
    def test_selects_chronological_unique_decision_indices(self) -> None:
        indexes = select_decision_indices(1_000, 5, 400)
        self.assertEqual(indexes[0], 400)
        self.assertEqual(indexes[-1], 999)
        self.assertEqual(len(indexes), len(set(indexes)))

    def test_reviewer_payload_is_draft_and_identified(self) -> None:
        payload = reviewer_payload("case-one", "reviewer_a")
        annotations = payload["perception_annotations"]
        self.assertEqual(payload["case_id"], "case-one")
        self.assertEqual(annotations["label_status"], "draft")
        self.assertEqual(annotations["reviewer_ids"], ["reviewer_a"])

    def test_generated_case_is_source_aligned_but_not_gold(self) -> None:
        def render_stub(_df, *, symbol: str, timeframe: str, output_path: str) -> None:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")

        with tempfile.TemporaryDirectory() as tmp, patch("tools.build_perception_gold_batch.render_raw_chart", side_effect=render_stub):
            root = Path(tmp)
            source = root / "BTCUSDT.csv"
            candles().to_csv(source, index=False)
            manifest = build_batch(
                [("BTCUSDT", source)],
                output_root=root / "cases",
                cases_per_symbol=1,
                warmup_bars=400,
                chart_bars=100,
                config=RuleConfig(),
                reviewers=["reviewer_a", "reviewer_b"],
            )
            case_path = Path(manifest["cases"][0]["case_path"])
            audit = audit_case(case_path)
            brief = (case_path.parent / "blind_review.md").read_text()
            adjudicated = json.loads((case_path.parent / "adjudicated.json").read_text())

        self.assertTrue(audit["usable_for_machine_research"])
        self.assertFalse(audit["usable_for_perception_evaluation"])
        self.assertNotIn("machine_analysis.json", brief)
        self.assertNotIn("engine overlay", brief.lower())
        self.assertEqual(adjudicated["perception_annotations"]["reviewer_ids"], ["reviewer_a", "reviewer_b"])
        self.assertEqual(adjudicated["perception_annotations"]["label_status"], "draft")


if __name__ == "__main__":
    unittest.main()
