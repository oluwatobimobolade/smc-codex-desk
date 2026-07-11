"""Separate, hashable prompts for each AI structure-lab role."""
from __future__ import annotations

import json
from typing import Any

from smc_desk.brain.structure_lab.schemas import ROLE_SCHEMAS
from smc_desk.brain.structure_reasoning_roles import load_structure_reasoning_contract
from smc_desk.data.hashing import object_sha256, sha256_text


ROLE_INSTRUCTIONS = {
    "blind_visual_structure_reader": "Read only clean chart evidence. Describe visible candidates and uncertainty. You have no detector labels and must not call a trade.",
    "deterministic_candidate_reconciler": "Map visual observations to certified evidence IDs. Reject unsupported candidates. Never move a time or price coordinate.",
    "causal_episode_constructor": "Build the parent/child structure story from reconciled evidence. Separate external continuation, internal pullback, transition, range, and uncertainty. Preserve alternatives.",
    "adversarial_structure_critic": "Try to falsify the causal episode against formal-graph invariants and evidence. You may pass, request revision, or downgrade. You may never promote.",
    "annotation_planner": "Choose the few semantic objects a professional SMC trader should see. Select evidence IDs only; the deterministic resolver owns geometry. No trade box.",
    "visual_annotation_critic": "Audit the rendered/declared annotation for clutter, locality, readability, and graph agreement. You may request cleanup or downgrade, never promote.",
}


def build_role_prompt(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    if role not in ROLE_SCHEMAS:
        raise ValueError(f"Unknown structure-lab role: {role}")
    contract = load_structure_reasoning_contract()
    schema = ROLE_SCHEMAS[role].model_json_schema()
    prompt = "\n\n".join(
        [
            "You are one governed role inside an AI-first SMC structure laboratory.",
            f"ROLE: {role}",
            ROLE_INSTRUCTIONS[role],
            "GLOBAL PROHIBITIONS:\n- " + "\n- ".join(contract["global_ai_prohibitions"]),
            "Return one strict JSON object matching this schema:\n" + json.dumps(schema, sort_keys=True),
            "ROLE INPUT:\n" + json.dumps(payload, sort_keys=True, default=str),
        ]
    )
    return {
        "schema": "structure_role_prompt_v1",
        "role": role,
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "input_sha256": object_sha256(payload),
        "output_schema_sha256": object_sha256(schema),
        "contract_sha256": contract["contract_file_sha256"],
    }
