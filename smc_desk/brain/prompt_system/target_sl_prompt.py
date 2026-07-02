from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="target_sl_prompt",
    version="1.0.0",
    purpose="Require model-completion targets and structural invalidation.",
    text="""Stop loss and target doctrine:

Stop loss is structural invalidation. It is the market level that proves the setup idea wrong.
For bearish setups, invalidation must normally be above the protected high / supply high / sweep extreme.
For bullish setups, invalidation must normally be below the protected low / demand low / sweep extreme.
Do not use arbitrary tight stops.

Targets must be model-completion liquidity, not nearest tiny 15M levels.
Valid target types include:
- previous structural high/low;
- equal highs/equal lows;
- active dealing-range high/low;
- session/day liquidity;
- unfilled imbalance when it is the model objective;
- opposing HTF POI when it is the logical completion point.

If target is unclear, output WATCH_ONLY or REVIEW_REQUIRED.
If entry, invalidation, and model-completion target do not produce at least 1:3, output VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY instead of TRADE_PLAN_READY.""",
)
