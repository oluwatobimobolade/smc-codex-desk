from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from smc_desk.case_library import build_case_payload, write_case_files
from smc_desk.rules import RuleConfig


def sample_ohlcv(rows: int = 520) -> pd.DataFrame:
    base = 100.0
    candles = []
    for i in range(rows):
        drift = i * 0.04
        wave = (i % 20) * 0.03
        open_ = base + drift + wave
        close = open_ + (0.08 if i % 3 else -0.06)
        high = max(open_, close) + 0.25
        low = min(open_, close) - 0.25
        candles.append((open_, high, low, close))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="15min"),
            "open": [row[0] for row in candles],
            "high": [row[1] for row in candles],
            "low": [row[2] for row in candles],
            "close": [row[3] for row in candles],
            "volume": [1000.0 for _ in candles],
        }
    )


class CaseLibraryTests(unittest.TestCase):
    def test_builds_case_payload_and_review_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "BTCUSD_15m.csv"
            df = sample_ohlcv()
            df.to_csv(csv_path, index=False)

            screenshot_meta = {
                "instrument": "BTCUSD",
                "exchange": "BITSTAMP",
                "tradingview_symbol": "BITSTAMP:BTCUSD",
                "captured_at": "2026-01-06T09:45:00+00:00",
                "screenshots": {"1D": "/tmp/1d.png", "4H": "/tmp/4h.png", "1H": "/tmp/1h.png", "15": "/tmp/15.png"},
            }
            payload = build_case_payload(
                symbol="BTCUSD",
                exchange="BITSTAMP",
                ohlcv_path=csv_path,
                df=df,
                config=RuleConfig(lookback_bars=250),
                screenshot_meta=screenshot_meta,
                case_kind="test_case",
            )

            self.assertEqual(payload["symbol"], "BTCUSD")
            self.assertEqual(payload["source_alignment"]["chart_exchange_matches_ohlcv"], True)
            self.assertIn("source_csv_sha256", payload["data"])
            self.assertEqual(payload["data"]["quality"]["gap_count"], 0)
            self.assertIn("machine_analysis", payload)
            self.assertIn("zones", payload["visual_geometry"])
            self.assertIn("structure_segments", payload["visual_geometry"])
            self.assertEqual(payload["expert_label"]["review_status"], "unreviewed")
            self.assertEqual(payload["expert_label"]["perception_annotations"]["label_status"], "missing")

            out_dir = tmp_path / "case"
            paths = write_case_files(out_dir, payload)

            self.assertTrue(paths["case_json"].exists())
            self.assertTrue(paths["machine_report"].exists())
            self.assertTrue(paths["human_label"].exists())
            self.assertTrue(paths["review_packet"].exists())
            written = json.loads(paths["case_json"].read_text(encoding="utf-8"))
            self.assertEqual(written["case_version"], "1.2")
            self.assertIn("Expert Read", paths["human_label"].read_text(encoding="utf-8"))
            self.assertIn("Chart Evidence", paths["review_packet"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
