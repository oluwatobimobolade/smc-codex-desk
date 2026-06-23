from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smc_desk.tradingview_overlay import build_tradingview_pine_overlay, write_tradingview_overlay
from smc_desk.visual_geometry import zone_visual_key


def minimal_case() -> dict:
    case = {
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
                    "index": 3,
                    "timestamp": "2026-01-01T00:00:00",
                    "price": 99.0,
                    "broken_level": 99.0,
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
    zones = case["machine_analysis"]["zones"]
    case["visual_geometry"] = {
        "as_of": "2026-01-01T00:00:00",
        "zones": [
            {
                "key": zone_visual_key(zones[0]),
                "activation_time": "2025-12-31T22:00:00Z",
                "end_time": "2026-01-01T00:00:00Z",
                "state": "fresh",
                "active": True,
            },
            {
                "key": zone_visual_key(zones[1]),
                "activation_time": "2025-12-31T23:00:00Z",
                "end_time": "2026-01-01T00:00:00Z",
                "state": "fresh",
                "active": True,
            },
        ],
        "structure_segments": [
            {
                "event_index": 3,
                "event_label": "BOS",
                "start_time": "2025-12-31T23:15:00Z",
                "end_time": "2026-01-01T00:00:00Z",
                "price": 99.0,
            }
        ],
        "plan": {"actionable": False},
    }
    return case


class TradingViewOverlayTests(unittest.TestCase):
    def test_builds_pine_overlay_with_deterministic_guardrail(self) -> None:
        pine, stats = build_tradingview_pine_overlay(minimal_case())

        self.assertIn("//@version=6", pine)
        self.assertIn('indicator("SMC Desk Overlay - BTCUSD"', pine)
        self.assertIn("box.new", pine)
        self.assertIn("line.new", pine)
        self.assertIn("label.new", pine)
        self.assertIn("should not invent extra levels", pine)
        self.assertNotIn("extend = extend.right", pine)
        self.assertNotIn("three days", pine)
        self.assertIn("left = 1767218400000", pine)
        self.assertIn("right = 1767225600000", pine)
        self.assertNotIn("Execution SL", pine)
        self.assertEqual(stats.boxes, 2)
        self.assertEqual(stats.lines, 1)
        self.assertEqual(stats.labels, 2)

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

    def test_limits_snapshot_to_six_highest_priority_active_zones(self) -> None:
        case = minimal_case()
        for index in range(7):
            zone = {
                "label": f"Bullish FVG {index}",
                "kind": "fvg",
                "direction": "bullish",
                "low": 110.0 + index,
                "high": 111.0 + index,
                "status": "fresh",
                "score": 0.9 - index * 0.01,
                "start_index": index,
                "end_index": index + 1,
            }
            case["machine_analysis"]["zones"].append(zone)
            case["visual_geometry"]["zones"].append(
                {
                    "key": zone_visual_key(zone),
                    "activation_time": "2025-12-31T22:00:00Z",
                    "end_time": "2026-01-01T00:00:00Z",
                    "state": "fresh",
                    "active": True,
                    "display_confidence": "high",
                }
            )

        _pine, stats = build_tradingview_pine_overlay(case)

        self.assertEqual(stats.boxes, 6)


if __name__ == "__main__":
    unittest.main()
