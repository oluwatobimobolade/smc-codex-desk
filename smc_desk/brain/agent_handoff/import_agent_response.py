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

from smc_desk.brain.agent_handoff.ai_seat_contract import verify_bundled_authority
from smc_desk.brain.agent_handoff.ai_seat_exam import (
    apply_exam_downgrade,
    validate_exam_transcript,
    validate_unresolved_claims,
)
from smc_desk.brain.ai_smc_trader_brain import parse_ai_smc_decision


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def validate_response_structure(response_dir: Path, *, require_exam: bool = False) -> list[str]:
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
        allowed = ("ai_smc_trader_decision_v1", "ai_smc_agent_response_v1", "ai_smc_agent_response_v2")
        if schema not in allowed:
            errors.append(
                f"Expected schema 'ai_smc_trader_decision_v1', 'ai_smc_agent_response_v1', or 'ai_smc_agent_response_v2', got {schema!r}"
            )
        if require_exam:
            if schema != "ai_smc_agent_response_v2":
                errors.append("A v2 packet requires ai_smc_agent_response_v2")
            if not isinstance(payload.get("exam_transcript"), Mapping):
                errors.append("A v2 packet requires exam_transcript")
    return errors


def verify_packet_integrity(packet_dir: Path) -> dict[str, Any]:
    root = Path(packet_dir)
    manifest_path = root / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Packet is missing run_manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Packet run_manifest.json is invalid: {exc}") from exc
    if manifest.get("schema") != "ai_smc_agent_packet_v2":
        return {"schema": manifest.get("schema"), "legacy": True, "manifest": manifest, "issues": []}
    issues = verify_bundled_authority(root)
    for filename, expected in (manifest.get("file_hashes") or {}).items():
        path = root / str(filename)
        if not path.is_file():
            issues.append(f"missing_packet_file:{filename}")
        elif _hash_file(path) != expected:
            issues.append(f"packet_file_hash_mismatch:{filename}")
    input_hashes = manifest.get("input_file_hashes") or {}
    recomputed: dict[str, str] = {}
    for filename in input_hashes:
        path = root / str(filename)
        if path.is_file():
            recomputed[str(filename)] = _hash_file(path)
    if recomputed != input_hashes:
        issues.append("sealed_input_file_hashes_mismatch")
    if _hash_json(recomputed) != manifest.get("sealed_input_hash"):
        issues.append("sealed_input_hash_mismatch")
    if issues:
        raise ValueError("Packet integrity verification failed: " + "; ".join(sorted(set(issues))))
    return {"schema": manifest["schema"], "legacy": False, "manifest": manifest, "issues": []}


