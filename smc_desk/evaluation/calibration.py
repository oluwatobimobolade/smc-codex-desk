"""Fail-closed calibration certificates for any non-observe vision authority."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from smc_desk.evaluation.evidence_signing import verify_evidence_envelope


AUTHORITY_RANK = {"observe_only": 0, "review_flag": 1, "calibrated_veto": 2, "full_fusion": 3}


class CalibrationCertificate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gold_set_version: str
    gold_set_hash: str
    model_name: str
    model_version: str
    prompt_version: str
    schema_version: str = "2.0.0"
    evaluation_timestamp: datetime
    approved_authority_level: str
    approver: str
    adjudicated_case_count: int = Field(ge=0)
    calibration_record_count: int = Field(ge=0)
    expected_calibration_error: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0, le=1.0)
    perturbation_consistency_rate: float = Field(ge=0.0, le=1.0)
    abstention_test_passed: bool
    certificate_hash: str


def issue_calibration_certificate(**values: Any) -> CalibrationCertificate:
    payload = {**values, "certificate_hash": ""}
    provisional = CalibrationCertificate.model_validate(payload)
    digest = _certificate_hash(provisional)
    return provisional.model_copy(update={"certificate_hash": digest})


def verify_calibration_certificate(
    certificate: CalibrationCertificate,
    *,
    minimum_adjudicated_cases: int = 30,
    minimum_calibration_records: int = 50,
    maximum_ece: float = 0.10,
    minimum_perturbation_consistency: float = 0.95,
) -> None:
    if certificate.approved_authority_level not in AUTHORITY_RANK:
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: unknown authority level")
    if certificate.certificate_hash != _certificate_hash(certificate):
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: certificate hash mismatch")
    if certificate.adjudicated_case_count < minimum_adjudicated_cases:
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: insufficient adjudicated cases")
    if certificate.calibration_record_count < minimum_calibration_records:
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: insufficient calibration records")
    if certificate.expected_calibration_error > maximum_ece:
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: expected calibration error exceeds threshold")
    if certificate.perturbation_consistency_rate < minimum_perturbation_consistency:
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: perturbation consistency below threshold")
    if not certificate.abstention_test_passed:
        raise ValueError("CALIBRATION_CERTIFICATE_INVALID: no-evidence abstention gate failed")


def enforce_authority_mode(
    config: dict[str, Any],
    certificate: CalibrationCertificate | None = None,
    *,
    certificate_path: str | None = None,
    certificate_envelope_path: str | None = None,
    trust_registry_path: str | None = None,
) -> None:
    mode = str(config.get("vision_authority_mode", "observe_only"))
    if mode not in AUTHORITY_RANK:
        raise ValueError(f"Invalid vision_authority_mode: {mode}")
    if mode == "observe_only":
        return
    if certificate is None:
        raise ValueError(
            f"STARTUP_PREVENTED: vision_authority_mode is set to '{mode}', but no valid CalibrationCertificate is present. "
            "Only 'observe_only' mode is allowed before calibration is completed."
        )
    verify_calibration_certificate(certificate)
    required_context = {
        "cohort_id": config.get("cohort_id"),
        "cohort_content_sha256": config.get("cohort_content_sha256"),
        "system_code_freeze_sha256": config.get("system_code_freeze_sha256"),
        "trust_registry_sha256": config.get("trust_registry_sha256"),
    }
    if any(value in {None, ""} for value in required_context.values()):
        raise ValueError("STARTUP_PREVENTED: signed calibration authority requires cohort and system-freeze context")
    if not certificate_path or not certificate_envelope_path or not trust_registry_path:
        raise ValueError("STARTUP_PREVENTED: non-observe authority requires a trusted signed calibration certificate")
    registry_path = Path(trust_registry_path).expanduser().resolve()
    if not registry_path.is_file() or hashlib.sha256(registry_path.read_bytes()).hexdigest() != required_context["trust_registry_sha256"]:
        raise ValueError("STARTUP_PREVENTED: trust registry does not match the pinned authority hash")
    try:
        payload = json.loads(open(certificate_path, encoding="utf-8").read())
        disk_certificate = CalibrationCertificate.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"STARTUP_PREVENTED: calibration certificate file is invalid: {type(exc).__name__}") from exc
    if disk_certificate != certificate:
        raise ValueError("STARTUP_PREVENTED: in-memory calibration certificate does not match signed file")
    signature = verify_evidence_envelope(
        certificate_envelope_path,
        trust_registry_path=trust_registry_path,
        allowed_roles={"calibration_authority"},
        expected_evidence_type="calibration_certificate",
        expected_subject_id=str(required_context["cohort_id"]),
        expected_cohort_content_sha256=str(required_context["cohort_content_sha256"]),
        expected_system_code_freeze_sha256=str(required_context["system_code_freeze_sha256"]),
    )
    if signature.get("status") != "PASS":
        raise ValueError(f"STARTUP_PREVENTED: calibration signature rejected: {signature.get('issues')}")
    if signature.get("signer_id") != certificate.approver:
        raise ValueError("STARTUP_PREVENTED: calibration signer does not match certificate approver")
    approved = certificate.approved_authority_level
    if AUTHORITY_RANK[mode] > AUTHORITY_RANK[approved]:
        raise ValueError(f"STARTUP_PREVENTED: certificate approves {approved}, not requested {mode}")


def _certificate_hash(certificate: CalibrationCertificate) -> str:
    payload = certificate.model_dump(mode="json")
    payload.pop("certificate_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "CalibrationCertificate",
    "enforce_authority_mode",
    "issue_calibration_certificate",
    "verify_calibration_certificate",
]
