"""Structured decision memory graph for the market colleague.

This is more than an append-only log: each decision is stored as a small graph
of market state, regime, perception, contradiction, decision, outcome, and
correction nodes. Outcome and correction can be filled later.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_decision_memory_record(
    *,
    symbol: str,
    decision_time: datetime,
    market_state_snapshot: dict[str, Any],
    regime: dict[str, Any] | None,
    fvg_state: dict[str, Any] | None,
    contradiction_result: dict[str, Any] | None,
    final_decision: dict[str, Any],
    outcome: str = "UNKNOWN",
    correction: dict[str, Any] | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    if decision_id is None:
        seed = json.dumps(
            {
                "symbol": symbol,
                "decision_time": decision_time.isoformat(),
                "final_action": final_decision.get("final_action") or final_decision.get("action"),
            },
            sort_keys=True,
        )
        decision_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

    nodes = [
        {
            "node_id": f"{decision_id}:market_state",
            "node_type": "market_state_snapshot",
            "payload": market_state_snapshot,
        },
        {
            "node_id": f"{decision_id}:regime",
            "node_type": "regime_classification",
            "payload": regime or {"status": "not_run"},
        },
        {
            "node_id": f"{decision_id}:fvg_state",
            "node_type": "fvg_state",
            "payload": fvg_state or {"status": "not_available"},
        },
        {
            "node_id": f"{decision_id}:contradiction",
            "node_type": "contradiction_result",
            "payload": contradiction_result or {"status": "not_run"},
        },
        {
            "node_id": f"{decision_id}:decision",
            "node_type": "final_decision",
            "payload": final_decision,
        },
        {
            "node_id": f"{decision_id}:outcome",
            "node_type": "later_outcome",
            "payload": {"outcome": outcome},
        },
        {
            "node_id": f"{decision_id}:correction",
            "node_type": "correction",
            "payload": correction or {"status": "none"},
        },
    ]
    edges = [
        {"source": nodes[0]["node_id"], "target": nodes[1]["node_id"], "edge_type": "CONTEXT_FOR"},
        {"source": nodes[1]["node_id"], "target": nodes[3]["node_id"], "edge_type": "QUALIFIES"},
        {"source": nodes[2]["node_id"], "target": nodes[3]["node_id"], "edge_type": "INFORMS"},
        {"source": nodes[3]["node_id"], "target": nodes[4]["node_id"], "edge_type": "RESOLVES_TO"},
        {"source": nodes[4]["node_id"], "target": nodes[5]["node_id"], "edge_type": "AWAITS"},
        {"source": nodes[5]["node_id"], "target": nodes[6]["node_id"], "edge_type": "MAY_CORRECT"},
    ]
    return {
        "schema_version": "decision_memory_graph.v1",
        "decision_id": decision_id,
        "symbol": symbol,
        "decision_time": decision_time.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nodes": nodes,
        "edges": edges,
    }


def append_decision_memory(path: str | Path, record: dict[str, Any]) -> None:
    memory_path = Path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    with memory_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def load_decision_memory(path: str | Path) -> list[dict[str, Any]]:
    memory_path = Path(path)
    if not memory_path.exists():
        return []
    records = []
    for line in memory_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def update_decision_outcome(
    path: str | Path,
    *,
    decision_id: str,
    outcome: str,
    correction: dict[str, Any] | None = None,
) -> bool:
    records = load_decision_memory(path)
    updated = False
    for record in records:
        if record.get("decision_id") != decision_id:
            continue
        for node in record.get("nodes", []):
            if node.get("node_type") == "later_outcome":
                node["payload"] = {"outcome": outcome}
                updated = True
            if correction is not None and node.get("node_type") == "correction":
                node["payload"] = correction
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
    if updated:
        memory_path = Path(path)
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(
            "\n".join(json.dumps(record, sort_keys=True, default=str) for record in records) + "\n",
            encoding="utf-8",
        )
    return updated


def supersede_prior_decisions(
    path: str | Path,
    *,
    symbol: str,
    current_decision_id: str,
    current_state: str,
    reason: str | None = None,
) -> list[str]:
    """Mark prior non-superseded memory records for the same symbol as superseded.

    A record is superseded when the communicated narrative state has changed
    (e.g. from a bullish watch to a bearish watch), ensuring downstream readers
    do not treat stale interpretations as current truth.
    """
    memory_path = Path(path)
    if not memory_path.exists():
        return []

    def _state_direction(state: str) -> str:
        state_l = str(state).lower()
        if "bullish" in state_l or "long" in state_l or "demand" in state_l:
            return "bullish"
        if "bearish" in state_l or "short" in state_l or "supply" in state_l:
            return "bearish"
        return "neutral"

    records = load_decision_memory(path)
    superseded_ids: list[str] = []
    current_direction = _state_direction(current_state)
    for record in records:
        if record.get("decision_id") == current_decision_id:
            continue
        if record.get("symbol") != symbol:
            continue
        if record.get("superseded_by"):
            continue
        prior_state = ""
        for node in record.get("nodes", []):
            if node.get("node_type") == "final_decision":
                prior_state = str(node.get("payload", {}).get("final_state") or node.get("payload", {}).get("final_action") or "")
                break
        prior_direction = _state_direction(prior_state)
        if prior_direction != "neutral" and prior_direction != current_direction:
            record["superseded_by"] = current_decision_id
            record["superseded_at"] = datetime.now(timezone.utc).isoformat()
            record["superseded_reason"] = reason or f"state changed from {prior_state} to {current_state}"
            superseded_ids.append(record["decision_id"])
    if superseded_ids:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(
            "\n".join(json.dumps(record, sort_keys=True, default=str) for record in records) + "\n",
            encoding="utf-8",
        )
    return superseded_ids


def state_direction(state: str) -> str:
    state_l = str(state).lower()
    if "bullish" in state_l or "long" in state_l or "demand" in state_l:
        return "bullish"
    if "bearish" in state_l or "short" in state_l or "supply" in state_l:
        return "bearish"
    return "neutral"


def write_active_truth_index(
    path: str | Path,
    *,
    symbol: str,
    current_decision_id: str,
    current_state: str,
    superseded_ids: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Write the current active interpretation index beside the memory log.

    Decision memory is append-only; this index is the one-record-per-symbol
    pointer that tells operators which interpretation is current and which
    prior records were explicitly superseded.
    """
    memory_path = Path(path)
    index_path = memory_path.parent / "active_truth_index.json"
    if index_path.exists():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        payload = {"schema_version": "active_truth_index.v1", "symbols": {}}
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload.setdefault("symbols", {})[symbol] = {
        "symbol": symbol,
        "active_decision_id": current_decision_id,
        "active_state": current_state,
        "active_direction": state_direction(current_state),
        "memory_file": memory_path.name,
        "superseded_prior_decision_ids": superseded_ids or [],
        "reason": reason or "new cognitive state became active truth",
        "updated_at": payload["updated_at"],
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return payload
