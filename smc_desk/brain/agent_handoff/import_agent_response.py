"""Import and validate an external AI agent's response.

The external AI agent writes its response to a response directory:

  response_dir/
    official_decision_candidate.json  — the AISMCDecision JSON
    agent_reasoning_summary.md          — short markdown reasoning
    annotation_plan.json                — chart labels and levels
    requested_more_context.json         — optional, if agent needs more data

The import function:
  1. Validates the response schema
  2. Extracts the decision JSON
  3. Records the agent identity, packet hash, and response hash
  4. Returns a validated decision ready for the orchestrator
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_desk.brain.ai_smc_trader_brain import parse_ai_smc_decision


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def validate_response_structure(response_dir: Path) -> list[str]:
    """Check that the response directory has the required files and structure.

    Returns a list of error messages. Empty list means valid.
    """
    errors: list[str] = []
    response_dir = Path(response_dir)
    if not response_dir.exists():
        errors.append(f"Response directory does not exist: {response_dir}")
        return errors

    required = ["official_decision_candidate.json", "agent_reasoning_summary.md"]
    for filename in required:
        if not (response_dir / filename).exists():
            errors.append(f"Missing required response file: {filename}")

    decision_path = response_dir / "official_decision_candidate.json"
    if decision_path.exists():
        try:
            payload = json.loads(decision_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in official_decision_candidate.json: {exc}")
            return errors

        if not isinstance(payload, Mapping):
            errors.append("official_decision_candidate.json must be a JSON object")
            return errors

        schema = payload.get("schema")
        if schema not in ("ai_smc_trader_decision_v1", "ai_smc_agent_response_v1"):
            errors.append(
                f"Expected schema 'ai_smc_trader_decision_v1' or 'ai_smc_agent_response_v1', got {schema!r}"
            )
    return errors


def import_agent_response(
    response_dir: Path,
    *,
    expected_packet_hash: str | None = None,
) -> dict[str, Any]:
    """Import and validate an external AI agent's response.

    Returns a dict with:
      - decision: parsed AISMCDecision
      - decision_payload: raw dict
      - agent_identity: from the response
      - audit: agent identity, packet hash, response hash, timestamps
      - requested_more_context: list of context requests
    """
    response_dir = Path(response_dir)
    errors = validate_response_structure(response_dir)
    if errors:
        raise ValueError(f"Invalid agent response: {'; '.join(errors)}")

    decision_payload = json.loads((response_dir / "official_decision_candidate.json").read_text(encoding="utf-8"))

    if isinstance(decision_payload, Mapping) and "decision" in decision_payload and isinstance(decision_payload["decision"], Mapping):
        response_metadata = {k: decision_payload[k] for k in decision_payload if k != "decision"}
        decision_payload = decision_payload["decision"]
    else:
        response_metadata = {
            k: decision_payload.pop(k) for k in list(decision_payload.keys())
            if k in ("agent_identity", "packet_hash", "semantic_anchors", "agent_reasoning_notes", "requested_more_context")
        }

    decision = parse_ai_smc_decision(decision_payload)

    reasoning = ""
    reasoning_path = response_dir / "agent_reasoning_summary.md"
    if reasoning_path.exists():
        reasoning = reasoning_path.read_text(encoding="utf-8")

    annotation_plan = None
    annotation_path = response_dir / "annotation_plan.json"
    if annotation_path.exists():
        try:
            annotation_plan = json.loads(annotation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            annotation_plan = None

    requested_more_context: list[Any] = []
    rmc_path = response_dir / "requested_more_context.json"
    if rmc_path.exists():
        try:
            rmc_payload = json.loads(rmc_path.read_text(encoding="utf-8"))
            if isinstance(rmc_payload, list):
                requested_more_context = rmc_payload
        except json.JSONDecodeError:
            pass

    response_hash = _hash_json(decision_payload)
    decision_payload_hash = _hash_file(response_dir / "official_decision_candidate.json")
    response_packet_hash = response_metadata.get("packet_hash") or response_metadata.get("agent_identity", {}).get("packet_hash", "")
    packet_hash_match = (expected_packet_hash is None) or (
        response_packet_hash == expected_packet_hash
    )

    audit = {
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "response_dir": str(response_dir),
        "packet_hash_expected": expected_packet_hash,
        "packet_hash_from_response": response_packet_hash,
        "packet_hash_match": packet_hash_match,
        "decision_payload_hash": decision_payload_hash,
        "response_hash": response_hash,
        "agent_identity": response_metadata.get("agent_identity", {}),
        "semantic_anchors": response_metadata.get("semantic_anchors", {}),
        "agent_reasoning_length": len(reasoning),
        "has_annotation_plan": annotation_plan is not None,
        "requested_more_context_count": len(requested_more_context),
    }

    return {
        "decision": decision,
        "decision_payload": decision_payload,
        "agent_identity": response_metadata.get("agent_identity", {}),
        "semantic_anchors": response_metadata.get("semantic_anchors", {}),
        "agent_reasoning": reasoning,
        "annotation_plan": annotation_plan,
        "requested_more_context": requested_more_context,
        "audit": audit,
    }
