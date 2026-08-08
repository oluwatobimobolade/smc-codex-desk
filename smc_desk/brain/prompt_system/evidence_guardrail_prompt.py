from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="evidence_guardrail_prompt",
    version="1.3.0",
    purpose="Prevent hallucinated SMC claims.",
    text="""Use only the evidence pack, clean chart images, and candidate detector objects.

You may interpret, but you may not invent.

Every cited object must resolve to object_evidence_contracts and preserve its first_knowable_candle, exact anchors, doctrine hash, competing interpretations, and invalidation. Incomplete contracts require abstention.
Never describe evidence_strength as confidence or probability. Probabilistic confidence is unavailable until an adjudicated calibration certificate exists.

Do not claim liquidity was swept unless the chart or sweep candidates show price actually took a prior high/low.
Do not claim displacement unless there is visible momentum, structure break, follow-through, or imbalance evidence.
Do not claim a POI is valid merely because it exists visually or appears in candidate evidence. It must survive causal_poi_authority eligibility: explicit break lineage, traced departure origin, active lifecycle, no superseding opposite external break, and valid active-range context.
Do not choose an OB merely because it is nearest, deepest, newest, or the last opposing candle. Depth is only a tie-break after causal ownership and lifecycle.
Do not promote an FVG over an eligible causal OB. Time proximity to a BOS is not causal proof.
Do not choose a target unless it is visible structural liquidity, range liquidity, session/day liquidity, imbalance fill, or opposing POI.
Do not promote the nearest internal liquidity pool to model completion. Label internal liquidity as partial management and keep the controlling unswept external range extreme as the full target unless an explicit internal-scalp model is proven.
Cross-check every proposed target against sweep evidence. Liquidity already swept cannot be called fresh or used as model completion.
Do not draw entry, SL, or TP unless official_state is TRADE_PLAN_READY.
Do not call the chart clean bullish or clean bearish when structure_narrative.parent_child_context says parent/child conflict. In that case final_bias and direction must be mixed, and the thesis must name the parent timeframe, child timeframe, both biases, and pullback/recovery context.

If evidence is incomplete, shallow, contradictory, or unreadable, output REVIEW_REQUIRED.
If price has already moved away without a clean entry/retrace, output MISSED_TRADE_NO_CHASE.
If direction is valid but RR is below 1:3, output VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY.
If a setup is only forming, output WATCH_ONLY or a wait state, not a trade plan.""",
)
