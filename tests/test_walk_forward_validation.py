from __future__ import annotations

import unittest

from tools.run_walk_forward_validation import chronological_folds, evaluate, reprice_r


def row(symbol: str, index: int, r_multiple: float) -> dict:
    return {
        "symbol": symbol,
        "entry_index": str(index),
        "decision_time": f"2025-01-{index + 1:02d}T00:00:00+00:00",
        "r_target_cost": r_multiple,
    }


class WalkForwardValidationTests(unittest.TestCase):
    def test_reprices_cost_in_r_units(self) -> None:
        value = reprice_r(
            {"r_multiple": "1.0", "entry_price": "100", "risk_per_r": "10", "cost_bps": "4"},
            target_cost_bps=10.0,
        )
        self.assertAlmostEqual(value, 0.994)

    def test_chronological_folds_preserve_order(self) -> None:
        rows = [row("BTCUSDT", index, 0.2) for index in range(6)]
        folds = chronological_folds(rows, 3)
        self.assertEqual([[item["entry_index"] for item in fold] for fold in folds], [["0", "1"], ["2", "3"], ["4", "5"]])

    def test_research_geometry_report_never_promotes_live_edge(self) -> None:
        rows = [row("BTCUSDT", index, 0.5) for index in range(4)] + [row("ETHUSDT", index + 4, 0.5) for index in range(4)]
        report = evaluate(rows, folds=2, min_trades=4, min_positive_folds=2, min_pairs=1, min_trades_per_pair=2)
        self.assertEqual(report["promotion_status"], "NO_GO")
        self.assertTrue(any("not literal Execute" in blocker for blocker in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
