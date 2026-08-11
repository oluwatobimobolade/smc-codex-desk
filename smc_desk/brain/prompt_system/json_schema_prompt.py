from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="json_schema_prompt",
    version="1.2.0",
    purpose="Force strict JSON output matching AISMCDecision.",
    text="""Return strict JSON only. No markdown. No prose outside JSON.

The JSON schema is ai_smc_trader_decision_v1 and must include:
official_state, setup_grade, direction, setup_model, bias_summary, active_range,
liquidity_story, displacement_assessment, active_poi, entry_plan, stop_loss_plan,
target_plan, rr_status, invalidation, annotation_plan, final_thesis.
annotation_plan_v2 is optional for backward compatibility but preferred for professional chart rendering.
context_exception_requests is optional and may contain only prequalified
context-only display requests from annotation_context_authority.

annotation_plan.reasoning_order must exactly equal required_reasoning_order.
annotation_plan_v2, when present, must use schema professional_smc_annotation_plan_v2 and objects with:
object_type, semantic_object_id, timeframe, label, reason, kind, price or price_low/price_high, start/end index or time, and evidence_object_ids.
structure_segment also requires structure_scope matching its source break. trade_box requires kind=trade plus entry_price, stop_price, and target_prices.

Semantic Grounding Requirement:
You must output semantic anchors before proposing any exact prices:
- entry_plan.entry_anchor (e.g. "15m_supply_origin_of_bearish_displacement")
- stop_loss_plan.stop_anchor (e.g. "above_sweep_high")
- target_plan.targets[].target_anchor (e.g. "previous_4h_structural_low")
- invalidation.invalidation_anchor (e.g. "acceptance_above_4h_range_high")
If not TRADE_PLAN_READY, entry_plan.entry_price/mapped_entry_price must be null, stop_loss_plan.stop_price/mapped_stop_price must be null,
target_plan.targets must be empty, and annotation_plan.show_trade_box must be false.

Precise Liquidity Status:
For each LiquidityReference in liquidity_story, you must output a precise status:
"fresh_untaken_liquidity", "prior_swept_liquidity", "re_sweep_objective", "range_low_reference", "range_high_reference", "below_low_external_liquidity", "above_high_external_liquidity", or "model_completion_reference".
Use evidence_object_ids wherever possible so the validator can check claims.""",
)
