"""Blind adjudication and weighted scoring for SMC interrogation cases."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_desk.evaluation.interrogation_cohort import CATASTROPHIC_GATES, DIMENSION_WEIGHTS
from smc_desk.evaluation.evidence_signing import verify_evidence_envelope


def validate_independent_reviewer_submission(payload: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if payload.get("schema") != "smc_interrogation_independent_review_v1":
        issues.append("invalid_reviewer_schema")
    if not payload.get("case_id"):
        issues.append("missing_case_id")
    if not payload.get("reviewer_id"):
        issues.append("missing_reviewer_id")
    if payload.get("independent_review_attested") is not True:
        issues.append("independent_review_not_attested")
    if payload.get("engine_output_seen") is not False:
        issues.append("reviewer_saw_engine_output")
    if not payload.get("doctrine_hash"):
        issues.append("missing_doctrine_hash")
    if not payload.get("completed_at"):
        issues.append("missing_completed_at")
    if not payload.get("signature"):
        issues.append("missing_signature")
    dimensions = payload.get("dimension_judgments") or {}
    if set(dimensions) != set(DIMENSION_WEIGHTS):
        issues.append("dimension_set_mismatch")
    for name in DIMENSION_WEIGHTS:
        row = dimensions.get(name) or {}
        score = row.get("score_0_to_100")
        if not _bounded_score(score):
            issues.append(f"invalid_dimension_score:{name}")
        if not isinstance(row.get("evidence"), list):
            issues.append(f"invalid_dimension_evidence:{name}")
    answers = payload.get("hard_question_answers") or []
    if len(answers) != 20:
        issues.append("hard_question_count_mismatch")
    for index, answer in enumerate(answers, start=1):
        if answer.get("answer") in {None, ""} and answer.get("abstain") is not True:
            issues.append(f"hard_question_unanswered:{index}")
    gates = payload.get("catastrophic_error_observed") or {}
    if set(gates) != set(CATASTROPHIC_GATES) or any(value not in {True, False} for value in gates.values()):
        issues.append("catastrophic_gate_labels_incomplete")
    if payload.get("expected_official_state") is None:
        issues.append("missing_expected_official_state")
    if payload.get("expected_direction") is None:
        issues.append("missing_expected_direction")
    if not isinstance(payload.get("annotation_plan_v2"), Mapping):
        issues.append("missing_reviewer_annotation_plan")
    return issues


def validate_system_submission(payload: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if payload.get("schema") != "smc_interrogation_system_submission_v1":
        issues.append("invalid_system_submission_schema")
    for field in ("case_id", "frozen_at", "source_manifest_sha256", "system_code_freeze_sha256", "official_state", "direction"):
        if payload.get(field) is None:
            issues.append(f"missing_system_field:{field}")
    if not isinstance(payload.get("object_evidence_contracts"), list):
        issues.append("system_object_contracts_must_be_list")
    answers = payload.get("hard_question_answers") or []
    if len(answers) != 20:
        issues.append("system_hard_question_count_mismatch")
    for index, answer in enumerate(answers, start=1):
        if answer.get("answer") in {None, ""} and answer.get("abstain") is not True:
            issues.append(f"system_hard_question_unanswered:{index}")
    if not isinstance(payload.get("annotation_plan_v2"), Mapping):
        issues.append("missing_system_annotation_plan")
    return issues


def build_system_submission_template(
    case_id: str, source_manifest_sha256: str, system_code_freeze_sha256: str = "UNSET"
) -> dict[str, Any]:
    return {
        "schema": "smc_interrogation_system_submission_v1",
        "case_id": case_id,
        "frozen_at": None,
        "source_manifest_sha256": source_manifest_sha256,
        "system_code_freeze_sha256": system_code_freeze_sha256,
        "official_state": None,
        "direction": None,
        "active_poi": None,
        "invalidation": None,
        "target": None,
        "object_evidence_contracts": [],
        "hard_question_answers": [
            {
                "question_number": index,
                "answer": None,
                "evidence_contract_ids": [],
                "abstain": None,
                "raw_confidence_for_calibration": None,
            }
            for index in range(1, 21)
        ],
        "annotation_plan_v2": None,
        "runtime_causal_integrity": None,
        "poi_ranking_freeze": None,
        "signature": None,
    }


def prepare_blind_adjudication_packet(
    *,
    case_manifest_path: str | Path,
    reviewer_submission_paths: Sequence[str | Path],
    system_submission_path: str | Path,
    output_dir: str | Path,
    trust_registry_path: str | Path,
    cohort_manifest_path: str | Path,
) -> dict[str, Any]:
    if len(reviewer_submission_paths) != 2:
        raise ValueError("Exactly two independent reviewer submissions are required")
    case_manifest_path = Path(case_manifest_path).resolve()
    case_manifest = _load(case_manifest_path)
    case_id = str(case_manifest.get("case_id") or "")
    trust_path = Path(trust_registry_path).resolve()
    cohort_path = Path(cohort_manifest_path).resolve()
    cohort = _load(cohort_path)
    cohort_id = str(cohort.get("cohort_id") or "")
    cohort_hash = str(cohort.get("cohort_content_sha256") or "")
    system_freeze_hash = str(cohort.get("system_code_freeze_sha256") or "")
    if not cohort_id or not cohort_hash or not system_freeze_hash:
        raise ValueError("Cohort authority manifest is incomplete")
    if cohort.get("trust_registry_status") != "PROVISIONED" or cohort.get("trust_registry_sha256") != _file_sha256(trust_path):
        raise ValueError("Trust registry is not provisioned and pinned by the cohort authority manifest")
    reviewers = [(_load(Path(path).resolve()), Path(path).resolve()) for path in reviewer_submission_paths]
    reviewer_issues = [validate_independent_reviewer_submission(payload) for payload, _ in reviewers]
    if any(reviewer_issues):
        raise ValueError(f"Reviewer submissions are incomplete: {reviewer_issues}")
    reviewer_ids = [str(payload["reviewer_id"]) for payload, _ in reviewers]
    if len(set(reviewer_ids)) != 2:
        raise ValueError("Reviewer identities must be distinct")
    if any(str(payload.get("case_id")) != case_id for payload, _ in reviewers):
        raise ValueError("Reviewer case ID does not match case manifest")
    reviewer_signatures = [
        _require_signature(
            path,
            trust_registry_path=trust_path,
            evidence_type="independent_review",
            subject_id=case_id,
            cohort_content_sha256=cohort_hash,
            system_code_freeze_sha256=system_freeze_hash,
            allowed_roles={"reviewer"},
        )
        for _, path in reviewers
    ]
    if [item.get("signer_id") for item in reviewer_signatures] != reviewer_ids:
        raise ValueError("Reviewer signature identities do not match reviewer submissions")
    if len({item.get("signer_id") for item in reviewer_signatures}) != 2:
        raise ValueError("Independent reviews require two distinct signing identities")
    system_path = Path(system_submission_path).resolve()
    system = _load(system_path)
    system_issues = validate_system_submission(system)
    if system_issues:
        raise ValueError(f"System submission is incomplete: {system_issues}")
    if str(system.get("case_id")) != case_id:
        raise ValueError("System case ID does not match case manifest")
    if str(system.get("system_code_freeze_sha256")) != system_freeze_hash:
        raise ValueError("System submission does not match frozen system source")
    expected_case_evidence_hash = _hash(case_manifest.get("candle_map_sha256") or {})
    if str(system.get("source_manifest_sha256")) != expected_case_evidence_hash:
        raise ValueError("System submission does not match frozen case evidence")
    system_signature = _require_signature(
        system_path,
        trust_registry_path=trust_path,
        evidence_type="system_submission",
        subject_id=case_id,
        cohort_content_sha256=cohort_hash,
        system_code_freeze_sha256=system_freeze_hash,
        allowed_roles={"system_operator"},
    )

    sources = [
        ("human_reviewer", payload, path, reviewer_ids[index])
        for index, (payload, path) in enumerate(reviewers)
    ] + [("system", system, system_path, "SYSTEM")]
    anonymous: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    for role, payload, path, identity in sources:
        source_hash = _file_sha256(path)
        anonymous_id = f"SUB-{hashlib.sha256((case_id + source_hash).encode()).hexdigest()[:10].upper()}"
        public_payload = _anonymise_submission(payload, anonymous_id)
        anonymous.append({"submission_id": anonymous_id, "payload": public_payload, "source_sha256": source_hash})
        identities.append({"submission_id": anonymous_id, "role": role, "identity": identity, "source_path": str(path), "source_sha256": source_hash})
    anonymous.sort(key=lambda item: item["submission_id"])

    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    submissions_path = root / "anonymous_submissions.json"
    _write(submissions_path, {"schema": "smc_anonymous_submission_bundle_v1", "case_id": case_id, "submissions": anonymous})
    adjudication_path = root / "adjudication.json"
    _write(
        adjudication_path,
        {
            "schema": "smc_interrogation_blind_adjudication_v1",
            "case_id": case_id,
            "anonymous_submission_bundle_sha256": _file_sha256(submissions_path),
            "adjudicator_id": None,
            "identity_of_system_submission_known": False,
            "submission_assessments": {
                item["submission_id"]: {
                    "dimension_scores": {name: None for name in DIMENSION_WEIGHTS},
                    "catastrophic_errors": {gate: None for gate in CATASTROPHIC_GATES},
                    "object_precision": None,
                    "object_recall": None,
                    "anchor_coordinate_error": None,
                    "price_coordinate_error": None,
                    "causal_edge_accuracy": None,
                    "event_order_accuracy": None,
                    "abstention_quality": None,
                    "hard_question_correctness": {str(index): None for index in range(1, 21)},
                    "reasoning_summary": None,
                }
                for item in anonymous
            },
            "resolved_object_evidence_contracts": [],
            "preserved_expert_disagreements": [],
            "completed_at": None,
            "signature": None,
            "adjudication_status": "pending",
        },
    )
    identity_path = root.parent / f"{case_id}_private_identity_map.json"
    identity_payload = {
        "schema": "smc_blind_adjudication_identity_map_v1",
        "case_id": case_id,
        "identities": identities,
        "anonymous_submission_bundle_sha256": _file_sha256(submissions_path),
    }
    identity_payload["identity_map_sha256"] = _hash({key: value for key, value in identity_payload.items() if key != "identity_map_sha256"})
    _write(identity_path, identity_payload)
    packet = {
        "schema": "smc_blind_adjudication_packet_v1",
        "case_id": case_id,
        "case_manifest_path": str(case_manifest_path),
        "case_manifest_sha256": _file_sha256(case_manifest_path),
        "anonymous_submissions_path": str(submissions_path),
        "anonymous_submissions_sha256": _file_sha256(submissions_path),
        "adjudication_path": str(adjudication_path),
        "private_identity_map_path": str(identity_path),
        "private_identity_map_sha256": _file_sha256(identity_path),
        "trust_registry_path": str(trust_path),
        "trust_registry_sha256": _file_sha256(trust_path),
        "cohort_manifest_path": str(cohort_path),
        "cohort_manifest_sha256": _file_sha256(cohort_path),
        "cohort_id": cohort_id,
        "cohort_content_sha256": cohort_hash,
        "system_code_freeze_sha256": system_freeze_hash,
        "pinned_trust_registry_sha256": str(cohort.get("trust_registry_sha256")),
        "reviewer_signature_verifications": reviewer_signatures,
        "system_signature_verification": system_signature,
        "status": "READY_FOR_BLIND_ADJUDICATION",
    }
    _write(root / "packet_manifest.json", packet)
    return packet


def score_completed_blind_adjudication(packet_manifest_path: str | Path) -> dict[str, Any]:
    packet_path = Path(packet_manifest_path).resolve()
    packet = _load(packet_path)
    issues: list[str] = []
    for field, hash_field in (
        ("case_manifest_path", "case_manifest_sha256"),
        ("anonymous_submissions_path", "anonymous_submissions_sha256"),
        ("private_identity_map_path", "private_identity_map_sha256"),
        ("trust_registry_path", "trust_registry_sha256"),
        ("cohort_manifest_path", "cohort_manifest_sha256"),
    ):
        path = Path(packet.get(field) or "")
        if not path.is_file() or _file_sha256(path) != packet.get(hash_field):
            issues.append(f"source_hash_mismatch:{field}")
    adjudication = _load(Path(packet.get("adjudication_path") or ""))
    if adjudication.get("adjudication_status") != "adjudicated":
        issues.append("adjudication_not_complete")
    if not adjudication.get("adjudicator_id") or not adjudication.get("completed_at") or not adjudication.get("signature"):
        issues.append("adjudicator_provenance_incomplete")
    if adjudication.get("identity_of_system_submission_known") is not False:
        issues.append("blindness_attestation_failed")
    adjudication_signature = verify_evidence_envelope(
        str(Path(packet.get("adjudication_path") or "").with_name("adjudication.json.envelope.json")),
        trust_registry_path=str(packet.get("trust_registry_path") or ""),
        allowed_roles={"adjudicator"},
        expected_evidence_type="blind_adjudication",
        expected_subject_id=str(packet.get("case_id") or ""),
        expected_cohort_content_sha256=str(packet.get("cohort_content_sha256") or ""),
        expected_system_code_freeze_sha256=str(packet.get("system_code_freeze_sha256") or ""),
    )
    if adjudication_signature.get("status") != "PASS":
        issues.append(f"adjudication_signature_rejected:{','.join(adjudication_signature.get('issues') or [])}")
    elif adjudication_signature.get("signer_id") != adjudication.get("adjudicator_id"):
        issues.append("adjudicator_signature_identity_mismatch")
    identity_map = _load(Path(packet.get("private_identity_map_path") or ""))
    for identity in identity_map.get("identities") or []:
        source_path = Path(identity.get("source_path") or "")
        if not source_path.is_file() or _file_sha256(source_path) != identity.get("source_sha256"):
            issues.append(f"original_submission_hash_mismatch:{identity.get('submission_id')}")
    system_identity_rows = [item for item in identity_map.get("identities") or [] if item.get("role") == "system"]
    if len(system_identity_rows) != 1:
        issues.append("system_identity_resolution_failed")
        system_id = None
    else:
        system_id = system_identity_rows[0]["submission_id"]
    assessment = (adjudication.get("submission_assessments") or {}).get(system_id or "") or {}
    dimensions = assessment.get("dimension_scores") or {}
    if set(dimensions) != set(DIMENSION_WEIGHTS) or any(not _bounded_score(value) for value in dimensions.values()):
        issues.append("system_dimension_scores_incomplete")
    gates = assessment.get("catastrophic_errors") or {}
    if set(gates) != set(CATASTROPHIC_GATES) or any(value not in {True, False} for value in gates.values()):
        issues.append("system_catastrophic_gates_incomplete")
    question_correctness = assessment.get("hard_question_correctness") or {}
    if set(question_correctness) != {str(index) for index in range(1, 21)} or any(
        value not in {True, False} for value in question_correctness.values()
    ):
        issues.append("system_hard_question_correctness_incomplete")
    score = None
    failed_gates: list[str] = []
    calibration_records: list[dict[str, Any]] = []
    if not issues:
        score = sum(float(dimensions[name]) * weight / 100.0 for name, weight in DIMENSION_WEIGHTS.items())
        failed_gates = sorted(name for name, failed in gates.items() if failed)
        system_payload = _load(Path(system_identity_rows[0]["source_path"]))
        for answer in system_payload.get("hard_question_answers") or []:
            number = str(answer.get("question_number"))
            confidence = answer.get("raw_confidence_for_calibration")
            if confidence is None:
                continue
            try:
                numeric_confidence = float(confidence)
            except (TypeError, ValueError):
                continue
            if 0.0 <= numeric_confidence <= 1.0 and number in question_correctness:
                calibration_records.append(
                    {
                        "case_id": packet.get("case_id"),
                        "question_number": int(number),
                        "truth_source": "human_adjudicated",
                        "confidence": numeric_confidence,
                        "correct": bool(question_correctness[number]),
                    }
                )
    return {
        "schema": "smc_blind_adjudication_case_score_v1",
        "case_id": packet.get("case_id"),
        "system_submission_id": system_id,
        "dimension_scores": dimensions if not issues else {},
        "weighted_score": score,
        "failed_catastrophic_gates": failed_gates,
        "calibration_records": calibration_records,
        "adjudication_signature_verification": adjudication_signature,
        "issues": issues,
        "status": "PASS_100" if score == 100.0 and not failed_gates else "FAIL" if score is not None else "INSUFFICIENT_ADJUDICATION",
        "score_is_perception_accuracy": True if score is not None else False,
    }


def aggregate_blind_case_scores(case_scores: Sequence[Mapping[str, Any]], *, minimum_cases: int = 30) -> dict[str, Any]:
    seen: set[str] = set()
    duplicate_case_ids: list[str] = []
    valid: list[Mapping[str, Any]] = []
    for row in case_scores:
        case_id = str(row.get("case_id") or "")
        if not case_id or row.get("weighted_score") is None:
            continue
        if case_id in seen:
            duplicate_case_ids.append(case_id)
            continue
        seen.add(case_id)
        valid.append(row)
    failed_gates = sorted({gate for row in valid for gate in row.get("failed_catastrophic_gates") or []})
    score = sum(float(row["weighted_score"]) for row in valid) / len(valid) if valid else None
    aggregate_dimensions = {
        name: sum(float((row.get("dimension_scores") or {}).get(name, 0.0)) for row in valid) / len(valid)
        for name in DIMENSION_WEIGHTS
    } if valid else {}
    complete = len(valid) >= minimum_cases
    certified_100 = (
        complete
        and not duplicate_case_ids
        and score == 100.0
        and not failed_gates
        and all(row.get("status") == "PASS_100" for row in valid)
    )
    return {
        "schema": "smc_blind_interrogation_cohort_score_v1",
        "valid_case_count": len(valid),
        "valid_case_ids": sorted(seen),
        "duplicate_case_ids": sorted(set(duplicate_case_ids)),
        "minimum_case_count": minimum_cases,
        "weighted_score": score if complete else None,
        "dimension_scores": aggregate_dimensions if complete else {},
        "failed_catastrophic_gates": failed_gates,
        "certified_100": certified_100,
        "status": "CERTIFIED_100" if certified_100 else "NOT_CERTIFIED" if complete else "INSUFFICIENT_ADJUDICATION",
        "case_scores": list(case_scores),
        "calibration_records": [record for row in valid for record in row.get("calibration_records") or []],
    }


def aggregate_blind_adjudication_packets(
    packet_manifest_paths: Sequence[str | Path], *, minimum_cases: int = 30,
) -> dict[str, Any]:
    scores = [score_completed_blind_adjudication(path) for path in packet_manifest_paths]
    return aggregate_blind_case_scores(scores, minimum_cases=minimum_cases)


def _anonymise_submission(payload: Mapping[str, Any], submission_id: str) -> dict[str, Any]:
    reviewer = payload.get("schema") == "smc_interrogation_independent_review_v1"
    answers = [
        {
            "question_number": answer.get("question_number"),
            "answer": answer.get("answer"),
            "evidence_contract_ids": list(answer.get("evidence_contract_ids") or []),
            "abstain": answer.get("abstain"),
        }
        for answer in payload.get("hard_question_answers") or []
    ]
    return {
        "schema": "smc_anonymous_interrogation_submission_v1",
        "submission_id": submission_id,
        "case_id": payload.get("case_id"),
        "state": payload.get("expected_official_state") if reviewer else payload.get("official_state"),
        "direction": payload.get("expected_direction") if reviewer else payload.get("direction"),
        "poi": payload.get("expected_poi") if reviewer else payload.get("active_poi"),
        "invalidation": payload.get("expected_invalidation") if reviewer else payload.get("invalidation"),
        "target": payload.get("expected_target") if reviewer else payload.get("target"),
        "object_evidence_contracts": list(payload.get("object_evidence_contracts") or []),
        "hard_question_answers": answers,
        "annotation_plan_v2": payload.get("annotation_plan_v2"),
    }


def _bounded_score(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return 0.0 <= numeric <= 100.0


def _require_signature(
    payload_path: Path,
    *,
    trust_registry_path: Path,
    evidence_type: str,
    subject_id: str,
    cohort_content_sha256: str,
    system_code_freeze_sha256: str,
    allowed_roles: set[str],
) -> dict[str, Any]:
    verification = verify_evidence_envelope(
        payload_path.with_name(f"{payload_path.name}.envelope.json"),
        trust_registry_path=trust_registry_path,
        allowed_roles=allowed_roles,
        expected_evidence_type=evidence_type,
        expected_subject_id=subject_id,
        expected_cohort_content_sha256=cohort_content_sha256,
        expected_system_code_freeze_sha256=system_code_freeze_sha256,
    )
    if verification.get("status") != "PASS":
        raise ValueError(f"Signed evidence rejected for {payload_path}: {verification.get('issues')}")
    return verification


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "aggregate_blind_case_scores",
    "aggregate_blind_adjudication_packets",
    "build_system_submission_template",
    "prepare_blind_adjudication_packet",
    "score_completed_blind_adjudication",
    "validate_independent_reviewer_submission",
    "validate_system_submission",
]
