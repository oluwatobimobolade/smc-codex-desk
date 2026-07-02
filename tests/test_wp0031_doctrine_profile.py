from __future__ import annotations

from smc_desk.profile.smc_intraday_profile import SMC_INTRADAY_PROFILE, assert_intraday_profile_contract


def test_intraday_profile_no_risk_authority():
    assert SMC_INTRADAY_PROFILE["risk_authority"] == "user_only"
    assert SMC_INTRADAY_PROFILE["position_sizing"] == "disabled"
    assert SMC_INTRADAY_PROFILE["leverage_decision"] == "disabled"
    assert SMC_INTRADAY_PROFILE["account_risk_decision"] == "disabled"
    assert SMC_INTRADAY_PROFILE["liquidation_risk_decision"] == "disabled"
    assert SMC_INTRADAY_PROFILE["partial_close_rules"] == "disabled"
    assert SMC_INTRADAY_PROFILE["breakeven_rules"] == "disabled"
    assert SMC_INTRADAY_PROFILE["trailing_rules"] == "disabled"


def test_minimum_rr_fixed_at_three():
    assert float(SMC_INTRADAY_PROFILE["minimum_rr"]) == 3.0
    assert_intraday_profile_contract()


def test_15m_entry_does_not_force_15m_target():
    from smc_desk.decision.liquidity_target_selector import select_liquidity_targets

    hierarchy = {
        "1h": {"external_range_low": "95.0", "protected_low": "96.0", "dealing_range": {"range_low": "97.0"}},
        "4h": {"external_range_low": "90.0", "protected_low": "92.0"},
    }
    result = select_liquidity_targets(
        setup_model={"direction": "bearish", "setup_timeframe": "1h"},
        structure_hierarchy=hierarchy,
        active_poi={"timeframe": "1h", "direction": "bearish"},
        current_price="100.0",
        invalidation={"price": "101.0"},
        entry_timeframe="15m",
    )
    assert result["entry_timeframe"] == "15m"
    assert result["entry_timeframe_is_not_target_authority"] is True
    for target in result["targets"]:
        assert target["timeframe"] != "15m" or target["source"] != "15m_only"
        assert float(target["price"]) < 100.0


def test_5m_refinement_optional_only():
    from smc_desk.decision.entry_style_selector import select_entry_style, FIVE_MINUTE_REFINEMENT_ALLOWED, CONSERVATIVE_CONFIRMATION_REQUIRED

    result = select_entry_style(
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
        requested_timeframe="5m",
        needs_refinement=True,
    )
    assert result["entry_timeframe"] == "15m"
    assert result["state"] == FIVE_MINUTE_REFINEMENT_ALLOWED
    assert result["refinement_timeframe"] == "5m"

    result2 = select_entry_style(
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
        requested_timeframe="5m",
        needs_refinement=False,
    )
    assert result2["state"] == CONSERVATIVE_CONFIRMATION_REQUIRED


def test_1m_entry_forbidden():
    from smc_desk.decision.entry_style_selector import select_entry_style, REJECTED_1M_ENTRY_FORBIDDEN

    result = select_entry_style(active_poi={}, requested_timeframe="1m")
    assert result["state"] == REJECTED_1M_ENTRY_FORBIDDEN
    assert result["entry_timeframe"] == "15m"
