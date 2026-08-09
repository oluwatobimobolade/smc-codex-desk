from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tools.check_governance_consistency import (
    ROOT,
    check_consistency,
    check_source_manifest_contents,
)
from tools.run_validation_registry import append_validation_record, load_registry


def _yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_wp0044_governance_consistency_gate_passes() -> None:
    passed, issues = check_consistency()
    assert passed, issues


def test_wp0044_validation_registry_is_append_only_and_source_bound() -> None:
    registry = load_registry(ROOT / "evidence" / "VALIDATION_REGISTRY.json")
    assert "latest_validation" not in registry
    records = registry["records"]
    ids = [item["record_id"] for item in records]
    assert len(ids) == len(set(ids))
    assert registry["current_gate"]["record_id"] in ids
    assert all(item["source"]["git_head"] and item["source"]["source_state"] for item in records)


def test_source_manifest_verifies_the_files_it_binds(tmp_path: Path) -> None:
    bound = tmp_path / "bound.py"
    bound.write_text("original\n", encoding="utf-8")
    manifest = tmp_path / "SOURCE_MANIFEST.tsv"
    manifest.write_text(
        "state\tsha256\tsize_bytes\tpath\n"
        f"worktree\t{hashlib.sha256(bound.read_bytes()).hexdigest()}\t{bound.stat().st_size}\tbound.py\n",
        encoding="utf-8",
    )

    assert check_source_manifest_contents(manifest, tmp_path) == []

    bound.write_text("drifted\n", encoding="utf-8")
    issues = check_source_manifest_contents(manifest, tmp_path)
    assert any("mismatch" in issue for issue in issues)


def test_source_manifest_rejects_paths_outside_the_repository(tmp_path: Path) -> None:
    manifest = tmp_path / "SOURCE_MANIFEST.tsv"
    manifest.write_text(
        "state\tsha256\tsize_bytes\tpath\n"
        f"worktree\t{'0' * 64}\t0\t../outside.py\n",
        encoding="utf-8",
    )

    assert any("escapes" in issue for issue in check_source_manifest_contents(manifest, tmp_path))


def test_wp0044_registry_append_preserves_history_and_rejects_duplicate() -> None:
    registry = load_registry(ROOT / "evidence" / "VALIDATION_REGISTRY.json")
    original_ids = [item["record_id"] for item in registry["records"]]
    record = {
        "record_id": "TEST-ONLY-RECORD",
        "work_package": "TEST",
        "gate": "TEST-GATE",
        "status": "PASS",
        "source": {"git_head": "abc", "source_state": "test"},
    }
    updated = append_validation_record(registry, record)
    assert [item["record_id"] for item in updated["records"]][:-1] == original_ids
    assert updated["current_gate"]["record_id"] == "TEST-ONLY-RECORD"
    with pytest.raises(ValueError, match="already exists"):
        append_validation_record(updated, record)


def test_wp0044_controlling_pdf_hashes_match_registered_bytes() -> None:
    register = _yaml("governance/SOURCE_DOCUMENT_REGISTER.yaml")
    for document in register["documents"].values():
        path = Path(document["path"])
        assert path.exists()
        assert path.stat().st_size == document["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == document["sha256"]


def test_wp0044_authority_precedence_names_one_canonical_runtime() -> None:
    precedence = _yaml("governance/AUTHORITY_PRECEDENCE.yaml")
    assert precedence["canonical_runtime"]["module"] == "smc_desk.colleague.orchestrator_v3"
    assert precedence["canonical_runtime"]["execution_authority"] == "disabled"
    assert "smc_desk.colleague.orchestrator" in precedence["canonical_runtime"]["comparison_only"]


def test_wp0044_status_vocabulary_prevents_implemented_equals_certified() -> None:
    vocabulary = _yaml("governance/STATUS_VOCABULARY.yaml")
    assert vocabulary["statuses"]["IMPLEMENTED"]["meaning"] != vocabulary["statuses"]["CERTIFIED"]["meaning"]
    assert "implemented_does_not_mean_validated" in vocabulary["prohibited_shortcuts"]
    assert "validated_does_not_mean_certified" in vocabulary["prohibited_shortcuts"]


def test_wp0044_companion_repository_is_non_authoritative() -> None:
    register = _yaml("governance/REPOSITORY_REGISTER.yaml")
    companion = register["repositories"]["companion_archive"]
    assert companion["authority"] == "non_authoritative"
    assert companion["import_into_canonical_runtime"] == "prohibited"
    assert companion["validation_registry_authority"] == "ignored"


def test_wp0044_onboarding_points_to_current_runtime_and_bridge() -> None:
    text = (ROOT / "governance" / "README_FIRST.md").read_text(encoding="utf-8")
    assert "python -m smc_desk.colleague" in text
    assert "WP-0001-COLLEAGUE-FOUNDATION" not in text
    assert "BR-001" in text and "BR-006" in text


def test_wp0044_wp0043_is_passed_with_explicit_limitations() -> None:
    report = (ROOT / "governance/WORK_PACKAGES/WP-0043-CANONICAL-RUNTIME-AND-AUTHORITY-CONSOLIDATION/final_report.md").read_text(encoding="utf-8")
    assert "VALIDATED_WITH_LIMITATIONS" in report
    assert "GATE-CANONICAL-RUNTIME-001" in report
    assert "full CLI" in report


def test_br001_supersedes_wp0044_mtf_transition_with_pure_data_modules() -> None:
    text = (ROOT / "governance" / "DEPRECATION_REGISTER.md").read_text(encoding="utf-8")
    assert "Historical Mixed-Authority Module" in text
    assert "smc_desk.data.timeframe_reconstruction" in text
    assert "smc_desk.data.market_truth_certificate" in text
    assert "no longer permitted in the canonical perception import graph" in text
