#!/usr/bin/env python3
"""Run canonical validation and append one source-bound registry record."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "evidence" / "VALIDATION_REGISTRY.json"
SCHEMA = "smc_codex_validation_registry_v2"


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": SCHEMA,
            "registry_status": "PASS",
            "policy": {
                "records_are_append_only": True,
                "generic_latest_validation_is_prohibited": True,
                "current_gate_is_explicit": True,
                "test_results_apply_only_to_recorded_source_state": True,
                "failed_records_are_retained": True,
            },
            "current_gate": None,
            "records": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"{path} is not {SCHEMA}; migrate it explicitly before recording new validation.")
    if "latest_validation" in payload:
        raise ValueError("latest_validation is prohibited by validation registry v2.")
    return payload


def append_validation_record(
    registry: dict[str, Any],
    record: dict[str, Any],
    *,
    make_current: bool = True,
) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "").strip()
    if not record_id:
        raise ValueError("record_id is required")
    existing = {str(item.get("record_id")) for item in registry.get("records", [])}
    if record_id in existing:
        raise ValueError(f"Validation record already exists: {record_id}")
    out = copy.deepcopy(registry)
    out.setdefault("records", []).append(copy.deepcopy(record))
    # Registry integrity and validation outcome are separate. Failed validation
    # records must remain queryable without making the registry file unhealthy.
    out["registry_status"] = out.get("registry_status", "PASS")
    if make_current:
        out["current_gate"] = {
            "record_id": record_id,
            "work_package": record.get("work_package"),
            "gate": record.get("gate"),
        }
    return out


def run_command(command: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    summary = next((line for line in reversed(output.splitlines()) if line.strip()), "no output")
    return {
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "summary": summary,
    }


def git_value(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--work-package", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--authority-mode", default="research_only")
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument(
        "--source-manifest",
        type=Path,
        help="Optional exact source manifest to bind into the append-only record.",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    if args.record_id in {str(item.get("record_id")) for item in registry.get("records", [])}:
        raise SystemExit(f"Refusing to overwrite append-only record: {args.record_id}")

    commands = [
        run_command([sys.executable, "-m", "pytest", "-q"]),
        run_command([sys.executable, "tools/check_governance_consistency.py"]),
        run_command([sys.executable, "tools/check_authority_boundaries.py"]),
    ]
    passed = all(item["exit_code"] == 0 for item in commands)
    worktree_lines = [line for line in git_value("status", "--porcelain").splitlines() if line]
    source = {
        "git_head": git_value("rev-parse", "HEAD"),
        "source_state": "dirty_worktree" if worktree_lines else "committed",
        "working_tree_status_lines": len(worktree_lines),
        "python_version": sys.version.split()[0],
    }
    if args.source_manifest:
        manifest_path = args.source_manifest.expanduser().resolve()
        if not manifest_path.exists():
            raise SystemExit(f"Source manifest does not exist: {manifest_path}")
        try:
            source["source_manifest"] = manifest_path.relative_to(ROOT).as_posix()
        except ValueError:
            source["source_manifest"] = str(manifest_path)
        source["source_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    record = {
        "record_id": args.record_id,
        "work_package": args.work_package,
        "gate": args.gate,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "source": source,
        "commands": commands,
        "primary_result": commands[0]["summary"],
        "report": args.report,
        "authority_mode": args.authority_mode,
        "limitations": list(args.limitation),
    }
    updated = append_validation_record(registry, record, make_current=True)
    args.registry.parent.mkdir(parents=True, exist_ok=True)
    temp = args.registry.with_suffix(args.registry.suffix + ".tmp")
    temp.write_text(json.dumps(updated, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temp.replace(args.registry)
    print(f"Validation record appended: {args.record_id}")
    print(f"Overall status: {record['status']}")
    print(f"Primary result: {record['primary_result']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
