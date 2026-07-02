from __future__ import annotations

from smc_desk.decision.execution_readiness import evaluate_execution_readiness
from smc_desk.decision.inducement_continuation_classifier import classify_inducement_continuation


def test_early_bearish_confirmation_requires_ltf_supply_retrace_before_readiness():
    assessment = classify_inducement_continuation(
        perception_by_tf={
            "15m": {
                "last_price": "60120",
                "structure_breaks": [
                    {"object_id": "mss_down", "direction": "bearish", "confirmed_at": "2026-06-27T20:30:00Z"}
                ],
                "order_blocks": [
                    {
                        "object_id": "new_15m_supply",
                        "direction": "bearish",
                        "price_low": "60250",
                        "price_high": "60500",
                        "mitigation_status": "fresh",
                        "terminal_reason": "none",
                    }
                ],
                "fvgs": [],
            }
        },
        liquidity_sequence_by_tf={
            "15m": {"buy_side_liquidity_taken": True, "sell_side_liquidity_taken": False}
        },
        watch_state={"direction": "bearish", "active_poi": None},
        structure_hierarchy={"15m": {"dealing_range": {"range_low": "59000", "range_high": "61000"}}},
    ).to_dict()

    readiness = evaluate_execution_readiness(
        watch_state={"final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION", "active_poi": None},
        inducement_continuation=assessment,
    ).to_dict()

    assert assessment["state"] == "EARLY_CONTINUATION_CONFIRMATION"
    assert readiness["state"] == "WAIT_FOR_RETRACE_TO_LTF_SUPPLY"
    assert readiness["signal_allowed"] is False
    assert any("retest/rejection" in reason for reason in readiness["reasons"])
