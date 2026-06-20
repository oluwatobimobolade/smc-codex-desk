from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smc_desk.tradingview_overlay import build_tradingview_pine_overlay, write_tradingview_overlay


def minimal_case() -> dict:
    return {
        "case_id": "BTCUSD_20260101_000000_test",
        "symbol": "BTCUSD",
        "exchange": "BITSTAMP",
        "decision_time": "2026-01-01T00:00:00",
        "machine_analysis": {
            "zones": [
                {
                    "label": "Bearish FVG",
                    "kind": "fvg",
                    "direction": "bearish",
                    "low": 101.0,
                    "high": 102.0,
                    "status": "fresh",
                    "score": 0.8,
                },
                {
                    "label": "Equal Lows",
                    "kind": "liquidity",
                    "direction": "bullish",
                    "low": 95.0,
                    "high": 95.2,
                    "status": "fresh",
                    "score": 0.7,
                },
            ],
            "events": [
                {
                    "label": "BOS",
                    "direction": "bearish",
                    "timestamp": "2026-01-01T00:00:00",
                    "price": 99.0,
                },
                {
                    "label": "Liquidity Sweep",
                    "direction": "bearish",
                    "timestamp": "2026-01-01T00:15:00",
                    "price": 103.0,
                },
            ],
            "trade_plan": {
                "selected_poi": {
                    "label": "Bearish FVG",
                    "kind": "fvg",
                    "direction": "bearish",
                    "low": 101.0,
                    "high": 102.0,
                    "status": "fresh",
                    "score": 0.8,
                },
                "invalidation": 103.0,
                "targets": [95.0],
                "liquidity_target": 95.0,
            },
        },
    }


class TradingViewOverlayTests(unittest.TestCase):
    def test_builds_pine_overlay_with_deterministic_guardrail(self) -> None:
        pine, stats = build_tradingview_pine_overlay(minimal_case())

        self.assertIn("//@version=6", pine)
        self.assertIn('indicator("SMC Desk Overlay - BTCUSD"', pine)
        self.assertIn("box.new", pine)
        self.assertIn("line.new", pine)
        self.assertIn("label.new", pine)
        self.assertIn("should not invent extra levels", pine)
        self.assertGreaterEqual(stats.boxes, 2)
        self.assertGreaterEqual(stats.lines, 3)
        self.assertGreaterEqual(stats.labels, 5)

    def test_writes_overlay_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_path = root / "case.json"
            case_path.write_text(json.dumps(minimal_case()), encoding="utf-8")

            manifest = write_tradingview_overlay(case_path)

            pine_path = Path(manifest["pine_path"])
            manifest_path = pine_path.with_suffix(".manifest.json")
            self.assertTrue(pine_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertEqual(manifest["boxes"], 2)


if __name__ == "__main__":
    unittest.main()
