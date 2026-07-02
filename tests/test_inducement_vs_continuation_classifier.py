from __future__ import annotations

from smc_desk.decision.inducement_continuation_classifier import classify_inducement_continuation
from smc_desk.decision.execution_readiness import evaluate_execution_readiness


def _bearish_execution_snapshot(last_price: str = "59900") -> dict:
    return {
        "last_price": last_price,
        "structure_breaks": [
            {"object_id": "mss_down", "direction": "bearish", "confirmed_at": "2026-06-27T20:30:00+00:00"}
        ],
        "order_blocks": [
            {
                "object_id": "new_supply",
                "direction": "bearish",
                "price_low": "60250",
                "price_high": "60500",
                "mitigation_status": "fresh",
                "terminal_reason": "none",
            }
        ],
        "fvgs": [],
    }


def test_buy_side_raid_bearish_displacement_is_early_continuation_until_retest():
    assessment = classify_inducement_continuation(
        perception_by_tf={"15m": _bearish_execution_snapshot(last_price="60120")},
        liquidity_sequence_by_tf={
            "15m": {
                "buy_side_liquidity_taken": True,
                "sell_side_liquidity_taken": False,
            }
        },
        watch_state={"direction": "bearish", "active_poi": None},
        structure_hierarchy={
            "15m": {
                "dealing_range": {"range_low": "59000", "range_high": "61000"},
            }
        },
    ).to_dict()

    assert assessment["state"] == "EARLY_CONTINUATION_CONFIRMATION"
    assert assessment["do_not_chase_reason"]
    assert assessment["continuation_confirmed_if"]
    assert assessment["inducement_confirmed_if"]


def test_move_started_near_target_liquidity_is_not_chaseable():
    assessment = classify_inducement_continuation(
        perception_by_tf={"15m": _bearish_execution_snapshot(last_price="59200")},
        liquidity_sequence_by_tf={
            "15m": {
                "buy_side_liquidity_taken": True,
                "sell_side_liquidity_taken": False,
            }
        },
        watch_state={"direction": "bearish", "active_poi": None},
        structure_hierarchy={
            "15m": {
                "dealing_range": {"range_low": "59000", "range_high": "61000"},
            }
        },
    ).to_dict()

    readiness = evaluate_execution_readiness(
        watch_state={"final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION", "active_poi": None},
        inducement_continuation=assessment,
    ).to_dict()

    assert assessment["state"] == "MOVE_STARTED_NOT_CHASEABLE"
    assert readiness["state"] == "MOVE_STARTED_NOT_CHASEABLE"
    assert readiness["signal_allowed"] is False


def test_continuation_conditions_prefer_selected_active_poi_over_latest_ltf_zone():
    assessment = classify_inducement_continuation(
        perception_by_tf={"15m": _bearish_execution_snapshot(last_price="60085")},
        liquidity_sequence_by_tf={
            "15m": {
                "buy_side_liquidity_taken": True,
                "sell_side_liquidity_taken": False,
            }
        },
        watch_state={
            "direction": "bearish",
            "active_poi": {
                "poi_id": "15m:order_block:selected_active_supply",
                "timeframe": "15m",
                "kind": "supply",
                "direction": "bearish",
                "price_low": "60167.1",
                "price_high": "60286.0",
                "price_relation": "below_poi",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
            },
        },
        structure_hierarchy={
            "15m": {
                "dealing_range": {"range_low": "59000", "range_high": "61000"},
            }
        },
    ).to_dict()

    assert assessment["state"] == "EARLY_CONTINUATION_CONFIRMATION"
    assert assessment["continuation_confirmed_if"][0] == "price retests active 15m supply 60167.1-60286.0"
    assert assessment["inducement_confirmed_if"][0] == "price reclaims above active 15m supply 60167.1-60286.0"
    assert "60250-60500" not in " ".join(assessment["continuation_confirmed_if"])

    readiness = evaluate_execution_readiness(
        watch_state={
            "final_state": "WATCH_BEARISH_RETRACE_TO_SUPPLY",
            "active_poi": {
                "timeframe": "15m",
                "kind": "supply",
                "price_low": "60167.1",
                "price_high": "60286.0",
            },
        },
        inducement_continuation=assessment,
    ).to_dict()

    assert readiness["state"] == "WAIT_FOR_RETRACE_TO_LTF_SUPPLY"
    assert readiness["reasons"][-1] == (
        "Continuation shift exists; wait for retest/rejection from active 15m supply 60167.1-60286.0."
    )
