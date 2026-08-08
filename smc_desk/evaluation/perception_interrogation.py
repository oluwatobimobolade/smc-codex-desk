"""Executable SMC perception interrogation and certification gates."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
from pydantic import ValidationError

from smc_desk.eval.gold_set_loader import GoldChartCase
from smc_desk.evaluation.evidence_signing import verify_evidence_envelope
from smc_desk.evaluation.interrogation_cohort import DIMENSION_WEIGHTS


FUTURE_REACTION_FIELDS = {
    "future_reaction",
    "reaction_score",
    "outcome",
    "realized_rr",
    "mfe",
    "mae",
    "target_hit",
    "stop_hit",
    "profitable",
}

TIMEFRAME_DURATION = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}


def freeze_poi_ranking(
    *,
    ranked_pois: Sequence[Mapping[str, Any]],
    visible_candles: Sequence[Mapping[str, Any]],
    decision_time: str,
    doctrine_hash: str,
) -> dict[str, Any]:
    cutoff = _timestamp(decision_time)
    violations: list[str] = []
    visible_times = [_timestamp(_candle_time(candle)) for candle in visible_candles]
    if visible_times and max(visible_times) > cutoff:
        violations.append("visible_candles_extend_beyond_decision_time")
    frozen_pois: list[dict[str, Any]] = []
    for rank, raw in enumerate(ranked_pois, start=1):
        item = dict(raw)
        forbidden = sorted(FUTURE_REACTION_FIELDS.intersection(item))
        if forbidden:
            violations.append(f"poi_rank_{rank}_contains_future_fields:{','.join(forbidden)}")
        known_at = item.get("first_knowable_candle") or item.get("confirmed_at") or item.get("candidate_at")
        if known_at is None:
            violations.append(f"poi_rank_{rank}_missing_first_knowable_candle")
        elif _timestamp(known_at) > cutoff:
            violations.append(f"poi_rank_{rank}_not_knowable_at_cutoff")
        frozen_pois.append({key: value for key, value in item.items() if key not in FUTURE_REACTION_FIELDS})
    payload = {
        "schema": "poi_ranking_freeze_v1",
        "decision_time": _iso(cutoff),
        "doctrine_hash": doctrine_hash,
        "ranked_pois": frozen_pois,
        "violations": violations,
        "status": "FROZEN_VALID" if not violations else "REJECTED_FUTURE_CONTAMINATION",
        "future_outcomes_revealed": False,
    }
    payload["freeze_sha256"] = _hash(payload)
    return payload


def run_sequential_replay(
    *,
    candles: Sequence[Mapping[str, Any]],
    analyze_prefix: Callable[[Sequence[Mapping[str, Any]], str], Mapping[str, Any]],
    minimum_bars: int = 10,
) -> dict[str, Any]:
    ordered = sorted((dict(candle) for candle in candles), key=lambda item: _timestamp(_candle_time(item)))
    snapshots: list[dict[str, Any]] = []
    violations: list[str] = []
    for end in range(max(1, minimum_bars), len(ordered) + 1):
        prefix = ordered[:end]
        cutoff = _iso(_timestamp(_candle_time(prefix[-1])))
        output = dict(analyze_prefix(prefix, cutoff))
        for object_id, contract in _contracts(output).items():
            first_knowable = contract.get("first_knowable_candle")
            if first_knowable is not None and _timestamp(first_knowable) > _timestamp(cutoff):
                violations.append(f"{cutoff}:{object_id}:first_knowable_after_cutoff")
        snapshots.append(
            {
                "cutoff": cutoff,
                "visible_candle_count": len(prefix),
                "latest_visible_candle": _candle_time(prefix[-1]),
                "output_sha256": _hash(output),
                "object_states": {
                    object_id: {
                        "status": contract.get("status"),
                        "contract_status": contract.get("contract_status"),
                        "first_knowable_candle": contract.get("first_knowable_candle"),
                    }
                    for object_id, contract in _contracts(output).items()
                },
            }
        )
    return {
        "schema": "smc_sequential_replay_audit_v1",
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "violations": violations,
        "status": "PASS" if not violations else "FAIL_FUTURE_LEAKAGE",
    }


def evaluate_runtime_causal_integrity(
    *,
    object_evidence_contracts: Mapping[str, Any],
    ohlcv_windows: Mapping[str, Sequence[Mapping[str, Any]]],
    decision_time: str,
) -> dict[str, Any]:
    cutoff = _timestamp(decision_time)
    violations: list[str] = []
    checked_candles = 0
    checked_contracts = 0
    for timeframe, candles in ohlcv_windows.items():
        duration = TIMEFRAME_DURATION.get(str(timeframe))
        if duration is None:
            violations.append(f"unknown_timeframe_duration:{timeframe}")
            continue
        for index, candle in enumerate(candles):
            checked_candles += 1
            open_time = _timestamp(candle.get("timestamp") or candle.get("open_time"))
            if open_time + duration > cutoff:
                violations.append(f"future_or_forming_candle:{timeframe}:{index}:{open_time.isoformat()}")
    for contract_id, contract in _contracts(object_evidence_contracts).items():
        checked_contracts += 1
        first_knowable = contract.get("first_knowable_candle")
        if first_knowable is None:
            violations.append(f"missing_first_knowable_candle:{contract_id}")
        elif _timestamp(first_knowable) > cutoff:
            violations.append(f"future_contract:{contract_id}:{first_knowable}")
    return {
        "schema": "smc_runtime_causal_integrity_v1",
        "decision_time": _iso(cutoff),
        "checked_candle_count": checked_candles,
        "checked_contract_count": checked_contracts,
        "violations": violations,
        "status": "PASS" if not violations else "FAIL_FUTURE_LEAKAGE",
    }


def generate_chart_perturbations(image_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source_path = Path(image_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as raw:
        source = raw.convert("RGB")
    width, height = source.size
    crop_box = (
        max(0, int(width * 0.08)),
        max(0, int(height * 0.08)),
        min(width, int(width * 0.92)),
        min(height, int(height * 0.92)),
    )
    variants = {
        "baseline": source,
        "grayscale": ImageOps.grayscale(source).convert("RGB"),
        "inverted_theme": ImageOps.invert(source),
        "reduced_contrast": ImageEnhance.Contrast(source).enhance(0.65),
        "resized_75pct": source.resize((max(1, int(width * 0.75)), max(1, int(height * 0.75)))),
        "center_crop_84pct": source.crop(crop_box),
        "padded_canvas": ImageOps.expand(source, border=(32, 24, 32, 24), fill=(245, 245, 245)),
    }
    manifest: dict[str, Any] = {}
    for name, image in variants.items():
        path = target / f"{name}.png"
        image.save(path, format="PNG")
        manifest[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width": image.width,
            "height": image.height,
            "transformation": name,
        }
    return {
        "schema": "smc_chart_perturbation_manifest_v1",
        "source_path": str(source_path),
        "variants": manifest,
        "variant_count": len(manifest),
        "semantic_evaluation_status": "PENDING_REAL_VISION_RESPONSES",
    }


def evaluate_perturbation_responses(
    responses: Mapping[str, Mapping[str, Any]], *, real_visual_responses: bool = False,
) -> dict[str, Any]:
    if "baseline" not in responses:
        raise ValueError("baseline response is required")
    baseline = _semantic_signature(responses["baseline"])
    comparisons: dict[str, Any] = {}
    consistent = 0
    for name, response in responses.items():
        signature = _semantic_signature(response)
        matches = signature == baseline
        comparisons[name] = {"matches_baseline": matches, "semantic_signature": signature}
        consistent += int(matches)
    total = len(comparisons)
    return {
        "schema": "smc_perturbation_consistency_report_v1",
        "variant_count": total,
        "consistent_variant_count": consistent,
        "consistency_rate": consistent / total if total else None,
        "variant_names": sorted(comparisons),
        "real_visual_responses": real_visual_responses,
        "comparisons": comparisons,
        "status": "PASS" if consistent == total else "FAIL_PRESENTATION_SENSITIVITY",
    }


def evaluate_no_evidence_baselines(
    responses: Mapping[str, Mapping[str, Any]], *, real_visual_responses: bool = False,
) -> dict[str, Any]:
    required = {"no_chart", "blank_chart", "random_chart", "unreadable_chart"}
    missing = sorted(required.difference(responses))
    failures = sorted(
        name
        for name, response in responses.items()
        if name in required and not bool(response.get("abstain"))
    )
    return {
        "schema": "smc_no_evidence_baseline_report_v1",
        "missing_baselines": missing,
        "failed_abstentions": failures,
        "baseline_count": len(required.intersection(responses)),
        "baseline_names": sorted(required.intersection(responses)),
        "real_visual_responses": real_visual_responses,
        "status": "PASS" if not missing and not failures else "FAIL_HALLUCINATION_BASELINE",
    }


def aggregate_perturbation_case_reports(
    case_reports: Sequence[Mapping[str, Any]],
    *,
    minimum_cases: int = 30,
    expected_variants_per_case: int = 15,
    minimum_consistency: float = 0.95,
) -> dict[str, Any]:
    seen: set[str] = set()
    duplicates: list[str] = []
    accepted: list[Mapping[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for index, report in enumerate(case_reports):
        case_id = str(report.get("case_id") or "")
        if not case_id:
            rejected.append({"case_id": f"index-{index}", "reason": "missing_case_id"})
            continue
        if case_id in seen:
            duplicates.append(case_id)
            continue
        seen.add(case_id)
        if report.get("real_visual_responses") is not True:
            rejected.append({"case_id": case_id, "reason": "not_real_visual_responses"})
            continue
        if int(report.get("variant_count") or 0) < expected_variants_per_case:
            rejected.append({"case_id": case_id, "reason": "insufficient_variant_count"})
            continue
        if float(report.get("consistency_rate") or 0.0) < minimum_consistency:
            rejected.append({"case_id": case_id, "reason": "consistency_below_threshold"})
            continue
        if report.get("status") != "PASS":
            rejected.append({"case_id": case_id, "reason": "case_report_not_pass"})
            continue
        accepted.append(report)
    complete = len(accepted) >= minimum_cases and not duplicates and not rejected
    aggregate_consistency = (
        sum(float(report["consistency_rate"]) for report in accepted) / len(accepted)
        if accepted else None
    )
    return {
        "schema": "smc_perturbation_cohort_consistency_report_v1",
        "status": "PASS" if complete else "FAIL_PRESENTATION_SENSITIVITY",
        "real_visual_responses": bool(accepted) and all(report.get("real_visual_responses") is True for report in accepted),
        "valid_case_count": len(accepted),
        "minimum_case_count": minimum_cases,
        "expected_variants_per_case": expected_variants_per_case,
        "aggregate_consistency_rate": aggregate_consistency,
        "minimum_consistency": minimum_consistency,
        "case_ids": sorted(str(report["case_id"]) for report in accepted),
        "duplicate_case_ids": sorted(set(duplicates)),
        "rejected_cases": rejected,
        "case_reports": list(case_reports),
    }


def aggregate_sweep_breakout_gold_cases(
    case_reports: Sequence[Mapping[str, Any]], *, minimum_cases: int = 30,
) -> dict[str, Any]:
    seen: set[str] = set()
    duplicates: list[str] = []
    accepted: list[Mapping[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for index, report in enumerate(case_reports):
        case_id = str(report.get("case_id") or "")
        if not case_id:
            rejected.append({"case_id": f"index-{index}", "reason": "missing_case_id"})
            continue
        if case_id in seen:
            duplicates.append(case_id)
            continue
        seen.add(case_id)
        if report.get("future_outcomes_used") is not False:
            rejected.append({"case_id": case_id, "reason": "future_outcomes_used"})
            continue
        if int(report.get("sequential_cutoff_count") or 0) < 4:
            rejected.append({"case_id": case_id, "reason": "insufficient_sequential_cutoffs"})
            continue
        if float(report.get("classification_accuracy") or 0.0) != 1.0:
            rejected.append({"case_id": case_id, "reason": "classification_error"})
            continue
        if report.get("catastrophic_errors"):
            rejected.append({"case_id": case_id, "reason": "catastrophic_lifecycle_error"})
            continue
        if report.get("status") != "PASS":
            rejected.append({"case_id": case_id, "reason": "case_report_not_pass"})
            continue
        accepted.append(report)
    complete = len(accepted) >= minimum_cases and not duplicates and not rejected
    return {
        "schema": "smc_sequential_sweep_breakout_gold_report_v1",
        "status": "PASS" if complete else "FAIL",
        "future_outcomes_used": False,
        "valid_case_count": len(accepted),
        "minimum_case_count": minimum_cases,
        "adjudicated_case_ids": sorted(str(report["case_id"]) for report in accepted),
        "duplicate_case_ids": sorted(set(duplicates)),
        "rejected_cases": rejected,
        "violations": [] if complete else ["sequential_sweep_breakout_cohort_incomplete_or_incorrect"],
        "case_reports": list(case_reports),
    }


def calibration_report(
    records: Sequence[Mapping[str, Any]],
    *,
    minimum_records: int = 50,
    bins: int = 10,
    maximum_ece: float = 0.10,
    maximum_brier_score: float = 0.25,
    minimum_distinct_cases: int = 30,
) -> dict[str, Any]:
    valid = [
        (float(item["confidence"]), int(bool(item["correct"])))
        for item in records
        if item.get("confidence") is not None and item.get("correct") is not None
    ]
    distinct_cases = {str(item.get("case_id")) for item in records if item.get("case_id")}
    if len(valid) < minimum_records or len(distinct_cases) < minimum_distinct_cases:
        return {
            "schema": "smc_confidence_calibration_report_v1",
            "status": "INSUFFICIENT_ADJUDICATED_CALIBRATION_DATA",
            "record_count": len(valid),
            "minimum_records": minimum_records,
            "distinct_case_count": len(distinct_cases),
            "minimum_distinct_cases": minimum_distinct_cases,
            "probabilistic_confidence_allowed": False,
            "ece": None,
            "brier_score": None,
        }
    brier = sum((confidence - correct) ** 2 for confidence, correct in valid) / len(valid)
    ece = 0.0
    bin_rows: list[dict[str, Any]] = []
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            (confidence, correct)
            for confidence, correct in valid
            if (lower <= confidence <= upper if index == bins - 1 else lower <= confidence < upper)
        ]
        if not bucket:
            continue
        mean_confidence = sum(value[0] for value in bucket) / len(bucket)
        accuracy = sum(value[1] for value in bucket) / len(bucket)
        ece += len(bucket) / len(valid) * abs(mean_confidence - accuracy)
        bin_rows.append({"lower": lower, "upper": upper, "count": len(bucket), "mean_confidence": mean_confidence, "accuracy": accuracy})
    thresholds_passed = ece <= maximum_ece and brier <= maximum_brier_score
    return {
        "schema": "smc_confidence_calibration_report_v1",
        "status": "CALIBRATED_EVALUATION_COMPLETE" if thresholds_passed else "CALIBRATION_THRESHOLDS_FAILED",
        "record_count": len(valid),
        "minimum_records": minimum_records,
        "distinct_case_count": len(distinct_cases),
        "minimum_distinct_cases": minimum_distinct_cases,
        "probabilistic_confidence_allowed": thresholds_passed,
        "ece": ece,
        "brier_score": brier,
        "maximum_ece": maximum_ece,
        "maximum_brier_score": maximum_brier_score,
        "thresholds_passed": thresholds_passed,
        "bins": bin_rows,
    }


def load_adjudicated_evaluation_inputs(
    cases_root: str | Path,
    *,
    trust_registry_path: str | Path | None = None,
    cohort_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load only independently adjudicated cases and their linked calibration rows.

    Engine outputs and weak labels cannot satisfy this loader. Calibration rows
    must name a valid adjudicated case and explicitly declare their truth source.
    """
    root = Path(cases_root).expanduser().resolve()
    gold_cases: dict[str, GoldChartCase] = {}
    duplicate_case_ids: list[str] = []
    rejected_gold_records: list[dict[str, str]] = []
    calibration_files: list[Path] = []
    context = _external_validation_context(
        root / "validation" if (root / "validation").is_dir() else root,
        trust_registry_path,
        cohort_manifest_path,
    )
    accepted_signature_verifications: list[dict[str, Any]] = []

    files = [root] if root.is_file() else sorted(root.rglob("*.json")) if root.exists() else []
    for path in files:
        if root.is_dir() and "validation" in path.relative_to(root).parts:
            continue
        if path.name.endswith(".envelope.json") or path.name in {
            "trust_registry.json",
            "validation_context.json",
            "cohort_manifest.json",
        }:
            continue
        if "calibration" in path.name.lower():
            calibration_files.append(path)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rejected_gold_records.append({"path": str(path), "reason": f"json_error:{exc}"})
            continue
        records = payload if isinstance(payload, list) else [payload]
        if isinstance(payload, list):
            rejected_gold_records.append({"path": str(path), "reason": "signed_gold_requires_one_case_per_file"})
            continue
        for index, record in enumerate(records):
            reference = f"{path}#{index}" if isinstance(payload, list) else str(path)
            try:
                case = GoldChartCase.model_validate(record)
            except ValidationError as exc:
                rejected_gold_records.append({"path": reference, "reason": f"schema_error:{exc.errors()[0]['type']}"})
                continue
            signature = _verify_payload_signature(
                path,
                context=context,
                evidence_type="gold_case",
                subject_id=case.case_id,
                allowed_roles={"adjudicator"},
            )
            if signature.get("status") != "PASS":
                rejected_gold_records.append({
                    "path": reference,
                    "reason": f"signature_rejected:{','.join(signature.get('issues') or [])}",
                })
                continue
            if case.case_id in gold_cases:
                duplicate_case_ids.append(case.case_id)
                continue
            gold_cases[case.case_id] = case
            accepted_signature_verifications.append(signature)

    calibration_records: list[dict[str, Any]] = []
    rejected_calibration_records: list[dict[str, str]] = []
    seen_calibration_record_ids: set[str] = set()
    for path in calibration_files:
        signature = _verify_payload_signature(
            path,
            context=context,
            evidence_type="calibration_records",
            subject_id=str(context.get("cohort_id") or ""),
            allowed_roles={"adjudicator", "calibration_lead"},
        )
        if signature.get("status") != "PASS":
            rejected_calibration_records.append({
                "path": str(path),
                "reason": f"signature_rejected:{','.join(signature.get('issues') or [])}",
            })
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rejected_calibration_records.append({"path": str(path), "reason": f"json_error:{exc}"})
            continue
        raw_records = payload.get("records", []) if isinstance(payload, Mapping) else payload
        if not isinstance(raw_records, list):
            rejected_calibration_records.append({"path": str(path), "reason": "records_must_be_a_list"})
            continue
        for index, record in enumerate(raw_records):
            reference = f"{path}#{index}"
            if not isinstance(record, Mapping):
                rejected_calibration_records.append({"path": reference, "reason": "record_must_be_an_object"})
                continue
            case_id = str(record.get("case_id") or "")
            if record.get("truth_source") != "human_adjudicated":
                rejected_calibration_records.append({"path": reference, "reason": "truth_source_not_human_adjudicated"})
                continue
            if case_id not in gold_cases:
                rejected_calibration_records.append({"path": reference, "reason": "unknown_adjudicated_case_id"})
                continue
            question_number = record.get("question_number")
            object_contract_id = record.get("object_contract_id")
            calibration_unit = (
                f"question:{question_number}" if question_number is not None
                else f"object:{object_contract_id}" if object_contract_id
                else None
            )
            if calibration_unit is None:
                rejected_calibration_records.append({"path": reference, "reason": "missing_calibration_unit_identity"})
                continue
            record_id = f"{case_id}:{calibration_unit}"
            if record_id in seen_calibration_record_ids:
                rejected_calibration_records.append({"path": reference, "reason": "duplicate_calibration_record_identity"})
                continue
            try:
                confidence = float(record["confidence"])
                correct_raw = record["correct"]
            except (KeyError, TypeError, ValueError):
                rejected_calibration_records.append({"path": reference, "reason": "missing_or_invalid_confidence_or_correct"})
                continue
            if not 0.0 <= confidence <= 1.0 or correct_raw not in {True, False, 0, 1}:
                rejected_calibration_records.append({"path": reference, "reason": "confidence_or_correct_out_of_contract"})
                continue
            seen_calibration_record_ids.add(record_id)
            calibration_records.append({
                "record_id": record_id,
                "case_id": case_id,
                "question_number": question_number,
                "object_contract_id": object_contract_id,
                "confidence": confidence,
                "correct": bool(correct_raw),
            })
        accepted_signature_verifications.append(signature)

    return {
        "schema": "smc_adjudicated_evaluation_inputs_v1",
        "cases_root": str(root),
        "adjudicated_case_count": len(gold_cases),
        "adjudicated_case_ids": sorted(gold_cases),
        "duplicate_case_ids": sorted(set(duplicate_case_ids)),
        "calibration_record_count": len(calibration_records),
        "calibration_records": calibration_records,
        "rejected_gold_records": rejected_gold_records,
        "rejected_calibration_records": rejected_calibration_records,
        "weak_labels_accepted": False,
        "unsigned_evidence_accepted": False,
        "authority_context_ready": bool(context.get("context_ready")),
        "accepted_signature_verifications": accepted_signature_verifications,
    }


