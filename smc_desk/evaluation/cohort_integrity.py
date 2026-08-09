"""Canonical integrity contract for blind human-review cohorts.

The builder and scorer share this module so their schema, hashing, provenance,
and completion rules cannot evolve independently.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

COHORT_SCHEMA = "markup_cohort_v2"
MARKUP_SCHEMA = "markup_annotation_v2"
DEFINITION_STATUS_SCHEMA = "definition_set_status_v2"
REVIEWED_DEFINITION_STATUS = "ANALYST_REVIEWED"
VALID_COHORT_STATUS = "VALID_FOR_EXPERT_DEVELOPMENT"
INVALID_COHORT_STATUS = "INVALID_DO_NOT_MARK"
FAILED_COHORT_STATUS = "INVALID_GENERATION_FAILED"
SCOREABLE_COHORT_STATUSES = {
    VALID_COHORT_STATUS,
    "VALID_FOR_BLIND_REVIEW",
}
RENDER_TIMEFRAMES = ("1d", "4h", "1h", "15m")
VALID_TIMEFRAMES = set(RENDER_TIMEFRAMES)
STRUCTURE_PRIMITIVES = {"bos", "choch", "swing_high", "swing_low"}
VALID_BIASES = {"bullish", "bearish", "ranging", "unclear"}
VALID_DECISIONS = {"yes", "no", "watch"}


def float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(payload: Any, *, pretty: bool = False) -> bytes:
    options: dict[str, Any] = {"sort_keys": True, "default": str}
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(payload, **options) + "\n").encode("utf-8")


def write_json(path: Path, payload: Any) -> dict[str, Any]:
    content = json_bytes(payload, pretty=True)
    path.write_bytes(content)
    return {"sha256": sha256_bytes(content), "size_bytes": len(content)}


def artifact(path: Path) -> dict[str, Any]:
    return {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def case_ids_sha256(case_ids: list[str]) -> str:
    canonical = "\n".join(sorted(case_ids)) + "\n"
    return sha256_bytes(canonical.encode("utf-8"))


def definition_case_set_sha256(root: Path, case_ids: list[str]) -> str:
    """Bind case identities and the exact selection metadata they name."""
    records = []
    for case_id in sorted(case_ids):
        metadata_path = root / case_id / "metadata.json"
        if not metadata_path.is_file():
            raise ValueError(f"definition-set metadata is missing: {case_id}")
        records.append({
            "case_id": case_id,
            "metadata": json.loads(metadata_path.read_text(encoding="utf-8")),
        })
    return sha256_bytes(json_bytes(records))


def manifest_content_sha256(manifest: dict[str, Any]) -> str:
    content = {key: value for key, value in manifest.items() if key != "cohort_content_sha256"}
    return sha256_bytes(json_bytes(content))


def parse_aware_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def reviewed_definition_issues(
    status: dict[str, Any], case_ids: list[str], case_set_sha256: str
) -> list[str]:
    """Validate the minimum provenance needed to call a selection reviewed."""
    issues: list[str] = []
    if status.get("schema") != DEFINITION_STATUS_SCHEMA:
        issues.append(f"schema must be {DEFINITION_STATUS_SCHEMA}")
    if status.get("selection_status") != REVIEWED_DEFINITION_STATUS:
        issues.append(f"selection_status must be {REVIEWED_DEFINITION_STATUS}")
    if not str(status.get("analyst_id") or "").strip():
        issues.append("analyst_id is required")
    rationale = status.get("selection_rationale")
    if not (
        isinstance(rationale, str) and rationale.strip()
        or isinstance(rationale, list) and any(str(item).strip() for item in rationale)
    ):
        issues.append("selection_rationale is required")
    if parse_aware_timestamp(status.get("reviewed_at")) is None:
        issues.append("reviewed_at must be a timezone-aware ISO-8601 timestamp")
    if status.get("scoreable") is not True:
        issues.append("scoreable must be true")
    if status.get("case_count") != len(case_ids):
        issues.append("case_count does not match the definition-set directories")
    if status.get("case_ids_sha256") != case_ids_sha256(case_ids):
        issues.append("case_ids_sha256 does not match the definition-set directories")
    if status.get("case_set_sha256") != case_set_sha256:
        issues.append("case_set_sha256 does not match the definition-set metadata")
    return issues


def _safe_artifact_path(container: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"Unsafe artifact path in cohort manifest: {relative!r}")
    target = (container / relative).resolve()
    try:
        target.relative_to(container.resolve())
    except ValueError:
        raise ValueError(f"Artifact escapes its container directory: {relative}") from None
    return target


def _verify_artifacts(container: Path, artifacts: Any, *, label: str) -> None:
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError(f"{label} has no artifact seals")
    for relative, expected in artifacts.items():
        if not isinstance(expected, dict):
            raise ValueError(f"{label} artifact seal is invalid: {relative}")
        target = _safe_artifact_path(container, str(relative))
        if not target.is_file():
            raise ValueError(f"{label} artifact is missing: {relative}")
        if target.stat().st_size != expected.get("size_bytes"):
            raise ValueError(f"{label} artifact size mismatch: {relative}")
        if sha256_file(target) != expected.get("sha256"):
            raise ValueError(f"{label} artifact hash mismatch: {relative}")


def assert_cohort_scoreable(cohort: Path) -> dict[str, Any]:
    """Refuse unsealed, tampered, partial, or provenance-free cohorts."""
    cohort = cohort.expanduser().resolve()
    manifest_path = cohort / "cohort_manifest.json"
    if not manifest_path.exists():
        raise ValueError("Cohort has no cohort_manifest.json; provenance is unverified.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    status = str(manifest.get("validation_status") or "UNVERIFIED")
    if status not in SCOREABLE_COHORT_STATUSES:
        reasons = "; ".join(str(item) for item in (manifest.get("invalid_reasons") or []))
        detail = f" ({reasons})" if reasons else ""
        raise ValueError(f"Cohort is not scoreable: {status}{detail}")
    if manifest.get("schema") != COHORT_SCHEMA:
        raise ValueError(f"Scoreable cohorts must use {COHORT_SCHEMA}")
    if manifest.get("cohort_content_sha256") != manifest_content_sha256(manifest):
        raise ValueError("Cohort manifest content hash mismatch")

    cohort_artifacts = manifest.get("cohort_artifacts")
    if not isinstance(cohort_artifacts, dict) or "REVIEW_INSTRUCTIONS.md" not in cohort_artifacts:
        raise ValueError("Cohort review instructions are not hash-bound")
    _verify_artifacts(cohort, cohort_artifacts, label="Cohort")

    source = manifest.get("source") or {}
    source_path = Path(str(source.get("path") or "")).expanduser()
    if not source_path.is_file():
        raise ValueError(f"Bound OHLCV source is missing: {source_path}")
    if source_path.stat().st_size != source.get("size_bytes"):
        raise ValueError("Bound OHLCV source size changed after cohort generation")
    if sha256_file(source_path) != source.get("sha256"):
        raise ValueError("Bound OHLCV source hash changed after cohort generation")

    definition = manifest.get("definition_set") or {}
    definition_path = Path(str(definition.get("path") or "")).expanduser()
    status_hash = definition.get("status_file_sha256")
    if status_hash:
        status_path = definition_path / "definition_set_status.json"
        if not status_path.is_file() or sha256_file(status_path) != status_hash:
            raise ValueError("Definition-set review provenance changed after cohort generation")
    selected_case_ids = definition.get("all_case_ids")
    if not isinstance(selected_case_ids, list) or not selected_case_ids:
        raise ValueError("Definition-set case inventory is missing")
    if definition_case_set_sha256(definition_path, selected_case_ids) != definition.get(
        "all_case_set_sha256"
    ):
        raise ValueError("Definition-set case metadata changed after cohort generation")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Cohort manifest has no cases")
    ids = [str(row.get("case_id") or "") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)) or any(not case_id for case_id in ids):
        raise ValueError("Cohort manifest case identifiers are missing or duplicated")
    ready = [row for row in cases if row.get("status") == "READY"]
    if len(ready) != manifest.get("ready_count") or len(cases) != manifest.get("case_count"):
        raise ValueError("Cohort manifest case counts do not reconcile")
    if len(ready) != len(cases) or manifest.get("failed_count") != 0:
        raise ValueError("A scoreable cohort cannot contain failed or non-ready cases")

    required = {"markup_template.json", "_sealed_system_answer.json", "metadata.json"}
    for row in ready:
        case_id = str(row["case_id"])
        case_dir = cohort / case_id
        if not case_dir.is_dir():
            raise ValueError(f"Cohort case directory is missing: {case_id}")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, dict) or not required.issubset(artifacts):
            raise ValueError(f"Case {case_id} lacks required artifact seals")
        chart_names = row.get("charts") or []
        if len(chart_names) != len(RENDER_TIMEFRAMES):
            raise ValueError(f"Case {case_id} does not contain four review charts")
        for chart_name in chart_names:
            if f"charts/{chart_name}" not in artifacts:
                raise ValueError(f"Case {case_id} chart is not hash-bound: {chart_name}")
        _verify_artifacts(case_dir, artifacts, label=f"Case {case_id}")

        answer_hash = artifacts["_sealed_system_answer.json"].get("sha256")
        if row.get("sealed_answer_sha256") != answer_hash:
            raise ValueError(f"Case {case_id} sealed-answer hash does not reconcile")
        answer = json.loads((case_dir / "_sealed_system_answer.json").read_text(encoding="utf-8"))
        if answer.get("sealed") is not True or answer.get("generation_status") != "COMPLETE":
            raise ValueError(f"Case {case_id} system answer is not a complete seal")
        decision = answer.get("decision") if isinstance(answer.get("decision"), dict) else {}
        if decision.get("classification") not in VALID_DECISIONS:
            raise ValueError(f"Case {case_id} system decision is unresolved")
        metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
        sealed_time = parse_aware_timestamp(answer.get("decision_time"))
        metadata_time = parse_aware_timestamp(metadata.get("decision_time"))
        if not sealed_time or not metadata_time or sealed_time != metadata_time:
            raise ValueError(f"Case {case_id} sealed decision time does not match metadata")

        source_slices = row.get("source_slices")
        if not isinstance(source_slices, dict) or set(source_slices) != VALID_TIMEFRAMES:
            raise ValueError(f"Case {case_id} source-slice seals are incomplete")
        for timeframe, slice_info in source_slices.items():
            if not isinstance(slice_info, dict) or not slice_info.get("sha256") or not slice_info.get("row_count"):
                raise ValueError(f"Case {case_id} source-slice seal is invalid for {timeframe}")
        seal_payload = {"artifacts": artifacts, "source_slices": source_slices}
        if row.get("case_seal_sha256") != sha256_bytes(json_bytes(seal_payload)):
            raise ValueError(f"Case {case_id} seal hash does not reconcile")
    return manifest


def validate_completed_markup(
    human: dict[str, Any], *, case_id: str, reviewer_id: str, metadata: dict[str, Any]
) -> list[str]:
    """Separate a deliberate blank answer from an unfinished JSON form."""
    issues: list[str] = []
    if human.get("schema") != MARKUP_SCHEMA:
        issues.append(f"schema must be {MARKUP_SCHEMA}")
    if human.get("review_status") != "COMPLETE":
        issues.append("review_status must be COMPLETE")
    if parse_aware_timestamp(human.get("review_completed_at")) is None:
        issues.append("review_completed_at must be a timezone-aware ISO-8601 timestamp")
    if str(human.get("case_id") or "") != case_id:
        issues.append("case_id does not match the case directory")
    if str(human.get("reviewer_id") or "") != str(reviewer_id):
        issues.append("reviewer_id does not match the sealed cohort")
    if str(human.get("instrument") or "") != str(metadata.get("instrument") or ""):
        issues.append("instrument does not match metadata")
    human_time = parse_aware_timestamp(human.get("decision_time"))
    metadata_time = parse_aware_timestamp(metadata.get("decision_time"))
    if not human_time or not metadata_time or human_time != metadata_time:
        issues.append("decision_time does not match metadata")

    bias = str(human.get("htf_bias") or "").strip().lower()
    if bias not in VALID_BIASES:
        issues.append(f"htf_bias must be one of {sorted(VALID_BIASES)}")
    if str(human.get("context_timeframe") or "").strip().lower() not in VALID_TIMEFRAMES:
        issues.append(f"context_timeframe must be one of {sorted(VALID_TIMEFRAMES)}")
    if str(human.get("would_you_trade_this") or "").strip().lower() not in VALID_DECISIONS:
        issues.append(f"would_you_trade_this must be one of {sorted(VALID_DECISIONS)}")

    dealing_range = human.get("dealing_range") or {}
    range_low = float_or_none(dealing_range.get("low"))
    range_high = float_or_none(dealing_range.get("high"))
    if (range_low is None) != (range_high is None):
        issues.append("dealing_range high and low must both be filled or both be blank")
    if range_low is not None and str(dealing_range.get("timeframe") or "").lower() not in VALID_TIMEFRAMES:
        issues.append("a filled dealing_range requires a valid timeframe")
    if range_low is not None and range_high is not None and range_high <= range_low:
        issues.append("dealing_range high must be greater than low")

    annotations = human.get("annotations")
    if not isinstance(annotations, list):
        issues.append("annotations must be a list")
    else:
        for index, annotation in enumerate(annotations):
            if not isinstance(annotation, dict):
                issues.append(f"annotation {index} must be an object")
                continue
            primitive = str(annotation.get("primitive") or "").strip().lower()
            if primitive not in STRUCTURE_PRIMITIVES:
                issues.append(
                    f"annotation {index} primitive must be one of {sorted(STRUCTURE_PRIMITIVES)}; "
                    "record sweeps under liquidity.swept"
                )
            if str(annotation.get("direction") or "").strip().lower() not in {"bullish", "bearish"}:
                issues.append(f"annotation {index} requires bullish or bearish direction")
            if str(annotation.get("timeframe") or "").strip().lower() not in VALID_TIMEFRAMES:
                issues.append(f"annotation {index} requires a valid timeframe")
            if float_or_none(annotation.get("price")) is None:
                issues.append(f"annotation {index} requires a price")
            annotation_time = parse_aware_timestamp(annotation.get("timestamp"))
            if annotation_time is None:
                issues.append(f"annotation {index} requires a timezone-aware timestamp")
            elif metadata_time and annotation_time > metadata_time:
                issues.append(f"annotation {index} occurs after the decision time")
            confidence = float_or_none(annotation.get("confidence"))
            if confidence is not None and not 0 <= confidence <= 1:
                issues.append(f"annotation {index} confidence must be between 0 and 1")

    liquidity = human.get("liquidity") or {}
    for group in ("swept", "unswept"):
        records = liquidity.get(group) or []
        if not isinstance(records, list):
            issues.append(f"liquidity.{group} must be a list")
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict) or float_or_none(record.get("price")) is None:
                issues.append(f"liquidity.{group}[{index}] requires a price")
                continue
            if str(record.get("side") or "").strip().lower() not in {"buy_side", "sell_side"}:
                issues.append(f"liquidity.{group}[{index}] requires buy_side or sell_side")
            if str(record.get("timeframe") or "").strip().lower() not in VALID_TIMEFRAMES:
                issues.append(f"liquidity.{group}[{index}] requires a valid timeframe")
    draw = liquidity.get("expected_draw") or {}
    if float_or_none(draw.get("price")) is not None:
        if str(draw.get("direction") or "").strip().lower() not in {"bullish", "bearish"}:
            issues.append("a filled expected_draw requires bullish or bearish direction")
        if str(draw.get("timeframe") or "").strip().lower() not in VALID_TIMEFRAMES:
            issues.append("a filled expected_draw requires a valid timeframe")

    poi = human.get("primary_poi") or {}
    poi_low = float_or_none(poi.get("price_low"))
    poi_high = float_or_none(poi.get("price_high"))
    if (poi_low is None) != (poi_high is None):
        issues.append("primary_poi low and high must both be filled or both be blank")
    if poi_low is not None and str(poi.get("timeframe") or "").lower() not in VALID_TIMEFRAMES:
        issues.append("a filled primary_poi requires a valid timeframe")
    if poi_low is not None and poi_high is not None and poi_high < poi_low:
        issues.append("primary_poi high must be greater than or equal to low")
    if poi_low is not None and not str(poi.get("kind") or "").strip():
        issues.append("a filled primary_poi requires a kind")
    return issues
