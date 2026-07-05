from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="reasoning_order_prompt",
    version="1.0.0",
    purpose="Force the exact top-down SMC thinking sequence.",
    text="""Analyse in this exact order and keep annotation_plan.reasoning_order identical to the required_reasoning_order array:

1. Daily context: bias, active Daily range, and price location.
2. 4H context: alignment/conflict, active 4H dealing range, premium/discount/equilibrium.
3. 1H context: external structure, internal retracement, protected high/low, meaningful POI.
3A. Parent-child structure check: if Daily/12H/4H parent context conflicts with 1H/15M child structure, say both sides explicitly. Never flatten this into clean bullish or clean bearish.
4. Active range: define the dealing range that controls the current idea.
5. Premium/discount: state where price is in the active range.
6. Obvious liquidity: buy-side and sell-side pools visible before the decision.
7. Swept liquidity: what has actually been taken, if anything.
8. Displacement quality: momentum, structure break, follow-through, imbalance/FVG/OB/breaker/IFVG evidence.
9. Active POI: POI that caused displacement or is the valid return zone.
10. Entry model: HTF POI reaction, breaker retest, IFVG retest, continuation retrace, liquidity sweep reversal, or no model.
11. Entry readiness: trade-ready, watch-only, missed, bad RR, inducement risk, invalidated, or review.
12. Structural invalidation: the exact level that proves the trade idea wrong.
13. Model-completion liquidity target: prior high/low, equal highs/lows, range extreme, session/day liquidity, imbalance fill, or opposing HTF POI.
14. RR minimum 3: verify entry, invalidation, and target produce at least 1:3.
15. Final state: choose exactly one supported official_state.""",
)
