#!/usr/bin/env python3
"""Measure independent reviewer agreement for local SMC perception cases."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.perception_legacy import (
    PerceptionAnnotation,
    PerceptionAnnotationSet,
    greedy_match_annotations,
)


def _safe_div(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _metric(tp: int, fp: int, fn: int) -> dict[str, int | float | None]:
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and precision + recall > 0:
        f1 = round(2 * precision * recall / (precision + recall), 4)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def load_annotation_set(path: Path) -> PerceptionAnnotationSet:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("perception_annotations", payload)
    return PerceptionAnnotationSet.model_validate(raw)


def _case_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("case.json") if path.is_file())


def _by_primitive(objects: list[PerceptionAnnotation]) -> dict[str, list[PerceptionAnnotation]]:
    grouped: dict[str, list[PerceptionAnnotation]] = defaultdict(list)
    for obj in objects:
        grouped[obj.primitive].append(obj)
    return grouped


def _pair_metrics(left: list[PerceptionAnnotation], right: list[PerceptionAnnotation]) -> dict[str, Any]:
    matches = greedy_match_annotations(left, right)
    return _metric(len(matches), len(left) - len(matches), len(right) - len(matches))


def build_agreement_report(
    *,
    root: Path,
    reviewers: list[str],
    min_cases: int = 20,
) -> dict[str, Any]:
    if len(reviewers) != 2:
        raise ValueError("Exactly two independent reviewers are required for this agreement report.")
    reviewer_a, reviewer_b = reviewers
    per_primitive_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    case_results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for case_path in _case_files(root):
        case_dir = case_path.parent
        left_path = case_dir / f"{reviewer_a}.json"
        right_path = case_dir / f"{reviewer_b}.json"
        if not left_path.exists() or not right_path.exists():
            skipped.append({"case_path": str(case_path), "reason": "missing_reviewer_file"})
            continue
        left = load_annotation_set(left_path)
        right = load_annotation_set(right_path)
        if not left.objects and not right.objects:
            skipped.append({"case_path": str(case_path), "reason": "no_reviewer_objects"})
            continue

        case = json.loads(case_path.read_text(encoding="utf-8"))
        left_by = _by_primitive(left.objects)
        right_by = _by_primitive(right.objects)
        primitives = sorted(set(left_by) | set(right_by))
        case_primitive_metrics = {}
        case_tp = case_fp = case_fn = 0
        for primitive in primitives:
            metrics = _pair_metrics(left_by.get(primitive, []), right_by.get(primitive, []))
            counts = per_primitive_counts[primitive]
            counts["tp"] += int(metrics["tp"])
            counts["fp"] += int(metrics["fp"])
            counts["fn"] += int(metrics["fn"])
            case_tp += int(metrics["tp"])
            case_fp += int(metrics["fp"])
            case_fn += int(metrics["fn"])
            case_primitive_metrics[primitive] = metrics

        case_results.append(
            {
                "case_id": case.get("case_id"),
                "case_path": str(case_path),
                "symbol": case.get("symbol"),
                "decision_time": case.get("decision_time"),
                "reviewer_a": reviewer_a,
                "reviewer_b": reviewer_b,
                "reviewer_a_status": left.label_status,
                "reviewer_b_status": right.label_status,
                "reviewer_a_objects": len(left.objects),
                "reviewer_b_objects": len(right.objects),
                "overall": _metric(case_tp, case_fp, case_fn),
                "per_primitive": case_primitive_metrics,
            }
        )

    totals = {"tp": 0, "fp": 0, "fn": 0}
    for counts in per_primitive_counts.values():
        totals["tp"] += counts["tp"]
        totals["fp"] += counts["fp"]
        totals["fn"] += counts["fn"]
    per_primitive = {primitive: _metric(**counts) for primitive, counts in sorted(per_primitive_counts.items())}
    ready = len(case_results) >= min_cases and any(value["tp"] + value["fp"] + value["fn"] > 0 for value in per_primitive_counts.values())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "reviewers": reviewers,
        "status": "ready_for_ai_promotion_baseline" if ready else "insufficient_reviewer_annotations",
        "minimum_cases": min_cases,
        "eligible_cases": len(case_results),
        "skipped_cases": skipped,
        "overall": _metric(**totals),
        "per_primitive": per_primitive,
        "human_baseline_policy": "AI reviewer must meet or exceed the relevant human inter-reviewer F1 lower bound on a blinded holdout before promotion.",
        "cases": case_results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Human Reviewer Agreement Report",
        "",
        f"Status: **{report['status']}**",
        f"Eligible cases: **{report['eligible_cases']}** / required **{report['minimum_cases']}**",
        f"Reviewers: {', '.join(report['reviewers'])}",
        "",
        "## Overall",
        "",
        "| TP | FP | FN | Precision | Recall | F1 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    overall = report["overall"]
    lines.append(f"| {overall['tp']} | {overall['fp']} | {overall['fn']} | {overall['precision']} | {overall['recall']} | {overall['f1']} |")
    lines.extend(["", "## By Primitive", "", "| Primitive | TP | FP | FN | Precision | Recall | F1 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for primitive, metrics in report["per_primitive"].items():
        lines.append(f"| {primitive} | {metrics['tp']} | {metrics['fp']} | {metrics['fn']} | {metrics['precision']} | {metrics['recall']} | {metrics['f1']} |")
    if report["status"] != "ready_for_ai_promotion_baseline":
        lines.extend(["", "> No AI promotion baseline is valid yet. Fill independent reviewer annotations first."])
    lines.extend(["", f"Skipped cases: {len(report['skipped_cases'])}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure object-level agreement between two SMC reviewers.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--reviewers", nargs=2, default=["reviewer_a", "reviewer_b"])
    parser.add_argument("--min-cases", type=int, default=20)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_agreement_report(root=Path(args.root), reviewers=args.reviewers, min_cases=args.min_cases)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "reviewer_agreement.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "reviewer_agreement.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
