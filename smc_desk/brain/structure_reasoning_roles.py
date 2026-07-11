"""Machine-readable authority contract for AI-centered SMC reasoning."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from smc_desk.data.hashing import file_sha256, object_sha256


DEFAULT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "AI_CENTERED_STRUCTURE_REASONING_V1.yaml"
)
REQUIRED_ROLES = (
    "blind_visual_structure_reader",
    "deterministic_candidate_reconciler",
    "causal_episode_constructor",
    "adversarial_structure_critic",
    "annotation_planner",
    "visual_annotation_critic",
)
ABSOLUTE_PROHIBITIONS = {
    "invent_or_modify_ohlcv",
    "move_candidate_time_or_price_coordinates",
    "use_rows_after_decision_time",
    "bypass_deterministic_validation",
    "promote_trade_or_execution_authority",
    "overwrite_human_adjudicated_gold",
}


def load_structure_reasoning_contract(
    path: str | Path | None = None,
) -> dict[str, Any]:
    contract_path = Path(path) if path is not None else DEFAULT_CONTRACT_PATH
    payload = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("AI structure reasoning contract must be an object.")
    validate_structure_reasoning_contract(payload)
    payload = dict(payload)
    payload["contract_path"] = str(contract_path.resolve())
    payload["contract_file_sha256"] = file_sha256(contract_path)
    payload["contract_semantic_sha256"] = object_sha256(
        {key: value for key, value in payload.items() if not key.startswith("contract_")}
    )
    return payload


def validate_structure_reasoning_contract(payload: dict[str, Any]) -> None:
    if payload.get("contract_id") != "AI_CENTERED_STRUCTURE_REASONING_V1":
        raise ValueError("Unexpected AI structure reasoning contract ID.")
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        raise ValueError("AI structure reasoning contract is missing roles.")
    missing = [role for role in REQUIRED_ROLES if role not in roles]
    if missing:
        raise ValueError(f"AI structure reasoning contract missing roles: {missing}")
    orders = [int(roles[role].get("order", -1)) for role in REQUIRED_ROLES]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        raise ValueError("AI reasoning roles must have a unique causal order.")
    prohibitions = set(payload.get("global_ai_prohibitions", []))
    missing_prohibitions = ABSOLUTE_PROHIBITIONS.difference(prohibitions)
    if missing_prohibitions:
        raise ValueError(
            f"AI reasoning contract omitted hard prohibitions: {sorted(missing_prohibitions)}"
        )
    for critic in ("adversarial_structure_critic", "visual_annotation_critic"):
        if roles[critic].get("promotion_allowed") is not False:
            raise ValueError(f"{critic} must be downgrade-only.")
    execution = payload.get("execution_authority", {})
    if execution.get("signal_allowed") is not False:
        raise ValueError("AI structure research cannot grant signal authority.")
    if execution.get("paper_execution") != "disabled" or execution.get("live_execution") != "disabled":
        raise ValueError("AI structure research must keep execution disabled.")


def build_ai_role_trace(
    *,
    provider: str,
    model: str,
    role_status: str = "NOT_INVOKED_BASELINE",
) -> dict[str, Any]:
    contract = load_structure_reasoning_contract()
    return {
        "schema": "ai_structure_role_trace_v1",
        "contract_id": contract["contract_id"],
        "contract_sha256": contract["contract_file_sha256"],
        "provider": provider,
        "model": model,
        "role_status": role_status,
        "role_order": list(REQUIRED_ROLES),
        "ai_semantic_authority": True,
        "ai_geometry_authority": False,
        "ai_market_truth_authority": False,
        "ai_trade_promotion_authority": False,
        "silent_fallback_allowed": False,
        "bounded_repair_attempts": 0 if role_status == "NOT_INVOKED_BASELINE" else 1,
    }
