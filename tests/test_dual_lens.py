from __future__ import annotations

import unittest

from smc_desk.dual_lens import reconcile


def _engine() -> dict:
    return {
        "metrics": {"latest_close": 100.0, "range_low": 90.0, "range_high": 110.0},
        "trade_plan": {
            "direction": "bearish",
            "verdict": "Watch",
            "setup_grade": "B",
            "confidence": 0.7,
            "confluence_score": 0.62,
            "entry_low": 105.0,
            "entry_high": 106.0,
            "invalidation": 107.0,
            "targets": [95.0],
            "risk_reward": 3.0,
            "selected_poi": {
                "label": "Bearish FVG",
                "low": 105.0,
                "high": 106.0,
            },
        },
    }


class DualLensTests(unittest.TestCase):
    def test_vision_never_overwrites_engine_prices(self) -> None:
        vision = {
            "observed_bias": "bearish",
            "price_location": "below_poi",
            "key_zones_seen": [{"low": 120.0, "high": 130.0}],
            "structure_quality_score": 0.8,
            "tradeable_now": True,
        }

        recon = reconcile(_engine(), vision)

        self.assertEqual(recon["engine"]["entry_zone"], [105.0, 106.0])
        self.assertEqual(recon["engine"]["invalidation"], 107.0)
        self.assertEqual(recon["final_verdict"], "Watch")

    def test_source_mismatch_reduces_confidence_and_adds_conflict(self) -> None:
        aligned = {
            "observed_bias": "bearish",
            "price_location": "below_poi",
            "key_zones_seen": [{"low": 105.0, "high": 106.0}],
            "structure_quality_score": 0.8,
            "source_aligned": True,
        }
        mismatched = {**aligned, "source_aligned": False}

        aligned_recon = reconcile(_engine(), aligned, vision_authority_mode="calibrated_veto")
        mismatched_recon = reconcile(_engine(), mismatched, vision_authority_mode="calibrated_veto")

        self.assertLess(mismatched_recon["combined_confidence"], aligned_recon["combined_confidence"])
        self.assertTrue(any("source mismatch" in item for item in mismatched_recon["conflicts"]))


if __name__ == "__main__":
    unittest.main()
