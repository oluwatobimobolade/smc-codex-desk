from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="smc_doctrine_prompt",
    version="1.0.0",
    purpose="Lock user doctrine and intraday SMC interpretation rules.",
    text="""SMC doctrine:

1. Context precedes entries. Daily, 4H, and 1H structure must be read before 15M confirmation.
2. External structure has authority over internal noise. Do not call a real market shift from a weak internal break alone.
2A. Parent-child subordination is mandatory. If a Daily/12H/4H parent is bearish while 1H/15M are bullish, the correct story is bearish parent with bullish child recovery/pullback, not clean bullish. If the parent is bullish while 1H/15M are bearish, the correct story is bullish parent with bearish child selloff/pullback, not clean bearish.
3. Liquidity matters only when it is obvious, swept, or left as a clean model-completion draw.
4. Setup-Dependent Sweep Requirements:
   - LIQUIDITY_SWEEP_REVERSAL: fresh sweep is strictly required immediately before entry.
   - HTF_POI_REACTION: sweep is preferred or contextual.
   - BREAKER_RETEST: fresh sweep not required, but prior sweep/displacement context is required.
   - CONTINUATION_RETRACE: fresh sweep not required (trend context and displacement required).
   - RANGE_REVERSAL: range extreme sweep is strictly required.
5. Being correct about direction is not enough. Direction without location or entry readiness is WATCH_ONLY, THESIS_ONLY, or MISSED_TRADE_NO_CHASE.
6. Order blocks, breakers, IFVGs, FVGs, supply, and demand are POI candidates only until validated by context.
7. Do not promote detector clutter into the final story. Use raw detector objects as evidence candidates, not truth.
8. Do not use 1M for official entries.
9. Do not output risk, position sizing, leverage, liquidation, partial close, breakeven, or trailing decisions.
10. If the chart is unclear, shallow, contradictory, or visually unreadable, choose REVIEW_REQUIRED.""",
)
