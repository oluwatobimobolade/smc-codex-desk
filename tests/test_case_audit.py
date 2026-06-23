from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smc_desk.case_audit import audit_case_library, write_case_index
from smc_desk.case_library import file_sha256


def write_minimal_case(root: Path, *, review_status: str = "unreviewed") -> Path:
    source_csv = root / "BTCUSD_15m.csv"
    source_csv.write_text("timestamp,open,high,low,close,volume\n2026-01-01T00:00:00,1,2,0.5,1.5,100\n", encoding="utf-8")
    screenshot = root / "shot.png"
    screenshot.write_bytes(b"png-ish")
    case_dir = root / "BTCUSD" / "case_001"
    case_dir.mkdir(parents=True)
    payload = {
        "case_id": "BTCUSD_20260101_000000_test",
        "case_kind": "test",
        "symbol": "BTCUSD",
        "exchange": "BITSTAMP",
        "decision_time": "2026-01-01T00:00:00",
        "data": {
            "source_csv": str(source_csv),
            "source_csv_sha256": file_sha256(source_csv),
            "quality": {
                "gap_count": 0,
                "duplicate_timestamps": 0,
                "nan_ohlc_rows": 0,
            },
        },
        "chart_evidence": {
            "tradingview_symbol": "BITSTAMP:BTCUSD",
            "screenshots": {"15": str(screenshot)},
        },
        "source_alignment": {
            "chart_exchange_matches_ohlcv": True,
        },
        "machine_analysis": {
            "trade_plan": {
                "verdict": "Watch",
                "setup_grade": "B",
                "direction": "bearish",
                "risk_pct": 0.0,
                "confluence_score": 0.62,
                "checklist": {"directional_bias": True, "price_at_or_near_poi": False},
            }
        },
        "expert_label": {
            "review_status": review_status,
        },
    }
    case_path = case_dir / "case.json"
    case_path.write_text(json.dumps(payload), encoding="utf-8")
    return case_path


class CaseAuditTests(unittest.TestCase):
    def test_unreviewed_verified_case_is_research_ok_not_training_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_case(root, review_status="unreviewed")

            audit = audit_case_library(root)
            case = audit["cases"][0]

            self.assertTrue(case["usable_for_machine_research"])
            self.assertFalse(case["usable_for_training"])
            self.assertFalse(case["usable_for_perception_evaluation"])
            self.assertIn("unreviewed", case["warnings"])
            self.assertEqual(audit["summary"]["usable_for_training"], 0)

    def test_gold_standard_case_is_training_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_case(root, review_status="gold_standard")

            audit = audit_case_library(root)
            case = audit["cases"][0]

            self.assertTrue(case["usable_for_machine_research"])
            self.assertTrue(case["usable_for_training"])
            self.assertEqual(audit["summary"]["gold_standard_cases"], 1)

    def test_writes_index_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_case(root)

            paths = write_case_index(root)

            self.assertTrue(paths["index_json"].exists())
            self.assertTrue(paths["index_md"].exists())
            self.assertIn("SMC Case Library Index", paths["index_md"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
