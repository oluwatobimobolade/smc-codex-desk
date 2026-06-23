from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from tools.mark_chart import drop_unclosed_candles, main, validate_live_ohlcv, write_artifacts


def live_candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-22T12:00:00Z", "2026-06-22T12:15:00Z"]),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 12.0],
        }
    )


class MarkChartTests(unittest.TestCase):
    def test_drops_current_unclosed_candle(self) -> None:
        result = drop_unclosed_candles(
            live_candles(),
            "15m",
            now=datetime(2026, 6, 22, 12, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result["timestamp"].iloc[0], pd.Timestamp("2026-06-22T12:00:00Z"))

    def test_live_validation_rejects_invalid_candle_range(self) -> None:
        invalid = live_candles()
        invalid.loc[0, "high"] = 100.5
        with self.assertRaisesRegex(ValueError, "high/low consistency"):
            validate_live_ohlcv(invalid)

    def test_live_validation_rejects_duplicate_timestamps(self) -> None:
        invalid = live_candles()
        invalid.loc[1, "timestamp"] = invalid.loc[0, "timestamp"]
        with self.assertRaisesRegex(ValueError, "ordered and unique"):
            validate_live_ohlcv(invalid)

    def test_artifact_manifest_records_provenance_and_closed_candle_policy(self) -> None:
        analysis = SimpleNamespace(timeframe="15m", model_dump=lambda mode: {"timeframe": "15m"})
        with tempfile.TemporaryDirectory() as tmp, patch("tools.mark_chart.analysis_to_objects", return_value=[]):
            output = Path(tmp) / "BTCUSDT.png"
            write_artifacts(output, analysis, live_candles(), "high", "live_binance_futures_webbridge")
            manifest = json.loads(output.with_suffix(".objects.json").read_text())

        self.assertEqual(manifest["source"], "live_binance_futures_webbridge")
        self.assertTrue(manifest["window"]["closed_candles_only"])
        self.assertEqual(manifest["accuracy_claim"], "none; requires independent adjudicated gold labels")

    def test_live_failure_closes_created_browser_session(self) -> None:
        with (
            patch.object(sys, "argv", ["mark_chart.py", "--symbol", "BTCUSDT", "--source", "live", "--session", "test-session"]),
            patch("tools.mark_chart.require_healthy_bridge"),
            patch("tools.mark_chart.fetch_live", side_effect=RuntimeError("fetch failed")),
            patch("tools.mark_chart._bridge") as bridge,
        ):
            with self.assertRaisesRegex(RuntimeError, "fetch failed"):
                main()

        bridge.assert_called_once_with("close_session", {}, session="test-session")


if __name__ == "__main__":
    unittest.main()
