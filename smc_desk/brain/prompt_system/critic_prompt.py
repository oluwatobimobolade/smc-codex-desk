"""AI Critic prompt builder for the AI SMC trader brain."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def build_critic_prompt(decision_payload: Mapping[str, Any], evidence_pack: Mapping[str, Any]) -> str:
    from smc_desk.perception.formal_structure_graph import graph_to_dict_string

    graph = evidence_pack.get("formal_structure_graph") or {}
    graph_serialized = graph_to_dict_string(graph) if graph else "{}"

    prompt = {
        "role": "AI SMC Graph Challenger (Critic)",
        "instructions": [
            "You are a strict, skeptical, institutional-grade SMC colleague acting as a GRAPH CHALLENGER.",
            "Your job is to challenge the proposed trading decision against the FORMAL STRUCTURE GRAPH and raw price evidence.",
            "You can ONLY downgrade or veto. You can NEVER promote a decision to a higher state.",
            "Read the formal_structure_graph FIRST, before any candle or OHLC summary evidence.",
            "If the graph says PARENT_CHILD_CONFLICT, the decision direction MUST be mixed. Veto any clean bullish/bearish label.",
            "If the graph invariants are not PASS, the decision MUST NOT be TRADE_PLAN_READY. Veto or downgrade.",
            "If the graph says trade_promotion_blocked, veto any TRADE_PLAN_READY state.",
            "Check for common retail traps: chaser entry, inducement front-running, fake sweeps, and summary active ranges.",
            "If the entry has no clear sweep before break, or entry is not inside the POI, or stop is not protected by structural invalidation, you MUST veto or downgrade.",
            "Output your critique in strict JSON format matching the schema below."
        ],
        "formal_structure_graph": graph_serialized,
        "proposed_decision": decision_payload,
        "evidence_pack": {
            "symbol": evidence_pack.get("symbol"),
            "daily_candle_mode": evidence_pack.get("daily_candle_mode"),
            "asset_class": evidence_pack.get("asset_class"),
            "doctrine_profile": evidence_pack.get("doctrine_profile"),
            "ohlcv_summaries": {tf: summary for tf, summary in (evidence_pack.get("ohlcv_summaries") or {}).items()}
        },
        "response_schema": {
            "veto": "boolean (true if the setup is invalid, contradicts the graph, or is highly risky and must be blocked/downgraded)",
            "critique": "string (your detailed reasoning highlighting specific graph violations, price actions, or rule violations)",
            "suggested_downgrade_state": "string (e.g. REVIEW_REQUIRED, WATCH_ONLY, THESIS_ONLY, or KEEP_CURRENT — never promote)"
        }
    }
    return json.dumps(prompt, indent=2, sort_keys=True, default=str)
