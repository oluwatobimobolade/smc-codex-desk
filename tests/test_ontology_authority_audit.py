from __future__ import annotations

from tools.audit_ontology_authority import audit_authority_split


def test_ontology_authority_audit_marks_split_ready_but_runtime_pending() -> None:
    report = audit_authority_split()

    assert report["status"] == "runtime_config_migrated_to_split_contracts"
    assert "risk_reward_floor" in report["monolith"]["mixed_authority_terms"]
    assert report["detector_split"]["mixed_authority_terms"] == []
    assert report["detector_split"]["clean_for_detector_authority"] is True
    assert "risk_reward_floor" in report["strategy_split"]["strategy_terms_present"]
    assert report["runtime_config"]["migrated_to_split_contracts"] is True
    assert report["promotion_status"] == "blocked_until_live_shadow_and_adjudicated_validation"
    assert report["market_edge_claimed"] is False
