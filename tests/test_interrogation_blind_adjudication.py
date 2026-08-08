from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from smc_desk.evaluation.interrogation_adjudication import (
    aggregate_blind_case_scores,
    build_system_submission_template,
    prepare_blind_adjudication_packet,
    score_completed_blind_adjudication,
    validate_independent_reviewer_submission,
)
from smc_desk.evaluation.interrogation_cohort import CATASTROPHIC_GATES, DIMENSION_WEIGHTS
from smc_desk.evaluation.evidence_signing import sign_evidence_payload


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _review(case_id: str, reviewer_id: str) -> dict:
    return {
        "schema": "smc_interrogation_independent_review_v1",
        "case_id": case_id,
        "reviewer_slot": reviewer_id,
        "reviewer_id": reviewer_id,
        "independent_review_attested": True,
        "engine_output_seen": False,
        "doctrine_hash": "doctrine",
        "completed_at": "2026-07-13T00:00:00Z",
        "object_evidence_contracts": [],
        "dimension_judgments": {
            name: {"score_0_to_100": 100, "evidence": [], "uncertainty": "none"}
            for name in DIMENSION_WEIGHTS
        },
        "hard_question_answers": [
            {"question_number": index, "answer": "Grounded answer", "evidence_contract_ids": [], "abstain": False}
            for index in range(1, 21)
        ],
        "expected_official_state": "WATCH_ONLY",
        "expected_direction": "mixed",
        "expected_poi": None,
        "expected_invalidation": None,
        "expected_target": None,
        "annotation_plan_v2": {"schema": "professional_smc_annotation_plan_v2", "objects": []},
        "catastrophic_error_observed": {gate: False for gate in CATASTROPHIC_GATES},
        "signature": f"signed-{reviewer_id}",
    }


def _system(case_id: str, case_evidence_hash: str, system_freeze_hash: str) -> dict:
    payload = build_system_submission_template(case_id, case_evidence_hash, system_freeze_hash)
    payload.update({
        "frozen_at": "2026-07-13T00:00:00Z",
        "official_state": "WATCH_ONLY",
        "direction": "mixed",
        "annotation_plan_v2": {"schema": "professional_smc_annotation_plan_v2", "objects": []},
        "signature": "system-signature",
    })
    payload["hard_question_answers"] = [
        {"question_number": index, "answer": "Grounded system answer", "evidence_contract_ids": [], "abstain": False, "raw_confidence_for_calibration": 0.8}
        for index in range(1, 21)
    ]
    return payload


def _authority(root: Path) -> dict:
    signers = []
    private_keys = {}
    for signer_id, role in (("A", "reviewer"), ("B", "reviewer"), ("SYS", "system_operator"), ("C", "adjudicator")):
        private = root / f"{signer_id}_private.pem"
        public = root / f"{signer_id}_public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
        private_keys[signer_id] = private
        signers.append({
            "signer_id": signer_id,
            "role": role,
            "public_key_file": public.name,
            "public_key_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
            "active": True,
        })
    trust = root / "trust_registry.json"
    _write(trust, {"schema": "smc_evidence_trust_registry_v1", "registry_id": "test", "signers": signers})
    cohort = root / "cohort_manifest.json"
    _write(cohort, {
        "cohort_id": "COHORT-1",
        "cohort_content_sha256": "cohort-hash",
        "system_code_freeze_sha256": "system-hash",
        "trust_registry_status": "PROVISIONED",
        "trust_registry_sha256": hashlib.sha256(trust.read_bytes()).hexdigest(),
    })
    return {"trust": trust, "cohort": cohort, "private": private_keys}


def _sign(path: Path, authority: dict, signer_id: str, role: str, evidence_type: str, subject_id: str = "CASE-1") -> None:
    sign_evidence_payload(
        payload_path=path,
        envelope_path=path.with_name(f"{path.name}.envelope.json"),
        private_key_path=authority["private"][signer_id],
        evidence_type=evidence_type,
        subject_id=subject_id,
        cohort_content_sha256="cohort-hash",
        system_code_freeze_sha256="system-hash",
        signer_id=signer_id,
        signer_role=role,
    )


