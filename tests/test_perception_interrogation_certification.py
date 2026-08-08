from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from smc_desk.evaluation.perception_interrogation import (
    aggregate_perturbation_case_reports,
    aggregate_sweep_breakout_gold_cases,
    calibration_report,
    certification_verdict,
    evaluate_no_evidence_baselines,
    evaluate_perturbation_responses,
    evaluate_runtime_causal_integrity,
    freeze_poi_ranking,
    generate_chart_perturbations,
    load_adjudicated_evaluation_inputs,
    load_external_validation_readiness,
    run_sequential_replay,
)
from smc_desk.evaluation.evidence_signing import sign_evidence_payload
from smc_desk.evaluation.interrogation_cohort import DIMENSION_WEIGHTS


def _candles(count: int = 12) -> list[dict]:
    return [
        {
            "timestamp": f"2026-01-01T{index:02d}:00:00Z",
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100.5 + index,
        }
        for index in range(count)
    ]


def test_poi_freeze_rejects_future_reaction_fields() -> None:
    result = freeze_poi_ranking(
        ranked_pois=[
            {
                "poi_id": "poi-1",
                "first_knowable_candle": "2026-01-01T04:00:00Z",
                "price_low": 100.0,
                "price_high": 101.0,
                "reaction_score": 0.9,
            }
        ],
        visible_candles=_candles(6),
        decision_time="2026-01-01T05:00:00Z",
        doctrine_hash="hash",
    )
    assert result["status"] == "REJECTED_FUTURE_CONTAMINATION"
    assert "reaction_score" not in result["ranked_pois"][0]


def test_valid_poi_freeze_is_hash_sealed() -> None:
    result = freeze_poi_ranking(
        ranked_pois=[{"poi_id": "poi-1", "first_knowable_candle": "2026-01-01T04:00:00Z", "price_low": 100.0, "price_high": 101.0}],
        visible_candles=_candles(6),
        decision_time="2026-01-01T05:00:00Z",
        doctrine_hash="hash",
    )
    assert result["status"] == "FROZEN_VALID"
    assert len(result["freeze_sha256"]) == 64


def test_sequential_replay_never_passes_future_candles_to_analyzer() -> None:
    seen_lengths: list[int] = []

    def analyze(prefix, cutoff):
        seen_lengths.append(len(prefix))
        return {
            "contracts": {
                "event": {
                    "status": "candidate",
                    "contract_status": "COMPLETE",
                    "first_knowable_candle": cutoff,
                }
            }
        }

    result = run_sequential_replay(candles=_candles(), analyze_prefix=analyze, minimum_bars=4)
    assert result["status"] == "PASS"
    assert seen_lengths == list(range(4, 13))
    assert all(row["visible_candle_count"] == count for row, count in zip(result["snapshots"], seen_lengths))


def test_sequential_replay_catches_future_first_knowable_time() -> None:
    def analyze(_prefix, _cutoff):
        return {"contracts": {"event": {"first_knowable_candle": "2030-01-01T00:00:00Z"}}}

    result = run_sequential_replay(candles=_candles(3), analyze_prefix=analyze, minimum_bars=2)
    assert result["status"] == "FAIL_FUTURE_LEAKAGE"
    assert result["violations"]


