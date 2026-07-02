from __future__ import annotations

from smc_desk.decision.execution_readiness import evaluate_execution_readiness
from smc_desk.decision.inducement_continuation_classifier import classify_inducement_continuation
from smc_desk.decision.watch_state_engine import evaluate_watch_state


def test_15m_choch_alone_cannot_create_signal_without_htf_poi_context():
    watch = evaluate_watch_state(
        hierarchy_by_tf={
            "4h": {"external_bias": "bearish"},
            "1h": {"external_bias": "bearish"},
            "15m": {"external_bias": "bearish"},
        },
        roles={"notes": ["15m bearish CHoCH is entry-confirmation only."]},
        pois_by_tf={},
    ).to_dict()

    assessment = classify_inducement_continuation(
        perception_by_tf={
            "15m": {
                "last_price": "60120",
                "structure_breaks": [
                    {"object_id": "internal_choch_down", "direction": "bearish", "break_type": "CHOCH"}
                ],
                "order_blocks": [],
                "fvgs": [],
            }
        },
        liquidity_sequence_by_tf={"15m": {"buy_side_liquidity_taken": False, "sell_side_liquidity_taken": False}},
        watch_state=watch,
        structure_hierarchy={"15m": {"dealing_range": {"range_low": "59000", "range_high": "61000"}}},
    ).to_dict()

    readiness = evaluate_execution_readiness(watch_state=watch, inducement_continuation=assessment).to_dict()

    assert watch["signal_allowed"] is False
    assert watch["active_poi"] is None
    assert watch["final_state"] in {
        "NO_VALID_ACTIVE_POI_IN_CURRENT_1H_RANGE",
        "WATCH_NEW_LOWER_SUPPLY_FORMATION",
    }
    assert assessment["state"] == "POSSIBLE_INDUCEMENT"
    assert readiness["state"] == "INDUCEMENT_RISK_HIGH"
    assert readiness["capital_risk"] == 0
