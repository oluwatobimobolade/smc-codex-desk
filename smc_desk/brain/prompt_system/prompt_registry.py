"""Versioned registry for AI SMC prompt modules."""
from __future__ import annotations

import hashlib
from typing import Any

from smc_desk.brain.prompt_system.annotation_prompt import PROMPT as ANNOTATION_PROMPT
from smc_desk.brain.prompt_system.evidence_guardrail_prompt import PROMPT as EVIDENCE_GUARDRAIL_PROMPT
from smc_desk.brain.prompt_system.json_schema_prompt import PROMPT as JSON_SCHEMA_PROMPT
from smc_desk.brain.prompt_system.master_identity_prompt import PROMPT as MASTER_IDENTITY_PROMPT
from smc_desk.brain.prompt_system.prompt_contract import PromptModule
from smc_desk.brain.prompt_system.reasoning_order_prompt import PROMPT as REASONING_ORDER_PROMPT
from smc_desk.brain.prompt_system.smc_doctrine_prompt import PROMPT as SMC_DOCTRINE_PROMPT
from smc_desk.brain.prompt_system.target_sl_prompt import PROMPT as TARGET_SL_PROMPT
from smc_desk.brain.prompt_system.trade_readiness_prompt import PROMPT as TRADE_READINESS_PROMPT


PROMPT_SYSTEM_NAME = "smc_prompt_operating_system"
PROMPT_SYSTEM_VERSION = "1.0.0"


def load_prompt_modules() -> list[PromptModule]:
    return [
        MASTER_IDENTITY_PROMPT,
        SMC_DOCTRINE_PROMPT,
        REASONING_ORDER_PROMPT,
        EVIDENCE_GUARDRAIL_PROMPT,
        TRADE_READINESS_PROMPT,
        TARGET_SL_PROMPT,
        ANNOTATION_PROMPT,
        JSON_SCHEMA_PROMPT,
    ]


def prompt_system_hash(modules: list[PromptModule] | None = None) -> str:
    modules = modules or load_prompt_modules()
    payload = "\n".join([PROMPT_SYSTEM_NAME, PROMPT_SYSTEM_VERSION, *[module.hash for module in modules]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_prompt_registry_manifest(*, include_text: bool = True) -> dict[str, Any]:
    modules = load_prompt_modules()
    return {
        "schema": "smc_prompt_registry_manifest_v1",
        "name": PROMPT_SYSTEM_NAME,
        "version": PROMPT_SYSTEM_VERSION,
        "hash": prompt_system_hash(modules),
        "module_count": len(modules),
        "modules": [module.to_dict(include_text=include_text) for module in modules],
        "required_output_schema": "ai_smc_trader_decision_v1",
    }