def import_agent_response(
    response_dir: Path,
    *,
    expected_packet_hash: str | None = None,
    packet_dir: Path | None = None,
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
    packet_verification: dict[str, Any] | None = None
    authority_manifest: dict[str, Any] = {}
    evidence_pack: dict[str, Any] = {}
    require_exam = False
    packet_manifest: dict[str, Any] = {}
    if packet_dir is not None:
        packet_verification = verify_packet_integrity(packet_dir)
        packet_manifest = packet_verification["manifest"]
        require_exam = not packet_verification["legacy"]
        if require_exam:
            authority_manifest = json.loads(
                (Path(packet_dir) / "00_authority_manifest.json").read_text(encoding="utf-8")
            )
            evidence_pack = json.loads(
                (Path(packet_dir) / "02_evidence_pack.json").read_text(encoding="utf-8")
            )
            sealed_hash = str(packet_manifest.get("sealed_input_hash") or "")
            if expected_packet_hash is not None and expected_packet_hash != sealed_hash:
                raise ValueError("Caller expected packet hash does not match the sealed packet input hash")
            expected_packet_hash = sealed_hash

    errors = validate_response_structure(response_dir, require_exam=require_exam)
    if errors:
        raise ValueError(f"Invalid agent response: {'; '.join(errors)}")

    decision_payload = json.loads((response_dir / "official_decision_candidate.json").read_text(encoding="utf-8"))

    if isinstance(decision_payload, Mapping) and "decision" in decision_payload and isinstance(decision_payload["decision"], Mapping):
        response_metadata = {k: decision_payload[k] for k in decision_payload if k != "decision"}
        decision_payload = decision_payload["decision"]
    else:
        response_metadata = {
            k: decision_payload.pop(k) for k in list(decision_payload.keys())
            if k in (
                "agent_identity",
                "packet_hash",
                "semantic_anchors",
                "agent_reasoning_notes",
                "requested_more_context",
                "exam_transcript",
                "dissent_records",
                "doctrine_pending_claims",
            )
        }

    response_packet_hash = response_metadata.get("packet_hash") or response_metadata.get("agent_identity", {}).get("packet_hash", "")
    packet_hash_match = (expected_packet_hash is None) or response_packet_hash == expected_packet_hash
    if require_exam and not packet_hash_match:
        raise ValueError("Agent response packet_hash does not match the sealed packet input hash")

    exam_validation: dict[str, Any] | None = None
    unresolved_claim_validation: dict[str, Any] | None = None
    if require_exam:
        exam_validation = validate_exam_transcript(
            response_metadata.get("exam_transcript"),
            authority_manifest=authority_manifest,
            evidence_pack=evidence_pack,
            expected_packet_hash=str(expected_packet_hash or ""),
            expected_decision_time=str(packet_manifest.get("decision_time") or ""),
        )
        structural_exam_codes = {
            "invalid_exam_schema",
            "exam_self_certification_forbidden",
            "exam_independent_validation_missing",
            "exam_signal_authority_forbidden",
        }
        structural_exam_failure = any(
            str(item.get("code") or "").startswith(
                ("exam_binding_mismatch:", "missing_exam_station:", "duplicate_exam_station:", "unknown_exam_station:")
            )
            or item.get("code") in structural_exam_codes
            for item in exam_validation.get("issues") or []
            if isinstance(item, Mapping)
        )
        if structural_exam_failure:
            codes = [str(item.get("code")) for item in exam_validation["issues"]]
            raise ValueError("AI seat exam integrity failed: " + "; ".join(codes))
        unresolved_claim_validation = validate_unresolved_claims(
            dissent_records=response_metadata.get("dissent_records"),
            doctrine_pending_claims=response_metadata.get("doctrine_pending_claims"),
            authority_manifest=authority_manifest,
            evidence_pack=evidence_pack,
        )
        if unresolved_claim_validation["downgrade_required"]:
            exam_validation = dict(exam_validation)
            exam_validation["downgrade_required"] = True
            exam_validation["failed_stations"] = list(exam_validation.get("failed_stations") or []) + [
                "UNRESOLVED_DISSENT_OR_DOCTRINE"
            ]
            exam_validation["issues"] = list(exam_validation.get("issues") or []) + list(
                unresolved_claim_validation.get("issues") or []
            )
            exam_validation["status"] = "FAIL_CLOSED"
        decision_payload = apply_exam_downgrade(decision_payload, exam_validation)

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
        "packet_integrity_verified": bool(packet_verification and not packet_verification.get("legacy")),
        "exam_validation_status": exam_validation.get("status") if exam_validation else "LEGACY_NOT_REQUIRED",
        "exam_downgrade_applied": bool(exam_validation and exam_validation.get("downgrade_required")),
        "dissent_record_count": len(response_metadata.get("dissent_records") or []),
        "doctrine_pending_claim_count": len(response_metadata.get("doctrine_pending_claims") or []),
        "unresolved_claim_validation_status": unresolved_claim_validation.get("status") if unresolved_claim_validation else "LEGACY_NOT_REQUIRED",
    }

    return {
        "decision": decision,
        "decision_payload": decision_payload,
        "agent_identity": response_metadata.get("agent_identity", {}),
        "semantic_anchors": response_metadata.get("semantic_anchors", {}),
        "agent_reasoning": reasoning,
        "annotation_plan": annotation_plan,
        "requested_more_context": requested_more_context,
        "exam_transcript": response_metadata.get("exam_transcript"),
        "exam_validation": exam_validation,
        "unresolved_claim_validation": unresolved_claim_validation,
        "dissent_records": response_metadata.get("dissent_records") or [],
        "doctrine_pending_claims": response_metadata.get("doctrine_pending_claims") or [],
        "audit": audit,
    }
