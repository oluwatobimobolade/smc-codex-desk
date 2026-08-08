from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from smc_desk.evaluation.evidence_signing import sign_evidence_payload, verify_evidence_envelope


def _keys(root: Path) -> tuple[Path, Path]:
    private = root / "private.pem"
    public = root / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
    return private, public


def _registry(root: Path, public: Path) -> Path:
    path = root / "trust_registry.json"
    path.write_text(
        json.dumps({
            "schema": "smc_evidence_trust_registry_v1",
            "registry_id": "test",
            "signers": [{
                "signer_id": "reviewer-C",
                "role": "adjudicator",
                "public_key_file": public.name,
                "public_key_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
                "active": True,
            }],
        }),
        encoding="utf-8",
    )
    return path


def test_signed_evidence_envelope_verifies_and_binds_every_authority_hash(tmp_path: Path) -> None:
    private, public = _keys(tmp_path)
    registry = _registry(tmp_path, public)
    payload = tmp_path / "report.json"
    payload.write_text('{"status":"PASS"}', encoding="utf-8")
    envelope = tmp_path / "report.json.envelope.json"
    sign_evidence_payload(
        payload_path=payload,
        envelope_path=envelope,
        private_key_path=private,
        evidence_type="sweep_breakout_sequential",
        subject_id="COHORT-1",
        cohort_content_sha256="cohort-hash",
        system_code_freeze_sha256="system-hash",
        signer_id="reviewer-C",
        signer_role="adjudicator",
        signed_at="2026-07-13T00:00:00Z",
    )
    result = verify_evidence_envelope(
        envelope,
        trust_registry_path=registry,
        allowed_roles={"adjudicator"},
        expected_evidence_type="sweep_breakout_sequential",
        expected_subject_id="COHORT-1",
        expected_cohort_content_sha256="cohort-hash",
        expected_system_code_freeze_sha256="system-hash",
    )
    assert result["status"] == "PASS"


def test_payload_tampering_wrong_role_and_stale_freeze_fail(tmp_path: Path) -> None:
    private, public = _keys(tmp_path)
    registry = _registry(tmp_path, public)
    payload = tmp_path / "report.json"
    payload.write_text('{"status":"PASS"}', encoding="utf-8")
    envelope = tmp_path / "report.json.envelope.json"
    sign_evidence_payload(
        payload_path=payload,
        envelope_path=envelope,
        private_key_path=private,
        evidence_type="perturbation_consistency",
        subject_id="COHORT-1",
        cohort_content_sha256="cohort-hash",
        system_code_freeze_sha256="system-hash",
        signer_id="reviewer-C",
        signer_role="adjudicator",
    )
    payload.write_text('{"status":"FAIL"}', encoding="utf-8")
    result = verify_evidence_envelope(
        envelope,
        trust_registry_path=registry,
        allowed_roles={"visual_auditor"},
        expected_system_code_freeze_sha256="new-system-hash",
    )
    assert result["status"] == "FAIL"
    assert {"payload_hash_mismatch", "signer_role_not_allowed", "system_code_freeze_hash_mismatch"}.issubset(result["issues"])
