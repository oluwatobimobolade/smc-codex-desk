#!/usr/bin/env python3
"""Maintain an idempotent, zero-capital journal for live engine decisions.

Watches are observations. Only a literal Execute may become a pending paper
order; it becomes a paper trade only after a recorded fill. This keeps live
statistics aligned with the actual engine contract.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "records": []}
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _ledger_lock(path: Path):
    """Serialize read-modify-write journal updates across CLI processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    temporary.replace(path)


def _record_id(analysis_path: Path, payload: dict[str, Any]) -> str:
    source = payload.get("source") or {}
    decision_time = source.get("decision_time") or payload.get("generated_at") or "unknown"
    analysis_hash = hashlib.sha256(analysis_path.read_bytes()).hexdigest()
    raw = f"{analysis_path.resolve()}|{analysis_hash}|{payload.get('symbol')}|{decision_time}"
    return hashlib.sha256(raw.encode()).hexdigest()[:18]


def _load_analysis(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("symbol") or not isinstance(payload.get("trade_plan"), dict):
        raise ValueError("Analysis JSON must contain symbol and trade_plan.")
    return payload


def _is_executable(plan: dict[str, Any]) -> bool:
    targets = plan.get("targets") or []
    return bool(
        plan.get("verdict") == "Execute"
        and float(plan.get("risk_pct") or 0.0) > 0.0
        and plan.get("entry_low") is not None
        and plan.get("entry_high") is not None
        and plan.get("invalidation") is not None
        and targets
    )


def record_analysis(ledger_path: Path, analysis_path: Path) -> dict[str, Any]:
    payload = _load_analysis(analysis_path)
    with _ledger_lock(ledger_path):
        ledger = _load_ledger(ledger_path)
        record_id = _record_id(analysis_path, payload)
        existing = next((record for record in ledger["records"] if record["record_id"] == record_id), None)
        if existing is not None:
            return {"created": False, "record": existing, "summary": journal_summary(ledger)}

        plan = payload["trade_plan"]
        source = payload.get("source") or {}
        if plan.get("verdict") == "Execute" and _is_executable(plan):
            state = "pending_entry"
            classification = "paper_candidate"
        elif str(plan.get("verdict", "")).startswith("Watch"):
            state = "observed_watch"
            classification = "observation"
        else:
            state = "observed_pass"
            classification = "observation"
        record = {
            "record_id": record_id,
            "recorded_at": _now(),
            "analysis_path": str(analysis_path.resolve()),
            "analysis_sha256": hashlib.sha256(analysis_path.read_bytes()).hexdigest(),
            "symbol": payload["symbol"],
            "timeframe": payload.get("timeframe", "15m"),
            "decision_time": source.get("decision_time") or payload.get("generated_at"),
            "latest_close": (payload.get("metrics") or {}).get("latest_close"),
            "classification": classification,
            "state": state,
            "plan": {
                key: plan.get(key)
                for key in (
                    "verdict", "setup_grade", "direction", "entry_type", "risk_pct", "entry_low", "entry_high",
                    "invalidation", "targets", "risk_reward", "confluence_score", "warnings",
                )
            },
            "fill": None,
            "outcome": None,
        }
        ledger["records"].append(record)
        _write_ledger(ledger_path, ledger)
        return {"created": True, "record": record, "summary": journal_summary(ledger)}


def _find_record(ledger: dict[str, Any], record_id: str) -> dict[str, Any]:
    record = next((item for item in ledger["records"] if item["record_id"] == record_id), None)
    if record is None:
        raise ValueError(f"Unknown paper record: {record_id}")
    return record


def mark_filled(ledger_path: Path, record_id: str, price: float) -> dict[str, Any]:
    with _ledger_lock(ledger_path):
        ledger = _load_ledger(ledger_path)
        record = _find_record(ledger, record_id)
        plan = record["plan"]
        if record["state"] != "pending_entry":
            raise ValueError("Only a pending literal Execute can be marked filled.")
        low, high = float(plan["entry_low"]), float(plan["entry_high"])
        if not min(low, high) <= price <= max(low, high):
            raise ValueError("Paper fill must be inside the recorded entry zone.")
        record["state"] = "open"
        record["fill"] = {"price": price, "filled_at": _now()}
        _write_ledger(ledger_path, ledger)
        return {"record": record, "summary": journal_summary(ledger)}


def settle(ledger_path: Path, record_id: str, result: str, r_multiple: float | None = None) -> dict[str, Any]:
    with _ledger_lock(ledger_path):
        ledger = _load_ledger(ledger_path)
        record = _find_record(ledger, record_id)
        if result not in {"win", "loss", "breakeven", "cancelled"}:
            raise ValueError("Result must be win, loss, breakeven, or cancelled.")
        if result == "cancelled":
            if record["state"] != "pending_entry":
                raise ValueError("Only an unfilled pending Execute can be cancelled.")
        elif record["state"] != "open":
            raise ValueError("A paper trade must be marked filled before it can be settled.")
        if result != "cancelled" and r_multiple is None:
            raise ValueError("Settled win/loss/breakeven outcomes require an R multiple.")
        record["state"] = "cancelled" if result == "cancelled" else "settled"
        record["outcome"] = {"result": result, "r_multiple": r_multiple, "settled_at": _now()}
        _write_ledger(ledger_path, ledger)
        return {"record": record, "summary": journal_summary(ledger)}


def journal_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    records = ledger.get("records") or []
    settled = [record for record in records if record.get("state") == "settled"]
    values = [float(record["outcome"]["r_multiple"]) for record in settled if record.get("outcome", {}).get("r_multiple") is not None]
    wins = sum(1 for record in settled if record["outcome"]["result"] == "win")
    losses = sum(1 for record in settled if record["outcome"]["result"] == "loss")
    return {
        "observations": sum(1 for record in records if record.get("classification") == "observation"),
        "pending_entries": sum(1 for record in records if record.get("state") == "pending_entry"),
        "open_paper_trades": sum(1 for record in records if record.get("state") == "open"),
        "settled_paper_trades": len(settled),
        "cancelled_paper_candidates": sum(1 for record in records if record.get("state") == "cancelled"),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(settled), 4) if settled else None,
        "total_r": round(sum(values), 4),
        "avg_r": round(sum(values) / len(values), 4) if values else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and settle zero-capital paper decisions from engine JSON.")
    parser.add_argument("--ledger", default=str(ROOT / "journal/paper/ledger.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--analysis", required=True)
    fill_parser = subparsers.add_parser("fill")
    fill_parser.add_argument("--record-id", required=True)
    fill_parser.add_argument("--price", required=True, type=float)
    settle_parser = subparsers.add_parser("settle")
    settle_parser.add_argument("--record-id", required=True)
    settle_parser.add_argument("--result", required=True)
    settle_parser.add_argument("--r-multiple", type=float)
    subparsers.add_parser("status")
    args = parser.parse_args()
    ledger_path = Path(args.ledger)
    if args.command == "record":
        result = record_analysis(ledger_path, Path(args.analysis))
    elif args.command == "fill":
        result = mark_filled(ledger_path, args.record_id, args.price)
    elif args.command == "settle":
        result = settle(ledger_path, args.record_id, args.result, args.r_multiple)
    else:
        result = {"summary": journal_summary(_load_ledger(ledger_path))}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