def test_real_chart_perturbation_images_are_generated(tmp_path: Path) -> None:
    source = tmp_path / "chart.png"
    image = Image.new("RGB", (320, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.line((10, 160, 300, 20), fill="black", width=3)
    image.save(source)
    result = generate_chart_perturbations(source, tmp_path / "variants")
    assert result["variant_count"] == 7
    assert result["semantic_evaluation_status"] == "PENDING_REAL_VISION_RESPONSES"
    assert all(Path(item["path"]).exists() for item in result["variants"].values())


def test_perturbation_response_comparison_detects_semantic_drift() -> None:
    baseline = {"contracts": {"break": {"classification": "bos", "status": "confirmed", "timeframe": "15m", "price_coordinates": {"price": 100.0}, "abstain": False}}}
    changed = {"contracts": {"break": {"classification": "choch", "status": "confirmed", "timeframe": "15m", "price_coordinates": {"price": 100.0}, "abstain": False}}}
    report = evaluate_perturbation_responses({"baseline": baseline, "grayscale": baseline, "crop": changed})
    assert report["status"] == "FAIL_PRESENTATION_SENSITIVITY"
    assert report["consistency_rate"] == 2 / 3


def test_perturbation_cohort_requires_unique_full_case_coverage() -> None:
    reports = [
        {
            "case_id": f"case-{index}",
            "status": "PASS",
            "real_visual_responses": True,
            "variant_count": 15,
            "consistency_rate": 1.0,
        }
        for index in range(30)
    ]
    assert aggregate_perturbation_case_reports(reports)["status"] == "PASS"
    duplicated = [reports[0], *reports[:29]]
    failed = aggregate_perturbation_case_reports(duplicated)
    assert failed["status"] == "FAIL_PRESENTATION_SENSITIVITY"
    assert failed["duplicate_case_ids"] == ["case-0"]


def test_sweep_breakout_gold_requires_point_in_time_case_coverage() -> None:
    reports = [
        {
            "case_id": f"case-{index}",
            "status": "PASS",
            "future_outcomes_used": False,
            "sequential_cutoff_count": 4,
            "classification_accuracy": 1.0,
            "catastrophic_errors": [],
        }
        for index in range(30)
    ]
    assert aggregate_sweep_breakout_gold_cases(reports)["status"] == "PASS"
    reports[0]["future_outcomes_used"] = True
    failed = aggregate_sweep_breakout_gold_cases(reports)
    assert failed["status"] == "FAIL"
    assert failed["rejected_cases"][0]["reason"] == "future_outcomes_used"


def test_no_evidence_baselines_require_abstention() -> None:
    passing = {name: {"abstain": True} for name in ("no_chart", "blank_chart", "random_chart", "unreadable_chart")}
    assert evaluate_no_evidence_baselines(passing)["status"] == "PASS"
    passing["random_chart"] = {"abstain": False}
    assert evaluate_no_evidence_baselines(passing)["status"] == "FAIL_HALLUCINATION_BASELINE"


def test_calibration_refuses_small_sample_and_computes_when_ready() -> None:
    small = calibration_report([{"case_id": "case-1", "confidence": 0.8, "correct": True}], minimum_records=5, minimum_distinct_cases=1)
    assert small["status"] == "INSUFFICIENT_ADJUDICATED_CALIBRATION_DATA"
    assert small["probabilistic_confidence_allowed"] is False
    ready = calibration_report(
        [{"case_id": "case-1", "confidence": value, "correct": value >= 0.5} for value in (0.02, 0.04, 0.96, 0.98, 0.99)],
        minimum_records=5,
        bins=5,
        minimum_distinct_cases=1,
    )
    assert ready["status"] == "CALIBRATED_EVALUATION_COMPLETE"
    assert ready["ece"] is not None
    assert ready["brier_score"] is not None
    assert ready["thresholds_passed"] is True
    failed = calibration_report(
        [{"case_id": "case-1", "confidence": 0.99, "correct": False} for _ in range(5)],
        minimum_records=5,
        minimum_distinct_cases=1,
    )
    assert failed["status"] == "CALIBRATION_THRESHOLDS_FAILED"
    assert failed["probabilistic_confidence_allowed"] is False
    concentrated = calibration_report(
        [{"case_id": "only-case", "confidence": 0.02, "correct": False} for _ in range(50)],
        minimum_records=50,
        minimum_distinct_cases=30,
    )
    assert concentrated["status"] == "INSUFFICIENT_ADJUDICATED_CALIBRATION_DATA"
    assert concentrated["distinct_case_count"] == 1


def test_certification_cannot_round_missing_gold_up_to_100() -> None:
    verdict = certification_verdict(
        catastrophic_gates={"geometry": True, "lookahead": True},
        dimension_scores={"all_dimensions": 100.0},
        adjudicated_case_count=0,
        minimum_adjudicated_cases=30,
        calibration_status="INSUFFICIENT_ADJUDICATED_CALIBRATION_DATA",
        perturbation_status="PENDING_REAL_VISION_RESPONSES",
    )
    assert verdict["certified"] is False
    assert verdict["score"] is None
    assert verdict["status"] == "NOT_CERTIFIED"
    assert "missing_or_invalid_ten_dimension_empirical_scores" in verdict["certification_contract_failures"]


def test_certification_requires_all_ten_empirical_dimensions_and_blind_cohort() -> None:
    dimensions = {name: 100.0 for name in DIMENSION_WEIGHTS}
    verdict = certification_verdict(
        catastrophic_gates={"all": True},
        dimension_scores=dimensions,
        adjudicated_case_count=30,
        minimum_adjudicated_cases=30,
        calibration_status="CALIBRATED_EVALUATION_COMPLETE",
        perturbation_status="PASS",
        blind_cohort_status="CERTIFIED_100",
    )
    assert verdict["status"] == "CERTIFIED_100"
    assert verdict["score"] == 100.0


def test_evaluation_inputs_accept_only_human_adjudicated_linked_calibration(tmp_path: Path) -> None:
    case = {
        "case_id": "gold-1",
        "symbol": "BTCUSDT",
        "decision_time": "2026-01-01T00:00:00Z",
        "chart_images": {timeframe: f"{timeframe}.png" for timeframe in ("1d", "4h", "1h", "15m")},
        "human_smc_labels": {"external_bias": "bearish"},
        "expected_state": "WATCH_ONLY",
        "expected_direction": "bearish",
        "adjudication_status": "adjudicated",
    }
    (tmp_path / "gold.json").write_text(json.dumps(case), encoding="utf-8")
    records = {
        "records": [
            {"case_id": "gold-1", "question_number": 1, "truth_source": "human_adjudicated", "confidence": 0.8, "correct": True},
            {"case_id": "gold-1", "question_number": 2, "truth_source": "engine_weak_labels", "confidence": 0.9, "correct": True},
            {"case_id": "unknown", "question_number": 3, "truth_source": "human_adjudicated", "confidence": 0.7, "correct": False},
            {"case_id": "gold-1", "question_number": 1, "truth_source": "human_adjudicated", "confidence": 0.8, "correct": True},
        ]
    }
    (tmp_path / "calibration_records.json").write_text(json.dumps(records), encoding="utf-8")
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "sweep_breakout_sequential_report.json").write_text(
        json.dumps({"schema": "not_a_gold_case"}), encoding="utf-8"
    )

    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
    trust = tmp_path / "trust_registry.json"
    trust.write_text(json.dumps({
        "schema": "smc_evidence_trust_registry_v1",
        "registry_id": "test",
        "signers": [{
            "signer_id": "C",
            "role": "adjudicator",
            "public_key_file": public.name,
            "public_key_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
            "active": True,
        }],
    }), encoding="utf-8")
    cohort = tmp_path / "cohort_manifest.json"
    cohort.write_text(json.dumps({
        "cohort_id": "COHORT-1",
        "cohort_content_sha256": "cohort-hash",
        "system_code_freeze_sha256": "system-hash",
        "trust_registry_status": "PROVISIONED",
        "trust_registry_sha256": hashlib.sha256(trust.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    sign_evidence_payload(
        payload_path=tmp_path / "gold.json",
        envelope_path=tmp_path / "gold.json.envelope.json",
        private_key_path=private,
        evidence_type="gold_case",
        subject_id="gold-1",
        cohort_content_sha256="cohort-hash",
        system_code_freeze_sha256="system-hash",
        signer_id="C",
        signer_role="adjudicator",
    )
    sign_evidence_payload(
        payload_path=tmp_path / "calibration_records.json",
        envelope_path=tmp_path / "calibration_records.json.envelope.json",
        private_key_path=private,
        evidence_type="calibration_records",
        subject_id="COHORT-1",
        cohort_content_sha256="cohort-hash",
        system_code_freeze_sha256="system-hash",
        signer_id="C",
        signer_role="adjudicator",
    )

    result = load_adjudicated_evaluation_inputs(
        tmp_path,
        trust_registry_path=trust,
        cohort_manifest_path=cohort,
    )

    assert result["adjudicated_case_count"] == 1
    assert result["calibration_record_count"] == 1
    assert result["calibration_records"] == [{
        "record_id": "gold-1:question:1",
        "case_id": "gold-1",
        "question_number": 1,
        "object_contract_id": None,
        "confidence": 0.8,
        "correct": True,
    }]
    assert len(result["rejected_calibration_records"]) == 3
    assert result["rejected_gold_records"] == []
    assert result["weak_labels_accepted"] is False
    assert result["unsigned_evidence_accepted"] is False


def test_runtime_causal_integrity_checks_candle_close_and_contract_time() -> None:
    registry = {
        "contracts": {
            "break-1": {"first_knowable_candle": "2026-01-01T00:15:00Z"},
        }
    }
    passing = evaluate_runtime_causal_integrity(
        object_evidence_contracts=registry,
        ohlcv_windows={"15m": [{"timestamp": "2026-01-01T00:00:00Z"}]},
        decision_time="2026-01-01T00:15:00Z",
    )
    assert passing["status"] == "PASS"
    failing = evaluate_runtime_causal_integrity(
        object_evidence_contracts=registry,
        ohlcv_windows={"15m": [{"timestamp": "2026-01-01T00:15:00Z"}]},
        decision_time="2026-01-01T00:15:00Z",
    )
    assert failing["status"] == "FAIL_FUTURE_LEAKAGE"


def test_external_validation_reports_are_fail_closed_and_unlock_only_with_real_evidence(tmp_path: Path) -> None:
    missing = load_external_validation_readiness(tmp_path, adjudicated_case_ids=[f"gold-{i}" for i in range(30)])
    assert not any(section["accepted"] for key, section in missing.items() if isinstance(section, dict) and "accepted" in section)

    case_ids = [f"gold-{i}" for i in range(30)]
    (tmp_path / "sweep_breakout_sequential_report.json").write_text(
        json.dumps({
            "schema": "smc_sequential_sweep_breakout_gold_report_v1",
            "status": "PASS",
            "future_outcomes_used": False,
            "violations": [],
            "adjudicated_case_ids": case_ids,
            "valid_case_count": 30,
            "duplicate_case_ids": [],
            "rejected_cases": [],
            "case_reports": [
                {
                    "case_id": case_id,
                    "status": "PASS",
                    "future_outcomes_used": False,
                    "sequential_cutoff_count": 4,
                    "classification_accuracy": 1.0,
                    "catastrophic_errors": [],
                }
                for case_id in case_ids
            ],
        }),
        encoding="utf-8",
    )
    (tmp_path / "perturbation_consistency_report.json").write_text(
        json.dumps({
            "schema": "smc_perturbation_cohort_consistency_report_v1",
            "status": "PASS",
            "real_visual_responses": True,
            "valid_case_count": 30,
            "expected_variants_per_case": 15,
            "aggregate_consistency_rate": 1.0,
            "case_ids": case_ids,
            "duplicate_case_ids": [],
            "rejected_cases": [],
        }),
        encoding="utf-8",
    )
    (tmp_path / "no_evidence_baseline_report.json").write_text(
        json.dumps({
            "schema": "smc_no_evidence_baseline_report_v1",
            "status": "PASS",
            "real_visual_responses": True,
            "baseline_count": 4,
            "baseline_names": ["blank_chart", "no_chart", "random_chart", "unreadable_chart"],
            "missing_baselines": [],
            "failed_abstentions": [],
        }),
        encoding="utf-8",
    )
    (tmp_path / "blind_cohort_score_report.json").write_text(
        json.dumps({
            "schema": "smc_blind_interrogation_cohort_score_v1",
            "status": "CERTIFIED_100",
            "valid_case_count": 30,
            "duplicate_case_ids": [],
            "weighted_score": 100.0,
            "dimension_scores": {name: 100.0 for name in DIMENSION_WEIGHTS},
            "failed_catastrophic_gates": [],
        }),
        encoding="utf-8",
    )
    unsigned = load_external_validation_readiness(tmp_path, adjudicated_case_ids=case_ids)
    assert unsigned["sweep_breakout_sequential"]["accepted"] is False
    assert unsigned["perturbation_consistency"]["accepted"] is False
    assert unsigned["no_evidence_abstention"]["accepted"] is False

    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
    trust = tmp_path / "trust_registry.json"
    trust.write_text(json.dumps({
        "schema": "smc_evidence_trust_registry_v1",
        "registry_id": "test",
        "signers": [{
            "signer_id": "C",
            "role": "adjudicator",
            "public_key_file": public.name,
            "public_key_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
            "active": True,
        }],
    }), encoding="utf-8")
    cohort = tmp_path / "cohort_manifest.json"
    cohort.write_text(json.dumps({
        "cohort_id": "COHORT-1",
        "cohort_content_sha256": "cohort-hash",
        "system_code_freeze_sha256": "system-hash",
        "trust_registry_status": "PROVISIONED",
        "trust_registry_sha256": hashlib.sha256(trust.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    for filename, evidence_type in (
        ("sweep_breakout_sequential_report.json", "sweep_breakout_sequential"),
        ("perturbation_consistency_report.json", "perturbation_consistency"),
        ("no_evidence_baseline_report.json", "no_evidence_abstention"),
        ("blind_cohort_score_report.json", "blind_cohort_score"),
    ):
        sign_evidence_payload(
            payload_path=tmp_path / filename,
            envelope_path=tmp_path / f"{filename}.envelope.json",
            private_key_path=private,
            evidence_type=evidence_type,
            subject_id="COHORT-1",
            cohort_content_sha256="cohort-hash",
            system_code_freeze_sha256="system-hash",
            signer_id="C",
            signer_role="adjudicator",
        )
    ready = load_external_validation_readiness(
        tmp_path,
        adjudicated_case_ids=case_ids,
        trust_registry_path=trust,
        cohort_manifest_path=cohort,
    )
    assert ready["sweep_breakout_sequential"]["accepted"] is True
    assert ready["perturbation_consistency"]["accepted"] is True
    assert ready["no_evidence_abstention"]["accepted"] is True
    assert ready["blind_cohort_score"]["accepted"] is True
    unpinned_cohort = tmp_path / "unpinned_cohort_manifest.json"
    unpinned_cohort.write_text(json.dumps({
        "cohort_id": "COHORT-1",
        "cohort_content_sha256": "cohort-hash",
        "system_code_freeze_sha256": "system-hash",
        "trust_registry_status": "PROVISIONED",
        "trust_registry_sha256": "attacker-controlled-registry-hash",
    }), encoding="utf-8")
    unpinned = load_external_validation_readiness(
        tmp_path,
        adjudicated_case_ids=case_ids,
        trust_registry_path=trust,
        cohort_manifest_path=unpinned_cohort,
    )
    assert unpinned["authority_context"]["context_ready"] is False
    assert unpinned["blind_cohort_score"]["accepted"] is False