def _case_evidence_hash(candle_hashes: dict) -> str:
    encoded = json.dumps(candle_hashes, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_reviewer_validation_is_fail_closed() -> None:
    valid = _review("CASE-1", "A")
    assert validate_independent_reviewer_submission(valid) == []
    valid["engine_output_seen"] = True
    assert "reviewer_saw_engine_output" in validate_independent_reviewer_submission(valid)


def test_blind_packet_scores_system_only_after_complete_adjudication(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    case_manifest = tmp_path / "case_manifest.json"
    candle_hashes = {"15m": "candle-hash"}
    _write(case_manifest, {"case_id": "CASE-1", "candle_map_sha256": candle_hashes})
    reviewer_a = tmp_path / "reviewer_a.json"
    reviewer_b = tmp_path / "reviewer_b.json"
    system = tmp_path / "system.json"
    _write(reviewer_a, _review("CASE-1", "A"))
    _write(reviewer_b, _review("CASE-1", "B"))
    _write(system, _system("CASE-1", _case_evidence_hash(candle_hashes), "system-hash"))
    _sign(reviewer_a, authority, "A", "reviewer", "independent_review")
    _sign(reviewer_b, authority, "B", "reviewer", "independent_review")
    _sign(system, authority, "SYS", "system_operator", "system_submission")
    packet = prepare_blind_adjudication_packet(
        case_manifest_path=case_manifest,
        reviewer_submission_paths=[reviewer_a, reviewer_b],
        system_submission_path=system,
        output_dir=tmp_path / "packet",
        trust_registry_path=authority["trust"],
        cohort_manifest_path=authority["cohort"],
    )
    pending = score_completed_blind_adjudication(tmp_path / "packet" / "packet_manifest.json")
    assert pending["status"] == "INSUFFICIENT_ADJUDICATION"
    anonymous = json.loads(Path(packet["anonymous_submissions_path"]).read_text(encoding="utf-8"))
    assert len({tuple(sorted(item["payload"].keys())) for item in anonymous["submissions"]}) == 1
    assert all("raw_confidence_for_calibration" not in json.dumps(item["payload"]) for item in anonymous["submissions"])
    identity = json.loads(Path(packet["private_identity_map_path"]).read_text(encoding="utf-8"))
    system_id = next(item["submission_id"] for item in identity["identities"] if item["role"] == "system")
    adjudication_path = Path(packet["adjudication_path"])
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    for assessment in adjudication["submission_assessments"].values():
        assessment["dimension_scores"] = {name: 80 for name in DIMENSION_WEIGHTS}
        assessment["catastrophic_errors"] = {gate: False for gate in CATASTROPHIC_GATES}
        assessment["hard_question_correctness"] = {str(index): True for index in range(1, 21)}
    adjudication["submission_assessments"][system_id]["dimension_scores"] = {name: 100 for name in DIMENSION_WEIGHTS}
    adjudication.update({
        "adjudicator_id": "C",
        "completed_at": "2026-07-13T01:00:00Z",
        "signature": "signed-C",
        "adjudication_status": "adjudicated",
    })
    _write(adjudication_path, adjudication)
    _sign(adjudication_path, authority, "C", "adjudicator", "blind_adjudication")
    score = score_completed_blind_adjudication(tmp_path / "packet" / "packet_manifest.json")
    assert score["status"] == "PASS_100"
    assert score["weighted_score"] == 100.0
    assert len(score["calibration_records"]) == 20
    case_scores = [{**score, "case_id": f"CASE-{index:02d}"} for index in range(30)]
    cohort = aggregate_blind_case_scores(case_scores, minimum_cases=30)
    assert cohort["status"] == "CERTIFIED_100"
    duplicate = aggregate_blind_case_scores([score] * 30, minimum_cases=30)
    assert duplicate["status"] == "INSUFFICIENT_ADJUDICATION"
    assert duplicate["duplicate_case_ids"] == ["CASE-1"]


def test_source_tampering_blocks_adjudication_score(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    case_manifest = tmp_path / "case_manifest.json"
    reviewer_a = tmp_path / "reviewer_a.json"
    reviewer_b = tmp_path / "reviewer_b.json"
    system = tmp_path / "system.json"
    candle_hashes = {"15m": "candle-hash"}
    _write(case_manifest, {"case_id": "CASE-1", "candle_map_sha256": candle_hashes})
    _write(reviewer_a, _review("CASE-1", "A"))
    _write(reviewer_b, _review("CASE-1", "B"))
    _write(system, _system("CASE-1", _case_evidence_hash(candle_hashes), "system-hash"))
    _sign(reviewer_a, authority, "A", "reviewer", "independent_review")
    _sign(reviewer_b, authority, "B", "reviewer", "independent_review")
    _sign(system, authority, "SYS", "system_operator", "system_submission")
    packet = prepare_blind_adjudication_packet(
        case_manifest_path=case_manifest,
        reviewer_submission_paths=[reviewer_a, reviewer_b],
        system_submission_path=system,
        output_dir=tmp_path / "packet",
        trust_registry_path=authority["trust"],
        cohort_manifest_path=authority["cohort"],
    )
    Path(packet["anonymous_submissions_path"]).write_text("{}", encoding="utf-8")
    score = score_completed_blind_adjudication(tmp_path / "packet" / "packet_manifest.json")
    assert score["status"] == "INSUFFICIENT_ADJUDICATION"
    assert any("source_hash_mismatch" in issue for issue in score["issues"])
