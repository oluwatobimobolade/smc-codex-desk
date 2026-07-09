"""Agent packet and response schemas for external AI agent handoff.

The packet is what the system exports for an external AI agent (Codex, Gemini
Antigravity, ChatGPT, Kimi, etc.) to review. The response is what the agent
returns after reasoning over the packet.

The system does NOT pretend the external agent is an internal automated LLM
call. It treats the agent as an external reasoning step that produces a
decision JSON, which the system then validates, grounds, and renders.
"""
from __future__ import annotations

from typing import Any, Literal

AgentPacketSchema = Literal["ai_smc_agent_packet_v1"]
AgentResponseSchema = Literal["ai_smc_agent_response_v1"]

AGENT_PACKET_FILES = [
    "00_READ_ME_FIRST.md",
    "01_prompt_bundle.md",
    "02_evidence_pack.json",
    "03_chart_manifest.json",
    "04_clean_1d_chart.png",
    "05_clean_4h_chart.png",
    "06_clean_1h_chart.png",
    "07_clean_15m_chart.png",
    "08_candidate_levels.json",
    "09_expected_output_schema.json",
    "10_guardrails.md",
    "run_manifest.json",
]

AGENT_RESPONSE_FILES = [
    "official_decision_candidate.json",
    "agent_reasoning_summary.md",
    "annotation_plan.json",
]


def make_agent_response_template() -> dict[str, Any]:
    """Return the expected response shape for an external AI agent."""
    return {
        "schema": "ai_smc_agent_response_v1",
        "agent_identity": {
            "agent_name": "",
            "agent_model": "",
            "agent_version": "",
            "review_started_at": "",
            "review_completed_at": "",
        },
        "packet_hash": "",
        "decision": {
            "schema": "ai_smc_trader_decision_v1",
            "symbol": "",
            "official_state": "WATCH_ONLY",
            "setup_grade": "C",
            "direction": "mixed",
            "setup_model": "",
            "bias_summary": {
                "daily": "mixed",
                "4h": "mixed",
                "1h": "mixed",
                "final_bias": "mixed",
                "evidence": [],
            },
            "active_range": {
                "timeframe": "4h",
                "high": None,
                "low": None,
                "equilibrium": None,
                "price_location": "unknown",
                "source": "protected_swing_pair",
                "evidence_object_ids": [],
                "evidence": [],
            },
            "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": ""},
            "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": ""},
            "active_poi": {"poi_id": None, "timeframe": None, "kind": None, "direction": "unknown", "price_low": None, "price_high": None, "freshness": None, "evidence_object_ids": [], "summary": ""},
            "entry_plan": {"entry_ready": False, "entry_timeframe": "15m", "refinement_timeframe": "5m", "entry_price": None, "entry_zone_low": None, "entry_zone_high": None, "signal_type": None, "required_confirmation": [], "evidence_object_ids": [], "entry_anchor": None, "mapped_entry_price": None, "summary": ""},
            "stop_loss_plan": {"stop_price": None, "structural_invalidation_price": None, "source": None, "buffer_notes": None, "evidence_object_ids": [], "stop_anchor": None, "mapped_stop_price": None, "summary": ""},
            "target_plan": {"targets": [], "model_completion_liquidity_id": None, "summary": ""},
            "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": ""},
            "invalidation": {"invalidation_price": None, "condition": "", "source": None, "evidence_object_ids": [], "invalidation_anchor": None, "mapped_invalidation_price": None},
            "annotation_plan": {"chart_template": "context_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": [
                "daily_context", "4h_context", "1h_context", "active_range", "premium_discount",
                "obvious_liquidity", "swept_liquidity", "displacement_quality", "active_poi",
                "entry_model", "entry_readiness", "structural_invalidation",
                "model_completion_liquidity_target", "rr_minimum_three", "final_state"
            ]},
            "annotation_plan_v2": {
                "schema": "professional_smc_annotation_plan_v2",
                "style": "professional_smc_sparse",
                "objects": [],
                "notes": [
                    "Use professional sparse SMC drawing objects when evidence supports them.",
                    "Omit objects that cannot be grounded in the formal graph or detector evidence.",
                ],
            },
            "self_review": {"active_range_check": "not_applicable", "poi_check": "not_applicable", "annotation_check": "not_applicable", "refusal_check": "not_applicable", "corrections_made": [], "remaining_uncertainties": []},
            "final_thesis": "",
        },
        "semantic_anchors": {
            "poi_anchor": None,
            "entry_anchor": None,
            "stop_anchor": None,
            "target_anchor": None,
            "invalidation_anchor": None,
        },
        "agent_reasoning_notes": "",
        "requested_more_context": [],
    }
