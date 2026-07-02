from __future__ import annotations

from smc_desk.decision.execution_readiness import evaluate_execution_readiness
from smc_desk.decision.inducement_continuation_classifier import classify_inducement_continuation


def test_sol_topside_raid_then_extended_bearish_drop_is_not_chaseable():
    assessment = classify_inducement_continuation(
        perception_by_tf={
            "15m": {
                "last_price": "70.25",
                "structure_breaks": [
                    {"object_id": "sol_mss_down", "direction": "bearish", "confirmed_at": "2026-06-27T20:15:00Z"}
                ],
                "order_blocks": [
                    {
                        "object_id": "sol_new_supply",
                        "direction": "bearish",
                        "price_low": "71.30",
                        "price_high": "71.80",
                        "mitigation_status": "fresh",
                        "terminal_reason": "none",
                    }
                ],
                "fvgs": [],
            }
        },
        liquidity_sequence_by_tf={
            "15m": {
                "buy_side_liquidity_taken": True,
                "sell_side_liquidity_taken": False,
                "last_liquidity_event": "buy_side_sweep",
            }
        },
        watch_state={"direction": "bearish", "active_poi": None},
        structure_hierarchy={"15m": {"dealing_range": {"range_low": "70.00", "range_high": "73.00"}}},
    ).to_dict()

    readiness = evaluate_execution_readiness(
        watch_state={"final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION", "active_poi": None},
        inducement_continuation=assessment,
    ).to_dict()

    assert assessment["state"] == "MOVE_STARTED_NOT_CHASEABLE"
    assert assessment["do_not_chase_reason"]
    assert "71.30-71.80" in " ".join(assessment["continuation_confirmed_if"])
    assert readiness["state"] == "MOVE_STARTED_NOT_CHASEABLE"
    assert readiness["live_execution"] == "disabled"
