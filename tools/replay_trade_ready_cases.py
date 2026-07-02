#!/usr/bin/env python3
"""Audit real run artifacts for validated TRADE_PLAN_READY cases.

The current local-first system must not infer that trade-ready behavior exists
from synthetic tests. This tool scans saved official decisions and reports what
has actually happened in real/replay runs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def audit_trade_ready_replays(runs_root: str | Path) -> dict[str, Any]:
    root = Path(runs_root).expanduser().resolve()
    decision_files = _decision_files(root)
    trade_ready: list[dict[str, Any]] = []
    watch_or_review_count = 0
    invalid_trade_ready: list[dict[str, Any]] = []

    for file_path in decision_files:
        try:
            decision = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            invalid_trade_ready.append({"path": str(file_path), "reason": f"json_error: {exc}"})
            continue
        state = decision.get("official_state")
        if state != "TRADE_PLAN_READY":
            watch_or_review_count += 1
            continue
        entry = ((decision.get("entry_plan") or {}).get("entry_price"))
        stop = ((decision.get("stop_loss_plan") or {}).get("stop_price"))
        targets = ((decision.get("target_plan") or {}).get("targets") or [])
        rr = ((decision.get("rr_status") or {}).get("rr"))
        validation_status = decision.get("validation_status")
        candidate = {
            "path": str(file_path),
            "symbol": decision.get("symbol"),
            "official_state": state,
            "validation_status": validation_status,
            "direction": decision.get("direction"),
            "entry": entry,
            "stop": stop,
            "targets": targets,
            "rr": rr,
            "chart_template": ((decision.get("annotation_plan") or {}).get("chart_template")),
            "show_trade_box": ((decision.get("annotation_plan") or {}).get("show_trade_box")),
        }
        if validation_status != "VALIDATED" or entry is None or stop is None or not targets:
            invalid_trade_ready.append({**candidate, "reason": "trade_ready_missing_validated_entry_stop_or_target"})
        else:
            trade_ready.append(candidate)

    status = "TRADE_PLAN_READY_CANDIDATES_FOUND" if trade_ready else "NO_TRADE_PLAN_READY_FOUND"
    return {
        "schema": "trade_ready_replay_audit_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs_root": str(root),
        "official_decision_files_scanned": len(decision_files),
        "watch_or_review_decision_count": watch_or_review_count,
        "validated_trade_ready_count": len(trade_ready),
        "invalid_trade_ready_count": len(invalid_trade_ready),
        "status": status,
        "edge_claim_allowed": False,
        "note": "This audit only proves whether real run artifacts reached TRADE_PLAN_READY; outcome expectancy still requires separate walk-forward testing.",
        "validated_trade_ready_cases": trade_ready,
        "invalid_trade_ready_cases": invalid_trade_ready,
    }


def _decision_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("official_decision.json") if path.is_file())


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
    parser.add_argument("--runs-root", default="analysis_runs", help="Folder containing saved official_decision.json artifacts.")
    parser.add_argument("--output", default=None, help="Optional JSON report path.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when no validated TRADE_PLAN_READY case exists.")
    args = parser.parse_args()

    report = audit_trade_ready_replays(args.runs_root)
    _write_report(report, args.output)
    if args.strict and report["status"] != "TRADE_PLAN_READY_CANDIDATES_FOUND":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
