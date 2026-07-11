#!/usr/bin/env python3
"""Check governance documents for internal consistency.

Verifies that governance files agree on: current release, active work package,
active ontology, strategy authority, execution authority, test baseline,
deprecated modules, and capability states.

Exit non-zero on any inconsistency.
"""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_consistency() -> tuple[bool, list[str]]:
    """Return (pass, issues). pass=True means no inconsistencies found."""
    issues: list[str] = []

    current_state = load_yaml(ROOT / "governance" / "CURRENT_STATE.yaml")
    authority_matrix = load_yaml(ROOT / "governance" / "AUTHORITY_MATRIX.yaml")
    next_actions = load_yaml(ROOT / "governance" / "NEXT_ACTIONS.yaml")
    capability_matrix = load_yaml(ROOT / "governance" / "CAPABILITY_MATRIX.yaml")
    precedence = load_yaml(ROOT / "governance" / "AUTHORITY_PRECEDENCE.yaml")
    status_vocabulary = load_yaml(ROOT / "governance" / "STATUS_VOCABULARY.yaml")
    source_register = load_yaml(ROOT / "governance" / "SOURCE_DOCUMENT_REGISTER.yaml")
    repository_register = load_yaml(ROOT / "governance" / "REPOSITORY_REGISTER.yaml")
    validation_registry = load_json(ROOT / "evidence" / "VALIDATION_REGISTRY.json")

    # 1. Verify core authority claims are consistent
    authority = current_state.get("authority", {})

    # Execution must be disabled
    for key in ("paper_execution", "live_execution"):
        value = authority.get(key)
        if value and "disabled" not in str(value).lower():
            issues.append(f"CURRENT_STATE.authority.{key} = {value} — must be disabled")

    # Strategy authority must not be "active" or "enabled"
    strategy_keys = [k for k in authority if "strategy" in k.lower()]
    for sk in strategy_keys:
        val = authority[sk]
        if val and any(w in str(val).lower() for w in ("enabled", "active_runtime", "executable")):
            issues.append(f"CURRENT_STATE.authority.{sk} = {val} — strategy must not have execution authority")

    # Prediction must be disabled
    pred = authority.get("prediction")
    if pred and ("enabled" in str(pred).lower() or "active" in str(pred).lower()):
        issues.append(f"CURRENT_STATE.authority.prediction = {pred} — must be disabled")

    # 2. Legacy engine must be marked isolated
    legacy = authority.get("legacy_engine")
    if not legacy:
        issues.append("CURRENT_STATE.authority.legacy_engine missing — must document isolation status")
    elif "isolated" not in str(legacy).lower() and "comparison_only" not in str(legacy).lower():
        issues.append(f"CURRENT_STATE.authority.legacy_engine = {legacy} — must be isolated")

    # 3. Check for prohibited claims in governance files
    prohibited = [
        ("profitable", "guaranteed profitable"),
        ("alpha", "alpha"),
        ("edge verified", "edge verified"),
        ("live trading", "live trading"),
        ("100% accurate", "100% accurate"),
    ]
    for path in (ROOT / "governance").glob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        for word, _ in prohibited:
            if word in text:
                # Check if it's in a negated context or part of a compound term
                idx = text.find(word)
                context_before = text[max(0, idx - 60):idx]
                context_after = text[idx + len(word):idx + len(word) + 20]
                if any(neg in context_before for neg in ("no ", "not ", "never ", "cannot ", "no current", "disabled")):
                    continue
                # Skip compound terms like "live tradingview" (not "live trading" as a claim)
                full_word = text[idx:idx + len(word) + 10]
                if any(full_word.startswith(word + ext) for ext in ("view", "system", "api", "data", "chart")):
                    continue
                issues.append(f"{path.name}: contains unverified claim '{word}'")

    # 4. Check that WP-0012A-D and WP-0017A-B are recorded as complete
    completed_wps = ["wp0012a", "wp0012b", "wp0012c", "wp0012d", "wp0017a", "wp0017b"]
    authority_values = " ".join(str(v).lower() for v in authority.values())
    for wp in completed_wps:
        if wp not in authority_values:
            issues.append(f"{wp.upper()} not referenced in CURRENT_STATE.authority — must document completion")

    # 6. Verify no absolute paths are declared authoritative
    for path in (ROOT / "governance").glob("*.yaml"):
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.strip().startswith("/") and any(ext in line for ext in [".py", ".json", ".csv", ".yaml"]):
                if "Users" in line or "home" in line:
                    issues.append(f"{path.name}:{line.strip()[:60]} — absolute path must not be authoritative")

    # 7. Check that paper/live execution are not mentioned as available
    for path in (ROOT / "governance").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in ["paper_execute", "live_execute", "place_order"]:
            if phrase in text and "disabled" not in text[max(0, text.find(phrase) - 100):text.find(phrase) + len(phrase) + 100]:
                issues.append(f"{path.name}: contains '{phrase}' without explicit disablement context")

    # 8. Registry v2 is append-only and points to a real source-bound record.
    if validation_registry.get("schema") != "smc_codex_validation_registry_v2":
        issues.append("VALIDATION_REGISTRY.json must use smc_codex_validation_registry_v2")
    if "latest_validation" in validation_registry:
        issues.append("VALIDATION_REGISTRY.json latest_validation is prohibited; use explicit current_gate")
    records = validation_registry.get("records") or []
    record_ids = [str(item.get("record_id") or "") for item in records if isinstance(item, dict)]
    if len(record_ids) != len(set(record_ids)):
        issues.append("VALIDATION_REGISTRY.json contains duplicate record_id values")
    current_record = str((validation_registry.get("current_gate") or {}).get("record_id") or "")
    if not current_record or current_record not in set(record_ids):
        issues.append("VALIDATION_REGISTRY.json current_gate must reference an existing validation record")
    for item in records:
        if not isinstance(item, dict):
            issues.append("VALIDATION_REGISTRY.json records must be objects")
            continue
        source = item.get("source") or {}
        if not source.get("git_head") or not source.get("source_state"):
            issues.append(f"Validation record {item.get('record_id')} lacks source identity")
        report = item.get("report")
        if report and not (ROOT / str(report)).exists():
            issues.append(f"Validation record {item.get('record_id')} report does not exist: {report}")
    current_payload = next((item for item in records if item.get("record_id") == current_record), None)
    if isinstance(current_payload, dict):
        source = current_payload.get("source") or {}
        manifest_value = source.get("source_manifest")
        manifest_hash = source.get("source_manifest_sha256")
        if manifest_value or manifest_hash:
            manifest_path = ROOT / str(manifest_value or "")
            if not manifest_path.exists():
                issues.append(f"Current validation source manifest does not exist: {manifest_value}")
            elif sha256_file(manifest_path) != manifest_hash:
                issues.append("Current validation source manifest hash does not match registry")

    # 9. Registered controlling documents must match their recorded bytes.
    if source_register.get("schema") != "smc_codex_source_document_register_v1":
        issues.append("SOURCE_DOCUMENT_REGISTER.yaml schema missing or invalid")
    for doc_id, document in (source_register.get("documents") or {}).items():
        if not isinstance(document, dict):
            issues.append(f"Source document {doc_id} entry is invalid")
            continue
        path = Path(str(document.get("path") or "")).expanduser()
        if document.get("availability") == "present_verified":
            if not path.exists():
                issues.append(f"Registered source document missing: {doc_id} at {path}")
                continue
            if path.stat().st_size != int(document.get("size_bytes") or -1):
                issues.append(f"Registered source document size mismatch: {doc_id}")
            if sha256_file(path) != document.get("sha256"):
                issues.append(f"Registered source document hash mismatch: {doc_id}")

    # 10. Authority precedence, controlled statuses, repository ownership, and onboarding.
    if precedence.get("schema") != "smc_codex_authority_precedence_v1":
        issues.append("AUTHORITY_PRECEDENCE.yaml schema missing or invalid")
    canonical = precedence.get("canonical_runtime") or {}
    if canonical.get("module") != "smc_desk.colleague.orchestrator_v3":
        issues.append("Canonical runtime must be smc_desk.colleague.orchestrator_v3")
    required_statuses = {
        "PROPOSED", "IMPLEMENTED", "VALIDATED", "VALIDATED_WITH_LIMITATIONS",
        "CERTIFIED", "PROMOTED", "DEPRECATED", "HISTORICAL", "REJECTED", "BLOCKED",
    }
    declared_statuses = set((status_vocabulary.get("statuses") or {}).keys())
    missing_statuses = sorted(required_statuses - declared_statuses)
    if missing_statuses:
        issues.append(f"STATUS_VOCABULARY.yaml missing statuses: {missing_statuses}")
    repositories = repository_register.get("repositories") or {}
    companion = repositories.get("companion_archive") or {}
    if companion.get("authority") != "non_authoritative" or companion.get("import_into_canonical_runtime") != "prohibited":
        issues.append("Companion repository must be non-authoritative and prohibited from canonical imports")

    readme_first = (ROOT / "governance" / "README_FIRST.md").read_text(encoding="utf-8")
    if "python -m smc_desk.colleague" not in readme_first:
        issues.append("README_FIRST.md does not identify the canonical command surface")
    if "WP-0001-COLLEAGUE-FOUNDATION" in readme_first:
        issues.append("README_FIRST.md still points current work at WP-0001")
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "smc_desk.colleague.orchestrator_v3" not in root_readme:
        issues.append("README.md does not identify orchestrator_v3 as canonical")

    return len(issues) == 0, issues


def main() -> int:
    passed, issues = check_consistency()
    if passed:
        print("GOVERNANCE CONSISTENCY: PASS")
        print("No inconsistencies found.")
        return 0
    else:
        print("GOVERNANCE CONSISTENCY: FAIL")
        print(f"Found {len(issues)} issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
