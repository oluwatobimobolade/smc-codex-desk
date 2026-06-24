from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .case_library import file_sha256
from .perception_legacy import annotation_set_from_case, annotation_set_is_gold_ready


GOLD_REVIEW_STATUSES = {"gold_standard", "approved"}


def _as_path(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value))


def _false_checklist_items(case: dict[str, Any]) -> list[str]:
    checklist = (
        case.get("machine_analysis", {})
        .get("trade_plan", {})
        .get("checklist", {})
    )
    return [key for key, value in checklist.items() if value is False]


def audit_case(case_path: Path) -> dict[str, Any]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    data = case.get("data", {})
    chart_evidence = case.get("chart_evidence") or {}
    source_alignment = case.get("source_alignment") or {}
    plan = case.get("machine_analysis", {}).get("trade_plan", {})
    expert_label = case.get("expert_label") or {}

    warnings: list[str] = []
    source_csv = _as_path(data.get("source_csv"))
    source_exists = bool(source_csv and source_csv.exists())
    hash_matches: bool | None = None
    if not source_csv:
        warnings.append("missing_source_csv")
    elif not source_exists:
        warnings.append("source_csv_missing")
    else:
        expected_hash = data.get("source_csv_sha256")
        actual_hash = file_sha256(source_csv)
        hash_matches = actual_hash == expected_hash
        if not hash_matches:
            warnings.append("source_csv_hash_mismatch")

    screenshots = chart_evidence.get("screenshots") or {}
    missing_screenshots = [
        timeframe
        for timeframe, screenshot_path in screenshots.items()
        if not Path(str(screenshot_path)).exists()
    ]
    if chart_evidence and missing_screenshots:
        warnings.append("screenshot_missing")
    if not chart_evidence:
        warnings.append("missing_chart_evidence")

    chart_matches = source_alignment.get("chart_exchange_matches_ohlcv")
    if chart_matches is not True:
        warnings.append("chart_source_not_verified")

    quality = data.get("quality") or {}
    if int(quality.get("gap_count") or 0) > 0:
        warnings.append("ohlcv_gaps")
    if int(quality.get("duplicate_timestamps") or 0) > 0:
        warnings.append("duplicate_timestamps")
    if int(quality.get("nan_ohlc_rows") or 0) > 0:
        warnings.append("nan_ohlc_rows")

    review_status = str(expert_label.get("review_status") or "missing")
    if review_status == "unreviewed":
        warnings.append("unreviewed")

    perception_annotation_count = 0
    perception_label_status = "missing"
    perception_gold_ready = False
    try:
        perception_labels = annotation_set_from_case(case)
        perception_annotation_count = len(perception_labels.objects)
        perception_label_status = perception_labels.label_status
        perception_gold_ready = annotation_set_is_gold_ready(perception_labels)
    except ValueError:
        warnings.append("invalid_perception_annotations")
    if perception_label_status == "missing":
        warnings.append("missing_perception_annotations")
    elif not perception_gold_ready:
        warnings.append("perception_annotations_not_adjudicated")

    false_items = _false_checklist_items(case)
    return {
        "case_id": case.get("case_id"),
        "case_path": str(case_path.resolve()),
        "case_dir": str(case_path.parent.resolve()),
        "symbol": case.get("symbol"),
        "exchange": case.get("exchange"),
        "decision_time": case.get("decision_time"),
        "case_kind": case.get("case_kind"),
        "review_status": review_status,
        "is_gold_standard": review_status in GOLD_REVIEW_STATUSES,
        "perception_label_status": perception_label_status,
        "perception_annotation_count": perception_annotation_count,
        "perception_gold_ready": perception_gold_ready,
        "machine_verdict": plan.get("verdict"),
        "machine_grade": plan.get("setup_grade"),
        "machine_direction": plan.get("direction"),
        "risk_pct": plan.get("risk_pct"),
        "confluence_score": plan.get("confluence_score"),
        "missing_machine_checks": false_items,
        "source_csv": str(source_csv) if source_csv else None,
        "source_csv_exists": source_exists,
        "source_csv_hash_matches": hash_matches,
        "chart_tradingview_symbol": chart_evidence.get("tradingview_symbol"),
        "chart_exchange_matches_ohlcv": chart_matches,
        "screenshot_count": len(screenshots),
        "missing_screenshots": missing_screenshots,
        "data_quality": quality,
        "warnings": warnings,
        "usable_for_machine_research": (
            source_exists
            and hash_matches is True
            and chart_matches is True
            and not missing_screenshots
            and "ohlcv_gaps" not in warnings
            and "duplicate_timestamps" not in warnings
            and "nan_ohlc_rows" not in warnings
        ),
        "usable_for_training": (
            source_exists
            and hash_matches is True
            and chart_matches is True
            and not missing_screenshots
            and review_status in GOLD_REVIEW_STATUSES
        ),
        "usable_for_perception_evaluation": (
            source_exists
            and hash_matches is True
            and chart_matches is True
            and not missing_screenshots
            and review_status in GOLD_REVIEW_STATUSES
            and perception_gold_ready
        ),
    }


