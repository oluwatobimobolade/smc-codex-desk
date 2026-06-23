from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.paper_trade_journal import journal_summary, mark_filled, record_analysis, settle


def analysis(verdict: str, *, risk_pct: float = 0.0) -> dict:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source": {"decision_time": "2026-01-01T00:00:00+00:00"},
        "metrics": {"latest_close": 100.0},
        "trade_plan": {
            "verdict": verdict,
            "setup_grade": "A",
            "direction": "bullish",
            "entry_type": "confirmation",
            "risk_pct": risk_pct,
            "entry_low": 99.0,
            "entry_high": 101.0,
            "invalidation": 95.0,
            "targets": [110.0],
            "risk_reward": 2.0,
            "confluence_score": 0.9,
            "warnings": [],
        },
    }


class PaperTradeJournalTests(unittest.TestCase):
    def test_watch_is_observation_not_paper_trade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "watch.json"
            source.write_text(json.dumps(analysis("Watch")))
            result = record_analysis(root / "ledger.json", source)
        self.assertTrue(result["created"])
        self.assertEqual(result["record"]["state"], "observed_watch")
        self.assertEqual(result["summary"]["settled_paper_trades"], 0)

    def test_execute_requires_fill_before_settlement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "execute.json"
            source.write_text(json.dumps(analysis("Execute", risk_pct=1.0)))
            ledger = root / "ledger.json"
            record = record_analysis(ledger, source)["record"]
            with self.assertRaisesRegex(ValueError, "inside the recorded entry zone"):
                mark_filled(ledger, record["record_id"], 102.0)
            mark_filled(ledger, record["record_id"], 100.0)
            settled = settle(ledger, record["record_id"], "win", 2.0)
        self.assertEqual(settled["summary"]["settled_paper_trades"], 1)
        self.assertEqual(settled["summary"]["total_r"], 2.0)

    def test_recording_same_analysis_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "watch.json"
            source.write_text(json.dumps(analysis("Watch")))
            ledger = root / "ledger.json"
            first = record_analysis(ledger, source)
            second = record_analysis(ledger, source)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["summary"]["observations"], 1)


if __name__ == "__main__":
    unittest.main()
