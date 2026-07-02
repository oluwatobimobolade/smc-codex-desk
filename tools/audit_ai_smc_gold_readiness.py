#!/usr/bin/env python3
"""Audit whether the AI SMC gold set has enough real adjudicated cases.

This is intentionally an audit, not a label generator. Engine labels and model
outputs are never promoted to gold truth here.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from smc_desk.eval.gold_set_loader import GoldChartCase


def audit_gold_readiness(cases_root: str | Path, *, minimum_cases: int = 20) -> dict[str, Any]:
    root = Path(cases_root).expanduser().resolve()
    files = _case_files(root)
    valid_cases: list[str] = []
    rejected_cases: list[dict[str, Any]] = []
    pending_cases: list[str] = []

    for file_path in files:
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            rejected_cases.append(_rejected(file_path, "json_error", str(exc)))
            continue
        records = payload if isinstance(payload, list) else [payload]
        for index, record in enumerate(records):
            case_ref = f"{file_path}#{index}" if isinstance(payload, list) else str(file_path)
            if isinstance(record, dict) and record.get("adjudication_status") in {"pending", "rejected"}:
                pending_cases.append(case_ref)
                continue
            try:
                case = GoldChartCase.model_validate(record)
            except ValidationError as exc:
                rejected_cases.append(_rejected(Path(case_ref), "validation_error", str(exc)))
                continue
            valid_cases.append(case.case_id)

    status = "READY" if len(valid_cases) >= minimum_cases else "INSUFFICIENT_GROUND_TRUTH"
    return {
        "schema": "ai_smc_gold_readiness_audit_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases_root": str(root),
        "minimum_cases": int(minimum_cases),
        "adjudicated_case_count": len(valid_cases),
        "pending_or_rejected_case_count": len(pending_cases),
        "invalid_case_count": len(rejected_cases),
        "status": status,
        "gold_truth_policy": "human_adjudicated_labels_only",
        "engine_weak_labels_promoted_to_gold": False,
        "adjudicated_case_ids": valid_cases,
        "pending_or_rejected_cases": pending_cases,
        "invalid_cases": rejected_cases,
    }


def _case_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def _rejected(path: Path, code: str, message: str) -> dict[str, str]:
    return {"path": str(path), "code": code, "message": message}


def _write_report(report: dict[str, Any], output: str | Path | None) -> None:
    if output is None:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(str(output_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-root", default="data/gold_sets/ai_smc", help="Folder or JSON file containing adjudicated gold cases.")
    parser.add_argument("--minimum-cases", type=int, default=20, help="Minimum adjudicated cases required before accuracy claims.")
    parser.add_argument("--output", default=None, help="Optional JSON report path.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when the gold set is not ready.")
    args = parser.parse_args()

    report = audit_gold_readiness(args.cases_root, minimum_cases=args.minimum_cases)
    _write_report(report, args.output)
    if args.strict and report["status"] != "READY":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
