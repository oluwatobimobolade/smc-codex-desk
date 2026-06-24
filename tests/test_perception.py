from __future__ import annotations

import unittest

from smc_desk.perception_legacy import (
    PerceptionAnnotation,
    PerceptionAnnotationSet,
    annotation_match_score,
    engine_perception_objects,
    greedy_match_annotations,
)


class PerceptionContractTests(unittest.TestCase):
    def test_event_requires_time_and_price(self) -> None:
        with self.assertRaises(ValueError):
            PerceptionAnnotation(annotation_id="missing", primitive="bos")

    def test_adjudicated_set_requires_reviewer_and_adjudicator(self) -> None:
        with self.assertRaises(ValueError):
            PerceptionAnnotationSet(label_status="adjudicated")

    def test_event_matching_rejects_wrong_time_or_price(self) -> None:
        truth = PerceptionAnnotation(
            annotation_id="truth-bos",
            primitive="bos",
            direction="bullish",
            timestamp="2026-01-01T10:00:00+00:00",
            price=100.0,
        )
        wrong_time = PerceptionAnnotation(
            annotation_id="engine-late",
            primitive="bos",
            direction="bullish",
            timestamp="2026-01-01T10:30:00+00:00",
            price=100.0,
        )
        wrong_price = PerceptionAnnotation(
            annotation_id="engine-price",
            primitive="bos",
            direction="bullish",
            timestamp="2026-01-01T10:00:00+00:00",
            price=101.0,
        )
        self.assertIsNone(annotation_match_score(truth, wrong_time, time_tolerance_minutes=15, price_tolerance_pct=0.001))
        self.assertIsNone(annotation_match_score(truth, wrong_price, time_tolerance_minutes=15, price_tolerance_pct=0.001))

    def test_zone_matching_requires_meaningful_overlap(self) -> None:
        truth = PerceptionAnnotation(
            annotation_id="truth-fvg",
            primitive="fvg",
            direction="bullish",
            price_low=100.0,
            price_high=110.0,
        )
        overlaps = PerceptionAnnotation(
            annotation_id="engine-fvg",
            primitive="fvg",
            direction="bullish",
            price_low=102.0,
            price_high=112.0,
        )
        misses = PerceptionAnnotation(
            annotation_id="engine-miss",
            primitive="fvg",
            direction="bullish",
            price_low=109.0,
            price_high=120.0,
        )
        self.assertIsNotNone(annotation_match_score(truth, overlaps, min_zone_iou=0.5))
        self.assertIsNone(annotation_match_score(truth, misses, min_zone_iou=0.5))

    def test_greedy_match_does_not_hide_duplicate_engine_detections(self) -> None:
        truth = [
            PerceptionAnnotation(
                annotation_id="truth-sweep",
                primitive="liquidity_sweep",
                direction="bearish",
                timestamp="2026-01-01T10:00:00+00:00",
                price=100.0,
            )
        ]
        machine = [
            PerceptionAnnotation(
                annotation_id="engine-one",
                primitive="liquidity_sweep",
                direction="bearish",
                timestamp="2026-01-01T10:00:00+00:00",
                price=100.0,
            ),
            PerceptionAnnotation(
                annotation_id="engine-two",
                primitive="liquidity_sweep",
                direction="bearish",
                timestamp="2026-01-01T10:00:00+00:00",
                price=100.0,
            ),
        ]
        matches = greedy_match_annotations(truth, machine)
        self.assertEqual(len(matches), 1)

    def test_engine_output_translates_to_object_annotations(self) -> None:
        machine_objects = engine_perception_objects(
            {
                "timeframe": "15m",
                "events": [
                    {
                        "label": "BOS",
                        "direction": "bullish",
                        "timestamp": "2026-01-01T10:00:00+00:00",
                        "price": 100.0,
                        "structure_scope": "swing",
                        "strength": "strong",
                    }
                ],
                "zones": [
                    {
                        "kind": "fvg",
                        "label": "Bullish FVG",
                        "direction": "bullish",
                        "low": 99.0,
                        "high": 101.0,
                        "status": "fresh",
                        "score": 0.9,
                    }
                ],
            }
        )
        self.assertEqual([item.primitive for item in machine_objects], ["bos", "fvg"])


if __name__ == "__main__":
    unittest.main()
