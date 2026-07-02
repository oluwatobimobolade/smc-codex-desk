from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="trade_readiness_prompt",
    version="1.0.0",
    purpose="Separate analysis from trade readiness and enforce strict refusal.",
    text="""Trade readiness rules:

Being directionally right is not enough.
A trade is valid only if location, liquidity, displacement, POI, entry, invalidation, target, and RR all align.

Use strict refusal states:
- THESIS_ONLY when there is context but no actionable setup model.
- WATCH_ONLY when there is a possible setup but no entry condition.
- WAIT_FOR_POI when price has not reached the meaningful POI.
- WAIT_FOR_RETRACE_TO_SUPPLY or WAIT_FOR_RETRACE_TO_DEMAND when continuation needs retrace.
- POI_TOUCHED_AWAIT_CONFIRMATION when price is at POI but 15M confirmation is missing.
- TRADE_PLAN_READY only when entry, structural invalidation, model-completion target, and RR >= 3 are all valid.
- VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY when the idea is directionally valid but RR is below 1:3.
- MISSED_TRADE_NO_CHASE when the move already left without a controlled entry.
- INDUCEMENT_RISK when the move may be bait rather than confirmation.
- INVALIDATED_REMAP when the setup premise is broken.
- REVIEW_REQUIRED when evidence cannot support a clean decision.

TRADE_PLAN_READY is forbidden when displacement_assessment is none/weak/review,
when structure_broken is false, or when no displacement evidence_object_ids are
available. A planned entry without a proven displacement is a watch, not a trade.
The final_thesis must not say WATCH_ONLY, wait for, no trade, or refusal language
while official_state is TRADE_PLAN_READY.

Never upgrade a watch state into a trade plan just to be useful.""",
)
