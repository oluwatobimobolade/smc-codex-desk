from __future__ import annotations

from smc_desk.colleague.wp0020_gauntlet import _status_from_stage_results


def _base_stages() -> dict:
    return {
        "02_mtf_package": {
            "truth_validation": {"status": "PASS"},
            "derived_htf_consistency": {"status": "aligned"},
            "native_htf_audit": {"status": "not_available"},
            "data_depth": {},
        },
        "04_debug_legacy_annotations": {"status": "PASS"},
        "04a_story_charts": {"status": "PASS"},
        "06_cognitive": {"status": "PASS", "watch_state": {"active_poi": None, "poi_selection": {"status": "SELECTED_ACTIVE_POI"}}},
        "12_research_events": {"status": "PASS"},
        "09_smc_thesis": {"status": "PASS"},
        "08_visual_reconciliation": {"status": "VISUAL_AUDIT_AVAILABLE"},
    }


def test_htf_review_flag_prevents_clean_pass():
    stages = _base_stages()
    stages["02_mtf_package"]["derived_htf_consistency"] = {"status": "review"}

    status, failed_layer = _status_from_stage_results(stages)

    assert status == "PASS_WITH_REVIEW_FLAGS"
    assert failed_layer is None


def test_blank_visual_proof_prevents_clean_pass():
    stages = _base_stages()
    stages["08_visual_reconciliation"] = {"status": "VISUAL_CONTEXT_UNVERIFIED"}

    status, failed_layer = _status_from_stage_results(stages)

    assert status == "PARTIAL_PASS"
    assert failed_layer == "07_tradingview_visual"
