#!/usr/bin/env python3
"""Export adjudicated local cases as a JSONL dataset for future local AI training."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.perception_legacy import PerceptionAnnotationSet


def _case_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("case.json") if path.is_file())


def _load_annotations(path: Path) -> PerceptionAnnotationSet | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("perception_annotations", payload)
    return PerceptionAnnotationSet.model_validate(raw)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(root: Path, reviewers: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for case_path in _case_files(root):
        case_dir = case_path.parent
        adjudicated_path = case_dir / "adjudicated.json"
        adjudicated_payload = _load_json(adjudicated_path) if adjudicated_path.exists() else None
        adjudicated = _load_annotations(adjudicated_path)
        if adjudicated is None or adjudicated.label_status != "adjudicated":
            skipped.append({"case_path": str(case_path), "reason": "missing_or_unadjudicated_labels"})
            continue
        case = _load_json(case_path)
        reviewer_payloads = []
        for reviewer in reviewers:
            reviewer_path = case_dir / f"{reviewer}.json"
            reviewer_set = _load_annotations(reviewer_path)
            if reviewer_set is None:
                skipped.append({"case_path": str(case_path), "reason": f"missing_{reviewer}"})
                reviewer_payloads = []
                break
            reviewer_payloads.append(
                {
                    "reviewer_id": reviewer,
                    "label_status": reviewer_set.label_status,
                    "objects": [item.model_dump(mode="json") for item in reviewer_set.objects],
                    "notes": reviewer_set.notes,
                }
            )
        if not reviewer_payloads:
            continue
        weak_labels_path = case_dir / "engine_weak_labels.json"
        case_manifest_path = case_dir / "case_manifest.json"
        case_manifest = _load_json(case_manifest_path) if case_manifest_path.exists() else {}
        row = {
            "training_schema_version": "1.0",
            "case_id": case.get("case_id"),
            "symbol": case.get("symbol"),
            "decision_time": case.get("decision_time"),
            "source": {
                "case_path": str(case_path.resolve()),
                "analysis_window_15m": case.get("data", {}).get("analysis_window_csv"),
                "raw_charts": case.get("chart_evidence", {}).get("screenshots", {}),
                "case_manifest": str(case_manifest_path.resolve()) if case_manifest_path.exists() else None,
            },
            "reviewers": reviewer_payloads,
            "adjudication": {
                "label_status": adjudicated.label_status,
                "reviewer_ids": adjudicated.reviewer_ids,
                "adjudicated_by": adjudicated.adjudicated_by,
                "objects": [item.model_dump(mode="json") for item in adjudicated.objects],
                "notes": adjudicated.notes,
                "justification": (adjudicated_payload or {}).get("adjudicator_justification")
                or adjudicated.notes
                or "",
            },
            "engine_weak_labels": {
                "path": str(weak_labels_path.resolve()) if weak_labels_path.exists() else None,
                "truth_status": _load_json(weak_labels_path).get("truth_status") if weak_labels_path.exists() else None,
            },
            "truth_policy": case_manifest.get("truth_policy"),
        }
        rows.append(row)
    return rows, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Export adjudicated local SMC cases to JSONL.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--reviewers", nargs="+", default=["reviewer_a", "reviewer_b"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary-output")
    args = parser.parse_args()
    rows, skipped = build_rows(Path(args.root), args.reviewers)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(Path(args.root).resolve()),
        "rows": len(rows),
        "skipped": skipped,
        "status": "ready" if rows else "no_adjudicated_rows",
        "policy": "Dataset rows require adjudicated labels; reviewer drafts and engine weak labels alone are insufficient.",
    }
    summary_path = Path(args.summary_output) if args.summary_output else output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