def load_external_validation_readiness(
    validation_root: str | Path,
    *,
    adjudicated_case_ids: Sequence[str],
    minimum_adjudicated_cases: int = 30,
    trust_registry_path: str | Path | None = None,
    cohort_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate signed human/vision reports without trusting self-declared flags."""
    root = Path(validation_root).expanduser().resolve()
    known_case_ids = set(map(str, adjudicated_case_ids))
    context = _external_validation_context(root, trust_registry_path, cohort_manifest_path)
    sweep, sweep_verification = _load_signed_external_report(
        root / "sweep_breakout_sequential_report.json",
        context=context,
        evidence_type="sweep_breakout_sequential",
        allowed_roles={"adjudicator"},
    )
    perturbation, perturbation_verification = _load_signed_external_report(
        root / "perturbation_consistency_report.json",
        context=context,
        evidence_type="perturbation_consistency",
        allowed_roles={"visual_auditor", "adjudicator"},
    )
    no_evidence, no_evidence_verification = _load_signed_external_report(
        root / "no_evidence_baseline_report.json",
        context=context,
        evidence_type="no_evidence_abstention",
        allowed_roles={"visual_auditor", "adjudicator"},
    )
    blind_score, blind_score_verification = _load_signed_external_report(
        root / "blind_cohort_score_report.json",
        context=context,
        evidence_type="blind_cohort_score",
        allowed_roles={"adjudicator", "calibration_authority"},
    )

    sweep_ids = set(map(str, (sweep or {}).get("adjudicated_case_ids") or []))
    sweep_accepted = bool(
        sweep
        and sweep_verification.get("status") == "PASS"
        and sweep.get("schema") == "smc_sequential_sweep_breakout_gold_report_v1"
        and sweep.get("status") == "PASS"
        and sweep.get("future_outcomes_used") is False
        and not sweep.get("violations")
        and int(sweep.get("valid_case_count") or 0) >= minimum_adjudicated_cases
        and not sweep.get("duplicate_case_ids")
        and not sweep.get("rejected_cases")
        and len(sweep.get("case_reports") or []) >= minimum_adjudicated_cases
        and len(sweep_ids) >= minimum_adjudicated_cases
        and sweep_ids.issubset(known_case_ids)
    )
    perturbation_case_ids = set(map(str, (perturbation or {}).get("case_ids") or []))
    perturbation_accepted = bool(
        perturbation
        and perturbation_verification.get("status") == "PASS"
        and perturbation.get("schema") == "smc_perturbation_cohort_consistency_report_v1"
        and perturbation.get("status") == "PASS"
        and perturbation.get("real_visual_responses") is True
        and int(perturbation.get("valid_case_count") or 0) >= minimum_adjudicated_cases
        and int(perturbation.get("expected_variants_per_case") or 0) >= 15
        and float(perturbation.get("aggregate_consistency_rate") or 0.0) >= 0.95
        and not perturbation.get("duplicate_case_ids")
        and not perturbation.get("rejected_cases")
        and len(perturbation_case_ids) >= minimum_adjudicated_cases
        and perturbation_case_ids.issubset(known_case_ids)
    )
    no_evidence_accepted = bool(
        no_evidence
        and no_evidence_verification.get("status") == "PASS"
        and no_evidence.get("schema") == "smc_no_evidence_baseline_report_v1"
        and no_evidence.get("status") == "PASS"
        and no_evidence.get("real_visual_responses") is True
        and int(no_evidence.get("baseline_count") or 0) == 4
        and set(no_evidence.get("baseline_names") or []) == {"blank_chart", "no_chart", "random_chart", "unreadable_chart"}
        and not no_evidence.get("missing_baselines")
        and not no_evidence.get("failed_abstentions")
    )
    blind_dimensions = (blind_score or {}).get("dimension_scores") or {}
    blind_score_accepted = bool(
        blind_score
        and blind_score_verification.get("status") == "PASS"
        and blind_score.get("schema") == "smc_blind_interrogation_cohort_score_v1"
        and blind_score.get("status") == "CERTIFIED_100"
        and int(blind_score.get("valid_case_count") or 0) >= minimum_adjudicated_cases
        and not blind_score.get("duplicate_case_ids")
        and not blind_score.get("failed_catastrophic_gates")
        and float(blind_score.get("weighted_score") or 0.0) == 100.0
        and set(blind_dimensions) == set(DIMENSION_WEIGHTS)
        and all(float(blind_dimensions[name]) == 100.0 for name in DIMENSION_WEIGHTS)
    )
    return {
        "schema": "smc_external_validation_readiness_v1",
        "validation_root": str(root),
        "authority_context": {key: value for key, value in context.items() if key != "trust_registry_path"},
        "sweep_breakout_sequential": {
            "accepted": sweep_accepted,
            "status": (sweep or {}).get("status", "MISSING"),
            "signature_verification": sweep_verification,
        },
        "perturbation_consistency": {
            "accepted": perturbation_accepted,
            "status": (perturbation or {}).get("status", "MISSING"),
            "signature_verification": perturbation_verification,
        },
        "no_evidence_abstention": {
            "accepted": no_evidence_accepted,
            "status": (no_evidence or {}).get("status", "MISSING"),
            "signature_verification": no_evidence_verification,
        },
        "blind_cohort_score": {
            "accepted": blind_score_accepted,
            "status": (blind_score or {}).get("status", "MISSING"),
            "weighted_score": (blind_score or {}).get("weighted_score") if blind_score_verification.get("status") == "PASS" else None,
            "dimension_scores": blind_dimensions if blind_score_verification.get("status") == "PASS" else {},
            "failed_catastrophic_gates": (blind_score or {}).get("failed_catastrophic_gates") if blind_score_verification.get("status") == "PASS" else [],
            "signature_verification": blind_score_verification,
        },
        "fabricated_evidence_accepted": False,
        "unsigned_evidence_accepted": False,
    }


def certification_verdict(
    *,
    catastrophic_gates: Mapping[str, bool],
    dimension_scores: Mapping[str, float],
    adjudicated_case_count: int,
    minimum_adjudicated_cases: int,
    calibration_status: str,
    perturbation_status: str,
    blind_cohort_status: str = "MISSING",
    implementation_contract_coverage: float = 100.0,
) -> dict[str, Any]:
    failed_gates = sorted(name for name, passed in catastrophic_gates.items() if not passed)
    dimension_schema_valid = set(dimension_scores) == set(DIMENSION_WEIGHTS) and all(
        0.0 <= float(dimension_scores[name]) <= 100.0 for name in DIMENSION_WEIGHTS
    )
    empirical_score = (
        sum(float(dimension_scores[name]) * weight / 100.0 for name, weight in DIMENSION_WEIGHTS.items())
        if dimension_schema_valid else None
    )
    evidence_ready = adjudicated_case_count >= minimum_adjudicated_cases
    calibration_ready = calibration_status == "CALIBRATED_EVALUATION_COMPLETE"
    perturbation_ready = perturbation_status == "PASS"
    blind_cohort_ready = blind_cohort_status == "CERTIFIED_100"
    certified = bool(
        not failed_gates
        and evidence_ready
        and calibration_ready
        and perturbation_ready
        and blind_cohort_ready
        and empirical_score is not None
        and math.isclose(empirical_score, 100.0)
        and math.isclose(float(implementation_contract_coverage), 100.0)
    )
    contract_failures = []
    if not dimension_schema_valid:
        contract_failures.append("missing_or_invalid_ten_dimension_empirical_scores")
    if not blind_cohort_ready:
        contract_failures.append("blind_cohort_not_certified_100")
    return {
        "schema": "smc_perception_certification_verdict_v1",
        "certified": certified,
        "score": empirical_score if blind_cohort_status in {"CERTIFIED_100", "NOT_CERTIFIED"} else None,
        "implementation_score": float(implementation_contract_coverage),
        "dimension_scores": dict(dimension_scores) if dimension_schema_valid else {},
        "dimension_schema_valid": dimension_schema_valid,
        "blind_cohort_status": blind_cohort_status,
        "certification_contract_failures": contract_failures,
        "failed_catastrophic_gates": failed_gates,
        "adjudicated_case_count": adjudicated_case_count,
        "minimum_adjudicated_cases": minimum_adjudicated_cases,
        "calibration_status": calibration_status,
        "perturbation_status": perturbation_status,
        "status": "CERTIFIED_100" if certified else "NOT_CERTIFIED",
        "reason": None if certified else "100/100 requires a signed unique-case blind cohort score across all ten dimensions, every catastrophic gate, adjudicated gold, calibration, and real perturbation consistency.",
    }


def _semantic_signature(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    contracts = _contracts(response)
    return sorted(
        (
            {
                "object_id": object_id,
                "classification": item.get("classification"),
                "status": item.get("status"),
                "timeframe": item.get("timeframe"),
                "price_coordinates": item.get("price_coordinates"),
                "abstain": item.get("abstain"),
            }
            for object_id, item in contracts.items()
        ),
        key=lambda item: item["object_id"],
    )


def _contracts(payload: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    registry = payload.get("object_evidence_contracts") if isinstance(payload, Mapping) else None
    if isinstance(registry, Mapping) and isinstance(registry.get("contracts"), Mapping):
        return registry["contracts"]
    if isinstance(payload.get("contracts"), Mapping):
        return payload["contracts"]
    return {}


def _candle_time(candle: Mapping[str, Any]) -> Any:
    value = candle.get("close_time") or candle.get("timestamp") or candle.get("open_time")
    if value is None:
        raise ValueError("candle timestamp is required")
    return value


def _timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _iso(value: pd.Timestamp) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json_if_present(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, Mapping) else None


def _external_validation_context(
    root: Path,
    trust_registry_path: str | Path | None,
    cohort_manifest_path: str | Path | None,
) -> dict[str, Any]:
    context = _load_json_if_present(root / "validation_context.json") or {}
    trust_path = Path(trust_registry_path or context.get("trust_registry_path") or root / "trust_registry.json").expanduser().resolve()
    cohort_raw = cohort_manifest_path or context.get("cohort_manifest_path")
    cohort_path = Path(cohort_raw).expanduser().resolve() if cohort_raw else None
    cohort = _load_json_if_present(cohort_path) if cohort_path else None
    return {
        "trust_registry_path": str(trust_path),
        "cohort_manifest_path": str(cohort_path) if cohort_path else None,
        "cohort_id": (cohort or {}).get("cohort_id"),
        "cohort_content_sha256": (cohort or {}).get("cohort_content_sha256"),
        "system_code_freeze_sha256": (cohort or {}).get("system_code_freeze_sha256"),
        "trust_registry_sha256": (cohort or {}).get("trust_registry_sha256"),
        "actual_trust_registry_sha256": _file_hash_if_present(trust_path),
        "context_ready": bool(
            trust_path.is_file()
            and cohort
            and cohort.get("cohort_id")
            and cohort.get("cohort_content_sha256")
            and cohort.get("system_code_freeze_sha256")
            and cohort.get("trust_registry_status") == "PROVISIONED"
            and cohort.get("trust_registry_sha256")
            and _file_hash_if_present(trust_path) == cohort.get("trust_registry_sha256")
        ),
    }


def _load_signed_external_report(
    payload_path: Path,
    *,
    context: Mapping[str, Any],
    evidence_type: str,
    allowed_roles: set[str],
) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
    payload = _load_json_if_present(payload_path)
    envelope_path = payload_path.with_name(f"{payload_path.name}.envelope.json")
    if not context.get("context_ready"):
        return payload, {
            "schema": "smc_signed_evidence_verification_v1",
            "status": "FAIL",
            "issues": ["validation_authority_context_not_ready"],
            "envelope_path": str(envelope_path),
        }
    verification = verify_evidence_envelope(
        envelope_path,
        trust_registry_path=str(context["trust_registry_path"]),
        allowed_roles=allowed_roles,
        expected_evidence_type=evidence_type,
        expected_subject_id=str(context["cohort_id"]),
        expected_cohort_content_sha256=str(context["cohort_content_sha256"]),
        expected_system_code_freeze_sha256=str(context["system_code_freeze_sha256"]),
    )
    return payload, verification


def _verify_payload_signature(
    payload_path: Path,
    *,
    context: Mapping[str, Any],
    evidence_type: str,
    subject_id: str,
    allowed_roles: set[str],
) -> dict[str, Any]:
    envelope_path = payload_path.with_name(f"{payload_path.name}.envelope.json")
    if not context.get("context_ready"):
        return {
            "schema": "smc_signed_evidence_verification_v1",
            "status": "FAIL",
            "issues": ["validation_authority_context_not_ready"],
            "envelope_path": str(envelope_path),
        }
    return verify_evidence_envelope(
        envelope_path,
        trust_registry_path=str(context["trust_registry_path"]),
        allowed_roles=allowed_roles,
        expected_evidence_type=evidence_type,
        expected_subject_id=subject_id,
        expected_cohort_content_sha256=str(context["cohort_content_sha256"]),
        expected_system_code_freeze_sha256=str(context["system_code_freeze_sha256"]),
    )


def _file_hash_if_present(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


__all__ = [
    "calibration_report",
    "aggregate_perturbation_case_reports",
    "aggregate_sweep_breakout_gold_cases",
    "certification_verdict",
    "evaluate_no_evidence_baselines",
    "evaluate_perturbation_responses",
    "evaluate_runtime_causal_integrity",
    "freeze_poi_ranking",
    "generate_chart_perturbations",
    "load_adjudicated_evaluation_inputs",
    "load_external_validation_readiness",
    "run_sequential_replay",
]
