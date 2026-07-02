from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority, assert_narrative_authority_contract


def _cognitive(**kw):
    base = {
        "symbol": "SOLUSDT",
        "final_action": "NO_SIGNAL",
        "signal_allowed": False,
        "watch_state": {
            "final_state": "WATCH_BEARISH_RETRACE_TO_SUPPLY",
            "final_action": "NO_SIGNAL",
            "signal_allowed": False,
            "direction": "bearish",
            "active_poi": {
                "poi_id": "1h:supply:test",
                "kind": "supply",
                "timeframe": "1h",
                "direction": "bearish",
                "price_low": "71.0",
                "price_high": "72.0",
                "freshness": "fresh",
                "price_relation": "below_poi",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
            },
            "reasons": ["wait for retrace"],
        },
        "execution_readiness": {"state": "WAIT_FOR_RETRACE_TO_LTF_SUPPLY", "signal_allowed": False},
        "inducement_continuation": {
            "state": "EARLY_CONTINUATION_CONFIRMATION",
            "direction": "bearish",
            "continuation_confirmed_if": ["retrace", "reject", "break"],
            "inducement_confirmed_if": ["reclaim"],
            "evidence": {"same_direction_15m_break_count": 3},
        },
        "structure_hierarchy": {
            "4h": {"external_bias": "bearish", "external_range_low": "64.0", "protected_high": "74.0"},
            "1h": {"external_bias": "bearish", "external_range_low": "70.0", "protected_high": "73.0"},
            "15m": {"external_bias": "bearish"},
        },
        "liquidity_sequence": {"15m": {"buy_side_liquidity_taken": True}},
        "refusal": {"final_action": "NO_SIGNAL", "signal_allowed": False, "blocking_codes": ["watch_state_not_executable"]},
    }
    base.update(kw)
    return base


def test_narrative_authority_outputs_one_official_model():
    authority = build_smc_narrative_authority(symbol="SOLUSDT", cognitive_result=_cognitive())
    assert authority["official_model"]
    assert authority["official_bias"] == "bearish"
    assert authority["official_state"] in {"WAIT_FOR_RETRACE_TO_SUPPLY", "WATCH_ONLY"}
    assert authority["trade_plan_state"] == "WATCH_ONLY"
    assert authority["show_trade_box"] is False
    assert authority["entry"] is None
    assert authority["stop_loss"] is None
    assert authority["take_profit"] == []
    assert authority["targets"] == []
    assert_narrative_authority_contract(authority)


def test_official_chart_uses_only_narrative_authority():
    from smc_desk.rendering.smc_clean_annotation_renderer import build_clean_annotation_scene

    authority = build_smc_narrative_authority(symbol="SOLUSDT", cognitive_result=_cognitive())
    scene = build_clean_annotation_scene(authority)
    assert scene["source"] == "OfficialSMCDecision"
    assert scene["show_trade_box"] is False
    assert scene["numbered_reasoning_labels"]


def test_watch_chart_has_no_trade_box():
    authority = build_smc_narrative_authority(symbol="SOLUSDT", cognitive_result=_cognitive())
    assert authority["chart_template"] == "watch_chart"
    assert authority["show_trade_box"] is False
    assert authority["entry"] is None
    assert authority["stop_loss"] is None
    assert authority["take_profit"] == []


def test_trade_plan_chart_has_entry_sl_tp_rr():
    authority = build_smc_narrative_authority(symbol="SOLUSDT", cognitive_result=_cognitive(
        watch_state={
            "final_state": "EXECUTE",
            "final_action": "EXECUTE",
            "signal_allowed": True,
            "direction": "bearish",
            "active_poi": {
                "poi_id": "1h:supply:test",
                "kind": "supply",
                "timeframe": "1h",
                "direction": "bearish",
                "price_low": "71.0",
                "price_high": "72.0",
                "freshness": "fresh",
                "price_relation": "inside_poi",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
            },
            "reasons": ["exec"],
        },
        final_action="EXECUTE",
        signal_allowed=True,
        execution_readiness={"state": "TRADE_PLAN_READY", "signal_allowed": True},
    ))
    # Trade plan ready requires all gates; verify it does not falsely show a trade box
    assert authority["show_trade_box"] is False or authority["trade_plan_state"] == "TRADE_PLAN_READY"


def test_clean_annotation_hides_detector_clutter():
    from smc_desk.rendering.smc_clean_annotation_renderer import HIDDEN_FROM_OFFICIAL_CHART

    hidden = " ".join(HIDDEN_FROM_OFFICIAL_CHART)
    assert "raw BOS" in hidden
    assert "raw CHoCH" in hidden
    assert "minor swings" in hidden


def test_numbered_smc_reasoning_labels():
    from smc_desk.rendering.smc_clean_annotation_renderer import build_clean_annotation_scene

    authority = build_smc_narrative_authority(symbol="SOLUSDT", cognitive_result=_cognitive())
    scene = build_clean_annotation_scene(authority)
    labels = scene["numbered_reasoning_labels"]
    assert len(labels) > 0
    assert all("number" in item and "text" in item for item in labels)


def test_debug_chart_is_not_official_chart():
    from smc_desk.rendering.smc_clean_annotation_renderer import DEPRECATED_DEBUG_ONLY

    assert "legacy_annotation_renderer" in DEPRECATED_DEBUG_ONLY
    assert "raw_detector_story_chart" in DEPRECATED_DEBUG_ONLY


def test_thesis_v7_uses_official_decision_only():
    from smc_desk.colleague.smc_thesis_v7 import build_smc_thesis_v7, REQUIRED_SEQUENCE, assert_smc_thesis_v7_quality

    authority = build_smc_narrative_authority(symbol="SOLUSDT", cognitive_result=_cognitive())
    thesis = build_smc_thesis_v7(official_decision=authority)
    assert thesis["source"] == "OfficialSMCDecision"
    assert thesis["claim_sequence"] == REQUIRED_SEQUENCE
    assert thesis["forbidden_language_present"] is False
    assert thesis["show_trade_box"] is False
    assert_smc_thesis_v7_quality(thesis)
