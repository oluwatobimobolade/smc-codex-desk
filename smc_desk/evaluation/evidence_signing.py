"""Ed25519 evidence envelopes backed by an explicit public-key trust registry."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ENVELOPE_SCHEMA = "smc_signed_evidence_envelope_v1"
TRUST_REGISTRY_SCHEMA = "smc_evidence_trust_registry_v1"


def sign_evidence_payload(
    *,
    payload_path: str | Path,
    envelope_path: str | Path,
    private_key_path: str | Path,
    evidence_type: str,
    subject_id: str,
    cohort_content_sha256: str,
    system_code_freeze_sha256: str,
    signer_id: str,
    signer_role: str,
    signed_at: str | None = None,
) -> dict[str, Any]:
    payload = Path(payload_path).expanduser().resolve()
    envelope = Path(envelope_path).expanduser().resolve()
    private_key = Path(private_key_path).expanduser().resolve()
    if not payload.is_file() or not private_key.is_file():
        raise FileNotFoundError(payload if not payload.is_file() else private_key)
    envelope.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload_file = str(payload.relative_to(envelope.parent))
    except ValueError as exc:
        raise ValueError("Signed payload must be stored under the envelope directory") from exc
    statement = {
        "schema": ENVELOPE_SCHEMA,
        "evidence_type": evidence_type,
        "subject_id": subject_id,
        "payload_file": payload_file,
        "payload_sha256": _file_sha256(payload),
        "cohort_content_sha256": cohort_content_sha256,
        "system_code_freeze_sha256": system_code_freeze_sha256,
        "signer_id": signer_id,
        "signer_role": signer_role,
        "signed_at": signed_at or datetime.now(timezone.utc).isoformat(),
        "signature_algorithm": "ED25519",
    }
    signature = _openssl_sign(_canonical(statement), private_key)
    result = {
        **statement,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
        "statement_sha256": _sha256(_canonical(statement)),
    }
    result["envelope_sha256"] = _hash({key: value for key, value in result.items() if key != "envelope_sha256"})
    envelope.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def verify_evidence_envelope(
    envelope_path: str | Path,
    *,
    trust_registry_path: str | Path,
    allowed_roles: Iterable[str],
    expected_evidence_type: str | None = None,
    expected_subject_id: str | None = None,
    expected_cohort_content_sha256: str | None = None,
    expected_system_code_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    envelope_path = Path(envelope_path).expanduser().resolve()
    registry_path = Path(trust_registry_path).expanduser().resolve()
    issues: list[str] = []
    if not envelope_path.is_file():
        return _verification(envelope_path, None, ["missing_evidence_envelope"])
    if not registry_path.is_file():
        return _verification(envelope_path, None, ["missing_trust_registry"])
    try:
        envelope = _load_json(envelope_path)
        registry = _load_json(registry_path)
    except Exception as exc:
        return _verification(envelope_path, None, [f"json_error:{type(exc).__name__}"])
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        issues.append("invalid_envelope_schema")
    if registry.get("schema") != TRUST_REGISTRY_SCHEMA:
        issues.append("invalid_trust_registry_schema")
    if envelope.get("signature_algorithm") != "ED25519":
        issues.append("unsupported_signature_algorithm")
    statement = {
        key: envelope.get(key)
        for key in (
            "schema",
            "evidence_type",
            "subject_id",
            "payload_file",
            "payload_sha256",
            "cohort_content_sha256",
            "system_code_freeze_sha256",
            "signer_id",
            "signer_role",
            "signed_at",
            "signature_algorithm",
        )
    }
    if envelope.get("statement_sha256") != _sha256(_canonical(statement)):
        issues.append("statement_hash_mismatch")
    expected_envelope_hash = _hash({key: value for key, value in envelope.items() if key != "envelope_sha256"})
    if envelope.get("envelope_sha256") != expected_envelope_hash:
        issues.append("envelope_hash_mismatch")
    payload_path = _safe_child(envelope_path.parent, str(envelope.get("payload_file") or ""))
    if payload_path is None or not payload_path.is_file():
        issues.append("missing_or_unsafe_payload_path")
    elif _file_sha256(payload_path) != envelope.get("payload_sha256"):
        issues.append("payload_hash_mismatch")
    if expected_evidence_type is not None and envelope.get("evidence_type") != expected_evidence_type:
        issues.append("evidence_type_mismatch")
    if expected_subject_id is not None and envelope.get("subject_id") != expected_subject_id:
        issues.append("subject_id_mismatch")
    if expected_cohort_content_sha256 is not None and envelope.get("cohort_content_sha256") != expected_cohort_content_sha256:
        issues.append("cohort_hash_mismatch")
    if expected_system_code_freeze_sha256 is not None and envelope.get("system_code_freeze_sha256") != expected_system_code_freeze_sha256:
        issues.append("system_code_freeze_hash_mismatch")
    allowed = set(map(str, allowed_roles))
    if str(envelope.get("signer_role")) not in allowed:
        issues.append("signer_role_not_allowed")
    signer = next(
        (
            item
            for item in registry.get("signers") or []
            if item.get("signer_id") == envelope.get("signer_id")
        ),
        None,
    )
    if not isinstance(signer, Mapping):
        issues.append("signer_not_trusted")
    else:
        if signer.get("active") is not True:
            issues.append("signer_inactive_or_revoked")
        if signer.get("role") != envelope.get("signer_role"):
            issues.append("signer_role_registry_mismatch")
        public_key_path = _safe_child(registry_path.parent, str(signer.get("public_key_file") or ""))
        if public_key_path is None or not public_key_path.is_file():
            issues.append("missing_or_unsafe_public_key")
        elif _file_sha256(public_key_path) != signer.get("public_key_sha256"):
            issues.append("public_key_hash_mismatch")
        elif not issues:
            try:
                signature = base64.b64decode(str(envelope.get("signature_base64") or ""), validate=True)
                if not _openssl_verify(_canonical(statement), signature, public_key_path):
                    issues.append("signature_verification_failed")
            except Exception:
                issues.append("invalid_signature_encoding")
    return _verification(envelope_path, payload_path, issues, signer_id=envelope.get("signer_id"), signer_role=envelope.get("signer_role"))


def _openssl_sign(message: bytes, private_key: Path) -> bytes:
    with tempfile.TemporaryDirectory() as temporary:
        message_path = Path(temporary) / "message.bin"
        signature_path = Path(temporary) / "signature.bin"
        message_path.write_bytes(message)
        result = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(private_key), "-in", str(message_path), "-out", str(signature_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"OpenSSL Ed25519 signing failed: {result.stderr.strip()}")
        return signature_path.read_bytes()


def _openssl_verify(message: bytes, signature: bytes, public_key: Path) -> bool:
    with tempfile.TemporaryDirectory() as temporary:
        message_path = Path(temporary) / "message.bin"
        signature_path = Path(temporary) / "signature.bin"
        message_path.write_bytes(message)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(public_key), "-in", str(message_path), "-sigfile", str(signature_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0


def _safe_child(root: Path, relative: str) -> Path | None:
    if not relative or Path(relative).is_absolute():
        return None
    candidate = (root / relative).resolve()
    return candidate if candidate.is_relative_to(root.resolve()) else None


def _verification(
    envelope_path: Path,
    payload_path: Path | None,
    issues: list[str],
    *,
    signer_id: Any = None,
    signer_role: Any = None,
) -> dict[str, Any]:
    return {
        "schema": "smc_signed_evidence_verification_v1",
        "envelope_path": str(envelope_path),
        "payload_path": str(payload_path) if payload_path else None,
        "signer_id": signer_id,
        "signer_role": signer_role,
        "issues": issues,
        "status": "PASS" if not issues else "FAIL",
    }


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    return payload


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash(payload: Any) -> str:
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


__all__ = [
    "ENVELOPE_SCHEMA",
    "TRUST_REGISTRY_SCHEMA",
    "sign_evidence_payload",
    "verify_evidence_envelope",
]
