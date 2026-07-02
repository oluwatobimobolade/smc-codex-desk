from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from smc_desk.colleague.wp0020_gauntlet import write_research_event_package


def test_research_events_are_split_into_noise_and_decision_tiers(tmp_path):
    manifest = write_research_event_package(
        output_dir=tmp_path,
        symbol="BTCUSDT",
        cognitive_result={
            "perception_by_tf": {
                "15m": {
                    "structure_breaks": [{"object_id": "raw_break", "direction": "bearish"}],
                    "sweeps": [],
                    "order_blocks": [],
                    "fvgs": [],
                    "inducements": [],
                }
            },
            "poi_lifecycle": {
                "15m": [
                    {
                        "poi_id": "candidate_supply",
                        "direction": "bearish",
                        "validity_status": "VALID_ACTIVE_SETUP_POI",
                        "scope": "active_setup",
                    }
                ]
            },
            "liquidity_sequence": {"15m": {"buy_side_liquidity_taken": True, "sell_side_liquidity_taken": False}},
            "watch_state": {
                "final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
                "direction": "bearish",
                "signal_allowed": False,
            },
            "inducement_continuation": {"state": "EARLY_CONTINUATION_CONFIRMATION", "direction": "bearish"},
            "execution_readiness": {"state": "WAIT_FOR_RETRACE_TO_LTF_SUPPLY", "confidence": 0.62},
            "refusal": {"final_action": "NO_SIGNAL", "blocking_codes": ["observe_only"]},
            "final_action": "NO_SIGNAL",
        },
        decision_available_at=pd.Timestamp(datetime(2026, 6, 27, 21, 0, tzinfo=timezone.utc)),
    )

    assert manifest["event_hierarchy"]["raw_detector_events"] == 1
    assert manifest["event_hierarchy"]["candidate_research_events"] == 1
    assert manifest["event_hierarchy"]["decision_grade_events"] >= 4
    assert manifest["event_hierarchy"]["outcome_contract_events"] == 1
    assert manifest["wisdom_layer_priority"] == ["decision_grade_events", "outcome_contract_events"]
    for name in ("raw_detector_events", "candidate_research_events", "decision_grade_events", "outcome_contract_events"):
        assert (tmp_path / f"{name}.jsonl").exists()
