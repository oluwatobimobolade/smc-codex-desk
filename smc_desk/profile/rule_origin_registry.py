from __future__ import annotations

from typing import Any

RULE_ORIGIN_REGISTRY: dict[str, dict[str, Any]] = {
    "minimum_rr_3": {
        "origin": "user_preference",
        "scope": "trade_plan_validity",
        "not_smc_doctrine": True,
    },
    "fvg_min_width_bps": {
        "origin": "quality_filter",
        "scope": "tradable_fvg_filter",
        "not_smc_doctrine": True,
    },
    "pivot_window_external_5": {
        "origin": "system_approximation",
        "scope": "candidate_detection",
        "not_smc_doctrine": True,
    },
    "sweep_before_reversal": {
        "origin": "smc_doctrine",
        "scope": "high_probability_reversal_model",
        "not_smc_doctrine": False,
    },
}

def get_rule_origin(rule_name: str) -> dict[str, Any] | None:
    return RULE_ORIGIN_REGISTRY.get(rule_name)
