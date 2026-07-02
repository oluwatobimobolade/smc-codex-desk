from __future__ import annotations

from smc_desk.decision.setup_classifier import classify_setup_model, SetupClassification, NO_CLEAR_MODEL


def _cognitive(**kw):
    base = {
        "watch_state": {"direction": "bearish", "active_poi": None},
        "structure_hierarchy": {},
        "liquidity_sequence": {},
        "inducement_continuation": {"state": "EARLY_CONTINUATION_CONFIRMATION"},
    }
    base.update(kw)
    return base


def test_setup_classifier_bearish_breaker_retest():
    result = classify_setup_model(
        cognitive_result=_cognitive(),
        official_bias="bearish",
        active_poi={"kind": "breaker", "timeframe": "1h", "price_relation": "below_poi"},
        liquidity_sequence={},
    )
    assert result.setup_type == "BREAKER_RETEST_SHORT"
    assert result.direction == "bearish"


def test_setup_classifier_no_clear_model():
    result = classify_setup_model(
        cognitive_result=_cognitive(),
        official_bias="neutral",
        active_poi=None,
    )
    assert result.setup_type == NO_CLEAR_MODEL


def test_bearish_breaker_targets_previous_structural_low():
    from smc_desk.decision.liquidity_target_selector import select_liquidity_targets

    hierarchy = {
        "1h": {"external_range_low": "95.0", "protected_low": "96.0"},
        "4h": {"external_range_low": "90.0"},
    }
    result = select_liquidity_targets(
        setup_model={"direction": "bearish", "setup_type": "BREAKER_RETEST_SHORT", "setup_timeframe": "1h"},
        structure_hierarchy=hierarchy,
        active_poi={"timeframe": "1h", "direction": "bearish"},
        current_price="100.0",
        invalidation={"price": "101.0"},
    )
    assert result["status"] == "PASS"
    assert len(result["targets"]) > 0
    assert float(result["targets"][0]["price"]) < 100.0


def test_bullish_breaker_targets_previous_structural_high():
    from smc_desk.decision.liquidity_target_selector import select_liquidity_targets

    hierarchy = {
        "1h": {"external_range_high": "110.0", "protected_high": "108.0"},
        "4h": {"external_range_high": "115.0"},
    }
    result = select_liquidity_targets(
        setup_model={"direction": "bullish", "setup_type": "BREAKER_RETEST_LONG", "setup_timeframe": "1h"},
        structure_hierarchy=hierarchy,
        active_poi={"timeframe": "1h", "direction": "bullish"},
        current_price="100.0",
        invalidation={"price": "98.0"},
    )
    assert result["status"] == "PASS"
    assert len(result["targets"]) > 0
    assert float(result["targets"][0]["price"]) > 100.0


def test_target_selected_from_active_setup_liquidity():
    from smc_desk.decision.liquidity_target_selector import select_liquidity_targets

    hierarchy = {"1h": {"external_range_low": "95.0"}}
    result = select_liquidity_targets(
        setup_model={"direction": "bearish", "setup_timeframe": "1h"},
        structure_hierarchy=hierarchy,
        active_poi={"timeframe": "1h", "direction": "bearish"},
        current_price="100.0",
        invalidation={"price": "101.0"},
        entry_timeframe="15m",
    )
    assert result["target_selection"] == "setup_dependent_liquidity"
    assert result["entry_timeframe_is_not_target_authority"] is True


def test_target_conflicts_with_model_rejected():
    from smc_desk.decision.liquidity_target_selector import select_liquidity_targets, REJECTED_TARGET_CONFLICTS_WITH_MODEL

    hierarchy = {"1h": {"external_range_low": "102.0"}}
    result = select_liquidity_targets(
        setup_model={"direction": "bearish", "setup_timeframe": "1h"},
        structure_hierarchy=hierarchy,
        active_poi={"timeframe": "1h", "direction": "bearish"},
        current_price="100.0",
        invalidation={"price": "101.0"},
    )
    assert result["status"] == REJECTED_TARGET_CONFLICTS_WITH_MODEL
