#!/usr/bin/env python3
"""Evaluate engine perception against adjudicated object-level case labels.

This intentionally refuses to turn engine-generated pseudo-labels or synthetic
fixtures into a real accuracy claim.  Only source-aligned, expert-approved
cases with adjudicated object annotations are scored.
"""
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

from smc_desk.case_audit import audit_case, find_case_files
from smc_desk.perception import (
    EVENT_PRIMITIVES,
    ZONE_PRIMITIVES,
    annotation_set_from_case,
    engine_perception_objects,
    greedy_match_annotations,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score engine SMC objects against adjudicated expert labels.")
    parser.add_argument("--root", default="case_library", help="Case-library root containing case.json files.")
    parser.add_argument("--output-dir", default="backtests/perception/gold", help="Directory for JSON and Markdown reports.")
    parser.add_argument("--min-cases", type=int, default=20, help="Minimum adjudicated cases required before an accuracy claim.")
    parser.add_argument("--event-time-tolerance-minutes", type=float, default=15.0)
    parser.add_argument("--event-price-tolerance-pct", type=float, default=0.001)
    parser.add_argument("--min-zone-iou", type=float, default=0.5)
    return parser.parse_args()


def _metric(tp: int, fp: int, fn: int) -> dict[str, float | int | None]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def _primitive_order() -> list[str]:
    return [
        "bos",
        "choch",
        "liquidity_sweep",
        "fvg",
        "order_block",
        "equal_highs",
        "equal_lows",
        "inducement",
        "supply",
        "demand",
    ]


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root)
    counters: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    case_results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for case_path in find_case_files(root):
        audit = audit_case(case_path)
        if not audit["usable_for_perception_evaluation"]:
            skipped.append({"case_path": str(case_path), "reason": ",".join(audit["warnings"]) or "not_perception_ready"})
            continue

        case = json.loads(case_path.read_text(encoding="utf-8"))
        truth = annotation_set_from_case(case).objects
        machine = engine_perception_objects(case.get("machine_analysis") or {})
        matches = greedy_match_annotations(
            truth,
            machine,
            time_tolerance_minutes=args.event_time_tolerance_minutes,
            price_tolerance_pct=args.event_price_tolerance_pct,
            min_zone_iou=args.min_zone_iou,
        )
        matched_truth = {truth_index for truth_index, _machine_index, _score in matches}
        matched_machine = {machine_index for _truth_index, machine_index, _score in matches}
        for truth_index, machine_index, _score in matches:
            primitive = truth[truth_index].primitive
            counters[primitive]["tp"] += 1
        for truth_index, annotation in enumerate(truth):
            if truth_index not in matched_truth:
                counters[annotation.primitive]["fn"] += 1
        for machine_index, annotation in enumerate(machine):
            if machine_index not in matched_machine:
                counters[annotation.primitive]["fp"] += 1

        case_results.append(
            {
                "case_id": case.get("case_id"),
                "case_path": str(case_path),
                "truth_objects": len(truth),
                "machine_objects": len(machine),
                "matched_objects": len(matches),
                "unmatched_truth": [truth[index].annotation_id for index in range(len(truth)) if index not in matched_truth],
                "unmatched_machine": [machine[index].annotation_id for index in range(len(machine)) if index not in matched_machine],
            }
        )

    per_primitive = {primitive: _metric(**counters[primitive]) for primitive in _primitive_order()}
    totals = {key: sum(counters[primitive][key] for primitive in _primitive_order()) for key in ("tp", "fp", "fn")}
    status = "ready_for_measurement" if len(case_results) >= args.min_cases else "insufficient_ground_truth"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "method": {
            "truth_source": "source-aligned, gold-standard case.json expert_label.perception_annotations with label_status=adjudicated",
            "event_time_tolerance_minutes": args.event_time_tolerance_minutes,
            "event_price_tolerance_pct": args.event_price_tolerance_pct,
            "min_zone_iou": args.min_zone_iou,
            "minimum_cases": args.min_cases,
        },
        "eligible_cases": len(case_results),
        "skipped_cases": skipped,
        "overall": _metric(**totals),
        "per_primitive": per_primitive,
        "cases": case_results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Gold-Set SMC Perception Evaluation",
        "",
        f"Status: **{report['status']}**",
        f"Eligible adjudicated cases: **{report['eligible_cases']}** / required **{report['method']['minimum_cases']}**",
        "",
        "This report scores exact expert-labelled objects, not synthetic fixtures or engine pseudo-labels.",
        "Events require matching primitive/direction/time/price. Zones require matching primitive/direction and price-band IoU.",
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
        lines.append(
            f"| {primitive} | {metrics['tp']} | {metrics['fp']} | {metrics['fn']} | "
            f"{metrics['precision']} | {metrics['recall']} | {metrics['f1']} |"
        )
    if report["status"] != "ready_for_measurement":
        lines.extend(
            [
                "",
                "> No accuracy claim is valid yet. Add adjudicated, source-aligned object labels to more cases first.",
            ]
        )
    lines.extend(["", f"Skipped cases: {len(report['skipped_cases'])}", ""])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    report = evaluate(args)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "perception_gold_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = render_markdown(report)
    (out_dir / "perception_gold_report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Wrote {out_dir / 'perception_gold_report.md'}")


if __name__ == "__main__":
    main()
