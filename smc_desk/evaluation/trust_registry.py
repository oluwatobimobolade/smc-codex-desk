"""Provision and pin independent Ed25519 identities for an interrogation cohort."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ALLOWED_ROLES = {
    "reviewer",
    "adjudicator",
    "system_operator",
    "visual_auditor",
    "calibration_authority",
}


def provision_cohort_trust_registry(
    cohort_root: str | Path,
    signers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    root = Path(cohort_root).expanduser().resolve()
    manifest_path = root / "cohort_manifest.json"
    ledger_path = root / "access_ledger.json"
    if not manifest_path.is_file() or not ledger_path.is_file():
        raise FileNotFoundError("Cohort manifest and access ledger are required")
    manifest = _load(manifest_path)
    validated = _validate_signers(signers)
    key_root = root / "trust_keys"
    key_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for signer in validated:
        signer_id = str(signer["signer_id"])
        source = Path(signer["public_key_path"]).expanduser().resolve()
        target = key_root / f"{signer_id}.public.pem"
        shutil.copyfile(source, target)
        entries.append(
            {
                "signer_id": signer_id,
                "role": str(signer["role"]),
                "public_key_file": str(target.relative_to(root)),
                "public_key_sha256": _file_sha256(target),
                "active": True,
            }
        )
    registry = {
        "schema": "smc_evidence_trust_registry_v1",
        "registry_id": f"{manifest.get('cohort_id')}-TRUST-V1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cohort_id": manifest.get("cohort_id"),
        "independence_policy": {
            "distinct_public_key_per_identity": True,
            "minimum_reviewer_count": 2,
            "required_roles": sorted(ALLOWED_ROLES),
            "self_signed_system_evidence_is_insufficient": True,
        },
        "signers": entries,
    }
    registry_path = root / "trust_registry.json"
    _write(registry_path, registry)
    registry_hash = _file_sha256(registry_path)
    previous_content_hash = manifest.get("cohort_content_sha256")
    manifest.update(
        {
            "trust_registry_path": str(registry_path),
            "trust_registry_sha256": registry_hash,
            "trust_registry_status": "PROVISIONED",
            "certification_blockers": [
                item for item in manifest.get("certification_blockers") or []
                if item != "trust_registry_unprovisioned"
            ],
        }
    )
    manifest["cohort_content_sha256"] = _hash(
        {
            "cases": manifest.get("cases") or [],
            "identity_sha256": manifest.get("sealed_identity_map_sha256"),
            "no_evidence": manifest.get("no_evidence_pack") or {},
            "system_code_freeze_sha256": manifest.get("system_code_freeze_sha256"),
            "trust_registry_sha256": registry_hash,
        }
    )
    _write(manifest_path, manifest)
    ledger = _load(ledger_path)
    events = list(ledger.get("events") or [])
    events.append(
        {
            "event": "TRUST_REGISTRY_PROVISIONED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": "independent_key_provisioning_tool",
            "registry_sha256": registry_hash,
            "previous_cohort_content_sha256": previous_content_hash,
            "new_cohort_content_sha256": manifest["cohort_content_sha256"],
            "signer_ids": [entry["signer_id"] for entry in entries],
        }
    )
    ledger["events"] = events
    _write(ledger_path, ledger)
    return {
        "schema": "smc_cohort_trust_provisioning_result_v1",
        "cohort_id": manifest.get("cohort_id"),
        "registry_path": str(registry_path),
        "registry_sha256": registry_hash,
        "signer_count": len(entries),
        "reviewer_count": sum(entry["role"] == "reviewer" for entry in entries),
        "cohort_content_sha256": manifest["cohort_content_sha256"],
        "status": "PROVISIONED",
        "note": "Append the new cohort hash to the external/governance audit record before collecting signatures.",
    }


def _validate_signers(signers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in signers]
    ids = [str(item.get("signer_id") or "") for item in rows]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in ids):
        raise ValueError("Signer IDs must be unique and filesystem-safe")
    roles = [str(item.get("role") or "") for item in rows]
    if any(role not in ALLOWED_ROLES for role in roles):
        raise ValueError("Unknown signer role")
    if roles.count("reviewer") < 2:
        raise ValueError("At least two independent reviewer identities are required")
    missing_roles = sorted(ALLOWED_ROLES.difference(roles))
    if missing_roles:
        raise ValueError(f"Missing required trust roles: {missing_roles}")
    key_hashes: list[str] = []
    for row in rows:
        path = Path(row.get("public_key_path") or "").expanduser().resolve()
        if not path.is_file() or not _valid_ed25519_public_key(path):
            raise ValueError(f"Invalid Ed25519 public key: {path}")
        row["public_key_path"] = str(path)
        key_hashes.append(_file_sha256(path))
    if len(key_hashes) != len(set(key_hashes)):
        raise ValueError("Every trusted identity must use a distinct public key")
    return rows


def _valid_ed25519_public_key(path: Path) -> bool:
    result = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(path), "-pubcheck", "-noout"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and "Key is valid" in result.stdout


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["ALLOWED_ROLES", "provision_cohort_trust_registry"]
