"""Locked intraday SMC doctrine profile.

The profile is intentionally conservative. It defines what the system is not
allowed to decide, as much as what it is allowed to reason about.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


SMC_INTRADAY_PROFILE: Mapping[str, Any] = MappingProxyType({
    "trader_type": "intraday",
    "risk_authority": "user_only",
    "position_sizing": "disabled",
    "leverage_decision": "disabled",
    "account_risk_decision": "disabled",
    "liquidation_risk_decision": "disabled",
    "minimum_rr": 3.0,
    "default_entry_timeframe": "15m",
    "optional_refinement_timeframe": "5m",
    "forbidden_entry_timeframes": ("1m",),
    "partial_close_rules": "disabled",
    "breakeven_rules": "disabled",
    "trailing_rules": "disabled",
    "stop_loss_style": "hybrid_structural",
    "volatility_buffer_model": "disabled_for_now",
    "target_selection": "setup_dependent_liquidity",
    "annotation_style": "clean_smc_tradingview",
    "official_chart_source": "narrative_authority_only",
    "debug_chart_source": "detectors_allowed",
    "paper_execution": "disabled",
    "live_execution": "disabled",
    "capital_risk": 0,
})


def get_intraday_profile() -> Mapping[str, Any]:
    """Return the immutable intraday SMC doctrine profile."""
    return SMC_INTRADAY_PROFILE


def assert_intraday_profile_contract(profile: Mapping[str, Any] = SMC_INTRADAY_PROFILE) -> None:
    if profile.get("risk_authority") != "user_only":
        raise AssertionError("Risk authority must remain user_only.")
    for field in (
        "position_sizing",
        "leverage_decision",
        "account_risk_decision",
        "liquidation_risk_decision",
        "partial_close_rules",
        "breakeven_rules",
        "trailing_rules",
        "paper_execution",
        "live_execution",
    ):
        if profile.get(field) != "disabled":
            raise AssertionError(f"{field} must remain disabled.")
    if float(profile.get("minimum_rr", 0.0)) != 3.0:
        raise AssertionError("Minimum RR must be fixed at 3.0.")
    if profile.get("default_entry_timeframe") != "15m":
        raise AssertionError("Default entry timeframe must be 15m.")
    if profile.get("optional_refinement_timeframe") != "5m":
        raise AssertionError("Optional refinement timeframe must be 5m.")
    if "1m" not in set(profile.get("forbidden_entry_timeframes", ())):
        raise AssertionError("1m must remain forbidden for official entries.")