def find_case_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("case.json") if path.is_file())


def audit_case_library(root: Path) -> dict[str, Any]:
    cases = [audit_case(path) for path in find_case_files(root)]
    verdict_counts = Counter(case.get("machine_verdict") or "unknown" for case in cases)
    review_counts = Counter(case.get("review_status") or "missing" for case in cases)
    warning_counts: Counter[str] = Counter()
    for case in cases:
        warning_counts.update(case.get("warnings", []))

    usable_research = [case for case in cases if case["usable_for_machine_research"]]
    usable_training = [case for case in cases if case["usable_for_training"]]
    usable_perception = [case for case in cases if case["usable_for_perception_evaluation"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "summary": {
            "total_cases": len(cases),
            "usable_for_machine_research": len(usable_research),
            "usable_for_training": len(usable_training),
            "usable_for_perception_evaluation": len(usable_perception),
            "gold_standard_cases": sum(1 for case in cases if case["is_gold_standard"]),
            "unreviewed_cases": sum(1 for case in cases if case["review_status"] == "unreviewed"),
            "source_aligned_cases": sum(1 for case in cases if case["chart_exchange_matches_ohlcv"] is True),
            "verdict_counts": dict(verdict_counts),
            "review_status_counts": dict(review_counts),
            "warning_counts": dict(warning_counts),
            "promotion_readiness": "not_ready" if len(usable_training) < 20 else "sample_size_ready_requires_performance_review",
        },
        "cases": cases,
    }


def build_case_index_markdown(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# SMC Case Library Index",
        "",
        f"Generated: {audit['generated_at']}",
        f"Root: `{audit['root']}`",
        "",
        "## Summary",
        f"- Total cases: {summary['total_cases']}",
        f"- Usable for machine research: {summary['usable_for_machine_research']}",
        f"- Usable for training: {summary['usable_for_training']}",
        f"- Usable for perception evaluation: {summary['usable_for_perception_evaluation']}",
        f"- Gold-standard cases: {summary['gold_standard_cases']}",
        f"- Unreviewed cases: {summary['unreviewed_cases']}",
        f"- Source-aligned cases: {summary['source_aligned_cases']}",
        f"- Promotion readiness: `{summary['promotion_readiness']}`",
        "",
        "## Warning Counts",
    ]
    warning_counts = summary.get("warning_counts") or {}
    if warning_counts:
        lines.extend(f"- {key}: {value}" for key, value in sorted(warning_counts.items()))
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Symbol | Decision | Verdict | Grade | Review | Research OK | Training OK | Perception OK | Warnings |",
            "|---|---|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for case in audit["cases"]:
        warnings = ", ".join(case.get("warnings") or []) or "none"
        case_link = Path(case["case_dir"]) / "machine_report.md"
        lines.append(
            "| [{case_id}]({case_link}) | {symbol} | {decision} | {verdict} | {grade} | {review} | {research_ok} | {training_ok} | {perception_ok} | {warnings} |".format(
                case_id=case.get("case_id") or "unknown",
                case_link=case_link,
                symbol=case.get("symbol") or "",
                decision=case.get("decision_time") or "",
                verdict=case.get("machine_verdict") or "",
                grade=case.get("machine_grade") or "",
                review=case.get("review_status") or "",
                research_ok="yes" if case.get("usable_for_machine_research") else "no",
                training_ok="yes" if case.get("usable_for_training") else "no",
                perception_ok="yes" if case.get("usable_for_perception_evaluation") else "no",
                warnings=warnings,
            )
        )
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "Do not use unreviewed cases as expert training labels. A case can support machine research when data/chart alignment is clean, but it becomes training data only after expert review marks it `gold_standard` or `approved`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_case_index(root: Path, output_dir: Path | None = None) -> dict[str, Path]:
    out = output_dir or root
    out.mkdir(parents=True, exist_ok=True)
    audit = audit_case_library(root)
    json_path = out / "index.json"
    md_path = out / "index.md"
    json_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    md_path.write_text(build_case_index_markdown(audit), encoding="utf-8")
    return {"index_json": json_path, "index_md": md_path}
