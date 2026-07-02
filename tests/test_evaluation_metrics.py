from smc_desk.evaluation.gold_set import GoldSetLabel
from smc_desk.evaluation.metrics import match_objects


def test_match_objects_counts_tp_fp_fn_for_event_labels():
    gold = [
        GoldSetLabel(
            object_id="gold-bos-1",
            object_type="structure_break",
            annotator_id="human",
            agreed_status="confirmed",
            ground_truth_evidence={
                "direction": "bullish",
                "timestamp": "2026-01-01T12:00:00+00:00",
                "price": 100.0,
            },
        ),
        GoldSetLabel(
            object_id="gold-bos-2",
            object_type="structure_break",
            annotator_id="human",
            agreed_status="confirmed",
            ground_truth_evidence={
                "direction": "bearish",
                "timestamp": "2026-01-01T13:00:00+00:00",
                "price": 90.0,
            },
        ),
    ]
    predictions = [
        {
            "object_type": "structure_break",
            "direction": "bullish",
            "timestamp": "2026-01-01T12:10:00+00:00",
            "price": 100.05,
        },
        {
            "object_type": "structure_break",
            "direction": "bullish",
            "timestamp": "2026-01-01T14:00:00+00:00",
            "price": 120.0,
        },
    ]

    result = match_objects(predictions, gold, time_tolerance_bars=1, price_tolerance_bps=10.0)

    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 1
    assert result.precision == 0.5
    assert result.recall == 0.5


def test_match_objects_uses_zone_iou_for_areas():
    gold = [
        GoldSetLabel(
            object_id="gold-fvg-1",
            object_type="fvg",
            annotator_id="human",
            agreed_status="confirmed",
            ground_truth_evidence={
                "direction": "bullish",
                "timestamp": "2026-01-01T12:00:00+00:00",
                "price_low": 100.0,
                "price_high": 110.0,
            },
        )
    ]
    predictions = [
        {
            "object_type": "fvg",
            "direction": "bullish",
            "timestamp": "2026-01-01T12:00:00+00:00",
            "price_low": 101.0,
            "price_high": 109.0,
        }
    ]

    result = match_objects(predictions, gold)

    assert result.true_positives == 1
    assert result.false_positives == 0
    assert result.false_negatives == 0
