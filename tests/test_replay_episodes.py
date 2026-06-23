"""Tests for the replay_episodes observability tool."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.replay_episodes import _run_replay


class MockArgs:
    """Minimal argparse namespace for _run_replay."""

    def __init__(self, ohlcv: Path, output: Path) -> None:
        self.ohlcv = str(ohlcv)
        self.symbol = "EURUSD"
        self.max_bars = 100
        self.warmup_bars = 10
        self.visual_window = 40
        self.output = str(output)
        self.engine_bias = "bullish"
        self.engine_verdict = "Execute"
        self.engine_confidence = 0.7
        self.news_event = False
        self.news_time = None


class ReplayEpisodesToolTests(unittest.TestCase):
    """Smoke tests for tools/replay_episodes.py."""

    def _make_ohlcv(self, path: Path, bars: int = 120) -> None:
        rows = ["timestamp,open,high,low,close,volume"]
        price = 100.0
        for i in range(bars):
            open_p = price
            close = price + (-1 if i % 2 else 1) * 0.3
            high = max(open_p, close) + 0.2
            low = min(open_p, close) - 0.2
            rows.append(f"{i},{open_p},{high},{low},{close},1.0")
            price = close
        path.write_text("\n".join(rows))

    def test_replay_produces_json_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ohlcv = Path(tmp) / "bars.csv"
            output = Path(tmp) / "replay.json"
            self._make_ohlcv(ohlcv)
            args = MockArgs(ohlcv, output)
            result = _run_replay(args)

            self.assertEqual(result["meta"]["symbol"], "EURUSD")
            self.assertGreater(len(result["final_state"]["episodes"]), 0)
            self.assertIn("transitions", result)
            self.assertIn("intents", result)
            self.assertIn("fusion", result)

            # _run_replay returns the payload; main() writes it. Write here so we
            # can validate the JSON round-trip.
            output.write_text(json.dumps(result))
            parsed = json.loads(output.read_text())
            self.assertEqual(parsed["meta"]["total_bars"], 110)

    def test_replay_with_news_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ohlcv = Path(tmp) / "bars.csv"
            output = Path(tmp) / "replay.json"
            self._make_ohlcv(ohlcv)
            args = MockArgs(ohlcv, output)
            args.news_event = True
            args.news_time = 60
            result = _run_replay(args)

            # Fusion samples should exist after news injection
            self.assertGreater(len(result["fusion"]), 0)


if __name__ == "__main__":
    unittest.main()
