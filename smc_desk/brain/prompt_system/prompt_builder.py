"""Layered prompt builder for the AI SMC trader brain."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from smc_desk.brain.prompt_system.prompt_registry import build_prompt_registry_manifest


SCHEMA_FIELDS = [
    "official_state",
    "setup_grade",
    "direction",
    "setup_model",
    "bias_summary",
    "active_range",
    "liquidity_story",
    "displacement_assessment",
    "active_poi",
    "entry_plan",
    "stop_loss_plan",
    "target_plan",
    "rr_status",
    "invalidation",
    "annotation_plan",
    "self_review",
    "final_thesis",
]


def build_layered_ai_smc_prompt(evidence_pack: Mapping[str, Any]) -> str:
    from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER

    prompt_system = build_prompt_registry_manifest(include_text=True)
    prompt = {
        "role": "AI SMC trader brain",
        "prompt_system": prompt_system,
        "non_negotiables": [
            "Detector outputs are candidates, not truth.",
            "No 1m official entry.",
            "No live execution, no paper execution, no account risk, no leverage.",
            "Watch charts must not include entry, SL, TP, RR, or trade box.",
            "Do not use OHLCV summary highs/lows or whole-dataset extremes as the active dealing range.",
            "Use evidence_pack.active_range_authority.selected_range for active_range; if it is unresolved or visibly wrong, return REVIEW_REQUIRED.",
            "Every official annotation must be checked against the selected active range and active POI before output.",
            "TRADE_PLAN_READY requires validated entry, structural invalidation, model-completion liquidity target, and RR >= 3.",
            "TRADE_PLAN_READY requires clean/strong displacement, structure_broken=true, and displacement evidence_object_ids.",
            "If final_thesis says watch, wait, no trade, or refuses a trade plan, official_state must not be TRADE_PLAN_READY.",
            "Prefer REVIEW_REQUIRED, WATCH_ONLY, MISSED_TRADE_NO_CHASE, or VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY over weak trade plans.",
        ],
        "mandatory_self_review": [
            "First pass: map HTF bias, active range, liquidity, sweep/displacement, POI, entry readiness.",
            "Second pass: challenge the first pass. Ask whether the active range is too broad, summary-sourced, stale, or outside protected structure.",
            "Annotation pass: remove any label, level, entry, SL, or TP not supported by selected evidence.",
            "Refusal pass: if the setup needs invented levels, broad OHLCV ranges, or missing POI evidence, output REVIEW_REQUIRED or WATCH_ONLY.",
            "Populate self_review with the pass/fail result and corrections made.",
        ],
        "required_reasoning_order": REASONING_ORDER,
        "required_json_schema": {
            "schema": "ai_smc_trader_decision_v1",
            "fields": SCHEMA_FIELDS,
            "annotation_plan_must_include_reasoning_order": True,
            "strict_json_only": True,
        },
        "official_state_options": [
            "THESIS_ONLY",
            "WATCH_ONLY",
            "WAIT_FOR_POI",
            "WAIT_FOR_RETRACE_TO_SUPPLY",
            "WAIT_FOR_RETRACE_TO_DEMAND",
            "POI_TOUCHED_AWAIT_CONFIRMATION",
            "TRADE_PLAN_READY",
            "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY",
            "MISSED_TRADE_NO_CHASE",
            "INDUCEMENT_RISK",
            "INVALIDATED_REMAP",
            "MOVE_STARTED_NOT_CHASEABLE",
            "NO_TRADE",
            "REVIEW_REQUIRED",
        ],
        "evidence_pack": evidence_pack,
    }
    return json.dumps(prompt, indent=2, sort_keys=True, default=str)
