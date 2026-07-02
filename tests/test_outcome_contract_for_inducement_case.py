from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from smc_desk.colleague.wp0020_gauntlet import write_research_event_package


def test_outcome_contract_records_inducement_and_continuation_conditions(tmp_path):
    manifest = write_research_event_package(
        output_dir=tmp_path,
        symbol="BTCUSDT",
        decision_available_at=pd.Timestamp(datetime(2026, 6, 27, 21, 0, tzinfo=timezone.utc)),
        cognitive_result={
            "watch_state": {
                "final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
                "direction": "bearish",
                "signal_allowed": False,
                "active_poi": None,
            },
            "inducement_continuation": {
                "state": "EARLY_CONTINUATION_CONFIRMATION",
                "direction": "bearish",
                "continuation_confirmed_if": [
                    "price retests 60250-60500 supply",
                    "price rejects from that supply",
                    "price breaks the next sell-side liquidity after rejection",
                ],
                "inducement_confirmed_if": [
                    "price reclaims above 60250-60500 supply",
                    "price holds above the reclaimed supply",
                    "price expands back toward buy-side liquidity",
                ],
                "do_not_chase_reason": "Shift exists, but continuation needs a retest/rejection instead of a chase entry.",
            },
            "execution_readiness": {"state": "WAIT_FOR_RETRACE_TO_LTF_SUPPLY", "confidence": 0.62},
            "refusal": {"final_action": "NO_SIGNAL", "blocking_codes": ["observe_only"]},
            "final_action": "NO_SIGNAL",
            "perception_by_tf": {},
            "poi_lifecycle": {},
            "liquidity_sequence": {},
        },
    )

    contract_path = tmp_path / "pending_outcome_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    scenario = contract["tracked_scenarios"][0]

    assert manifest["outcome_contract_status"] == "pending_observation"
    assert contract["capital_risk"] == 0
    assert scenario["execution_readiness"] == "WAIT_FOR_RETRACE_TO_LTF_SUPPLY"
    assert scenario["inducement_continuation"] == "EARLY_CONTINUATION_CONFIRMATION"
    assert scenario["continuation_confirmed_if"]
    assert scenario["inducement_confirmed_if"]
    assert "retest/rejection" in scenario["do_not_chase_reason"]
