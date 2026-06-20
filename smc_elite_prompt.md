# SMC Elite Analyst — Quick Prompt

Analyze this chart using the SMC Elite Strategy.

**Source playbook:** `/Users/tobimobolade/smc-codex-desk/strategies/smc/SMC_ELITE_STRATEGY.md`

## Instructions

1. Open TradingView and load the chart for the instrument I specify.
2. Capture screenshots at **Daily → 4H → 1H → 15m**.
3. Determine the **bias** from Daily/4H structure.
4. Locate the **external liquidity target**.
5. Identify a valid **Point of Interest** on 1H (order block, FVG, or breaker).
6. Wait for / confirm on 15m:
   - Liquidity sweep / inducement
   - Displacement in trade direction
   - CHoCH / BOS
7. If OHLCV is available, run the deterministic engine and use its checklist as a guardrail.
8. Check brief **news/fundamental context**.
9. Output a complete trade plan:
   - Direction
   - Entry zone
   - Entry type (aggressive / confirmation / no trade)
   - Stop loss
   - Take profit(s)
   - Risk/Reward
   - Setup grade (A+ / A / B / C)
   - Risk %
   - Invalidation
10. Save the analysis to the journal:
   `/Users/tobimobolade/smc-codex-desk/journal/YYYY-MM-DD/<PAIR>_<HHMM>_<GRADE>.md`

## Constraints

- Only take A+ and A setups.
- Minimum R:R is 1:3.
- 1% risk default; 2% only on A+ setups.
- No trades against Daily/4H bias without exceptional counter-trend evidence.
- If the setup is weak or unclear, the correct answer is **no trade**.
- Never promise good trades or guaranteed profitability.
- Wick-only breaks do not count as BOS/CHoCH; require candle-body displacement.
- Fully mitigated POIs are invalid.

## Output Format

```markdown
# SMC Elite Analysis — [PAIR] [DATE]

## Bias
...

## Liquidity Target
...

## POI
...

## 15m Confirmation
...

## Trade Plan
- Direction: ...
- Entry Zone: ...
- Entry Type: ...
- Stop Loss: ...
- Take Profit 1: ...
- Take Profit 2: ...
- Risk/Reward: ...
- Setup Grade: ...
- Risk: ...

## Invalidation
...

## News Note
...

## Verdict
Execute / Watch / Pass
```

Proceed with the analysis.
