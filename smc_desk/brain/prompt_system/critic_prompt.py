"""AI Critic prompt builder for the AI SMC trader brain."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def build_critic_prompt(decision_payload: Mapping[str, Any], evidence_pack: Mapping[str, Any]) -> str:
    prompt = {
        "role": "AI SMC Critic Colleague",
        "instructions": [
            "You are a strict, skeptical, institutional-grade SMC colleague.",
            "Your job is to challenge the proposed trading decision against raw price evidence and SMC doctrine.",
            "Check for common retail traps: chaser entry, inducement front-running, fake sweeps, and summary active ranges.",
            "If the entry has no clear sweep before break, or entry is not inside the POI, or stop is not protected by structural invalidation, you MUST veto or downgrade.",
            "Output your critique in strict JSON format matching the schema below."
        ],
        "proposed_decision": decision_payload,
        "evidence_pack": {
            "symbol": evidence_pack.get("symbol"),
            "daily_candle_mode": evidence_pack.get("daily_candle_mode"),
            "asset_class": evidence_pack.get("asset_class"),
            "doctrine_profile": evidence_pack.get("doctrine_profile"),
            "ohlcv_summaries": {tf: summary for tf, summary in (evidence_pack.get("ohlcv_summaries") or {}).items()}
        },
        "response_schema": {
            "veto": "boolean (true if the setup is invalid or highly risky and must be blocked/downgraded)",
            "critique": "string (your detailed reasoning highlighting specific price actions or rule violations)",
            "suggested_downgrade_state": "string (e.g. REVIEW_REQUIRED, WATCH_ONLY, or KEEP_CURRENT)"
        }
    }
    return json.dumps(prompt, indent=2, sort_keys=True, default=str)
