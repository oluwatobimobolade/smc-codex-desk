from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd


def build_event_ledger_records(
    *,
    perception_by_tf: dict[str, dict[str, Any]],
    mtf_graph: dict[str, Any],
    scenario_tree: dict[str, Any],
    alignment_report: dict[str, Any],
    decision: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for tf, payload in perception_by_tf.items():
        for obj in payload.get("structure_breaks", []):
            records.append(
                {
                    "event_type": "perception.structure_break",
                    "timeframe": tf,
                    "object_id": obj.get("object_id"),
                    "direction": obj.get("direction"),
                    "status": obj.get("confirmation_status"),
                    "event_time": obj.get("confirmed_at") or obj.get("candidate_at"),
                }
            )
        for obj in payload.get("fvgs", []):
            if obj.get("confirmation_status") == "confirmed" and obj.get("mitigation_status") != "full":
                records.append(
                    {
                        "event_type": "perception.active_fvg",
                        "timeframe": tf,
                        "object_id": obj.get("object_id"),
                        "direction": obj.get("direction"),
                        "status": obj.get("mitigation_status"),
                        "event_time": obj.get("confirmed_at"),
                    }
                )
    for node in mtf_graph.get("nodes", []):
        if str(node.get("object_type", "")).endswith("candidate") or node.get("object_type") in {"order_block_proxy", "selected_execution_poi"}:
            records.append(
                {
                    "event_type": f"semantic.{node.get('object_type')}",
                    "timeframe": node.get("timeframe"),
                    "object_id": node.get("node_id"),
                    "authority": node.get("authority"),
                    "event_time": node.get("confirmed_at"),
                }
            )
    scenario = (scenario_tree.get("scenarios") or [{}])[0]
    records.append(
        {
            "event_type": "scenario.state",
            "scenario_id": scenario.get("scenario_id"),
            "setup_stage": scenario.get("setup_stage"),
            "action_state": scenario.get("current_action_state"),
            "next_best_action": scenario.get("next_best_action"),
        }
    )
    records.append({"event_type": "external.alignment", "status": alignment_report.get("status"), "passed": alignment_report.get("passed")})
    records.append({"event_type": "decision.final", "action": decision.get("action"), "capital_risk": decision.get("capital_risk")})
    return records


def event_ledger_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, default=str) for record in records) + "\n"


def build_outcome_contract(
    *,
    symbol: str,
    decision_available_at: pd.Timestamp,
    scenario_tree: dict[str, Any],
    decision: dict[str, Any],
    horizon_bars: int = 96,
) -> dict[str, Any]:
    due_at = pd.Timestamp(decision_available_at) + pd.Timedelta(minutes=15 * horizon_bars)
    return {
        "outcome_contract_version": "0.1",
        "status": "pending_observation",
        "symbol": symbol,
        "decision_available_at": pd.Timestamp(decision_available_at).isoformat(),
        "resolution_due_at": due_at.isoformat(),
        "horizon_bars_15m": horizon_bars,
        "decision_action": decision.get("action"),
        "capital_risk": 0,
        "tracked_scenarios": [
            {
                "scenario_id": scenario.get("scenario_id"),
                "direction": scenario.get("direction"),
                "setup_stage": scenario.get("setup_stage"),
                "terminal_conditions": {
                    "target_touch": scenario.get("target_definition", {}).get("targets", []),
                    "invalidation": scenario.get("invalidation_events", []),
                    "expiry": scenario.get("expiry_rule"),
                },
            }
            for scenario in scenario_tree.get("scenarios", [])
        ],
        "resolution_policy": "No performance claim until outcome/resolution.json is filled from future candles.",
        "created_at": datetime.now().astimezone().isoformat(),
    }


def unresolved_resolution_stub(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "unresolved",
        "outcome_contract_version": contract["outcome_contract_version"],
        "symbol": contract["symbol"],
        "decision_action": contract["decision_action"],
        "resolution_due_at": contract["resolution_due_at"],
        "market_edge_claimed": False,
    }
