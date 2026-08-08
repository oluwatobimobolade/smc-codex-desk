from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import subprocess

import pytest

from smc_desk.evaluation.calibration import (
    enforce_authority_mode,
    issue_calibration_certificate,
    verify_calibration_certificate,
)
from smc_desk.evaluation.evidence_signing import sign_evidence_payload


def _certificate(**changes):
    values = {
        "gold_set_version": "gold-v1",
        "gold_set_hash": "gold-hash",
        "model_name": "vision-model",
        "model_version": "1",
        "prompt_version": "1",
        "evaluation_timestamp": datetime.now(timezone.utc),
        "approved_authority_level": "calibrated_veto",
        "approver": "CAL",
        "adjudicated_case_count": 30,
        "calibration_record_count": 50,
        "expected_calibration_error": 0.05,
        "brier_score": 0.08,
        "perturbation_consistency_rate": 0.98,
        "abstention_test_passed": True,
    }
    values.update(changes)
    return issue_calibration_certificate(**values)


def _signed_certificate(tmp_path, certificate):
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
    registry = tmp_path / "trust_registry.json"
    registry.write_text(json.dumps({
        "schema": "smc_evidence_trust_registry_v1",
        "registry_id": "test",
        "signers": [{
            "signer_id": "CAL",
            "role": "calibration_authority",
            "public_key_file": public.name,
            "public_key_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
            "active": True,
        }],
    }), encoding="utf-8")
    path = tmp_path / "certificate.json"
    path.write_text(json.dumps(certificate.model_dump(mode="json"), indent=2), encoding="utf-8")
    envelope = tmp_path / "certificate.json.envelope.json"
    sign_evidence_payload(
        payload_path=path,
        envelope_path=envelope,
        private_key_path=private,
        evidence_type="calibration_certificate",
        subject_id="COHORT-1",
        cohort_content_sha256="cohort-hash",
        system_code_freeze_sha256="system-hash",
        signer_id="CAL",
        signer_role="calibration_authority",
    )
    config = {
        "cohort_id": "COHORT-1",
        "cohort_content_sha256": "cohort-hash",
        "system_code_freeze_sha256": "system-hash",
        "trust_registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
    }
    kwargs = {
        "certificate_path": str(path),
        "certificate_envelope_path": str(envelope),
        "trust_registry_path": str(registry),
    }
    return config, kwargs


def test_valid_hash_sealed_certificate_allows_only_approved_authority(tmp_path) -> None:
    certificate = _certificate()
    verify_calibration_certificate(certificate)
    context, kwargs = _signed_certificate(tmp_path, certificate)
    enforce_authority_mode({**context, "vision_authority_mode": "review_flag"}, certificate, **kwargs)
    enforce_authority_mode({**context, "vision_authority_mode": "calibrated_veto"}, certificate, **kwargs)
    with pytest.raises(ValueError, match="not requested full_fusion"):
        enforce_authority_mode({**context, "vision_authority_mode": "full_fusion"}, certificate, **kwargs)


def test_unsigned_certificate_cannot_enable_authority() -> None:
    certificate = _certificate()
    with pytest.raises(ValueError, match="signed calibration"):
        enforce_authority_mode({
            "vision_authority_mode": "calibrated_veto",
            "cohort_id": "COHORT-1",
            "cohort_content_sha256": "cohort-hash",
            "system_code_freeze_sha256": "system-hash",
            "trust_registry_sha256": "missing-trust-hash",
        }, certificate)


def test_tampered_certificate_is_rejected() -> None:
    certificate = _certificate().model_copy(update={"gold_set_hash": "tampered"})
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_calibration_certificate(certificate)


def test_insufficient_evidence_cannot_receive_authority() -> None:
    certificate = _certificate(adjudicated_case_count=2)
    with pytest.raises(ValueError, match="insufficient adjudicated"):
        enforce_authority_mode({"vision_authority_mode": "calibrated_veto"}, certificate)
