# SMC House Rules

This is the exact playbook the engine should follow. The deeper structure doctrine lives in `STRUCTURE_DOCTRINE.md`.

## Structure

### HTF Bias Consensus

- 1H and 4H must agree before their bias is fed into the execution engine.
- Daily must agree or be neutral.
- If Daily actively opposes the 1H/4H direction, the system stands aside or downgrades to research-only.
- A lone 1H signal cannot drive a trade.

### Valid Swing BOS

- BOS is continuation, not reversal.
- Bullish BOS: candle-body close through a prior swing high with displacement after bullish structure is active.
- Bearish BOS: candle-body close through a prior swing low with displacement after bearish structure is active.
- Wick-only breaks do not count as BOS.
- BOS should be read on the swing/external structure layer for bias.

### Valid Swing CHoCH

- CHoCH is reversal evidence only when the protected swing level breaks.
- In a bearish leg, bullish CHoCH requires a close above the protected swing high.
- In a bullish leg, bearish CHoCH requires a close below the protected swing low.
- Breaking an internal lower high or higher low is internal CHoCH only; it cannot flip HTF bias.
- Displacement is required.

### Internal Structure

- Internal structure is for entries, not bias.
- Internal CHoCH can confirm that execution flow changed after a sweep and displacement.
- Internal CHoCH is useful on 5m/15m when price is already at a valid POI.
- If internal structure conflicts with swing structure, the system must downgrade to `Watch` or `Pass`.

## Order Blocks

- Use order blocks as POIs, not standalone entries.
- Prefer the last opposite candle before displacement from a meaningful swing origin.
- Fresh is better than partial; fully mitigated is invalid by default.
- Swing order blocks drive POI selection; internal order blocks can help refine entries.
- Rank by freshness, confluence, displacement strength, and premium/discount location.
- Do not blindly prefer the nearest OB. A shallow OB/FVG sitting in front of a deeper same-leg OB can be inducement/liquidity. The deeper origin OB gets reaction priority when it is still protected-range-valid.

## Fair Value Gaps

- FVGs are three-candle imbalances.
- Ignore tiny gaps inside consolidation unless they overlap a stronger POI.
- Fresh FVGs are preferred. Partially mitigated FVGs are research-only unless explicitly allowed.
- FVG alignment matters: bearish FVGs in premium for sells, bullish FVGs in discount for buys.
- FVGs are secondary POIs by default. They may react, but an FVG-only pocket must not outrank a valid deeper OB unless there is no better OB or fresh confirmation makes the FVG the active reaction zone.

## Liquidity

- Equal highs/lows, prior swing highs/lows, and session extremes are liquidity pools.
- A wick through liquidity is a sweep/grab, not a structure break by itself.
- A useful sweep must be followed by displacement and internal or swing structure confirmation.
- External liquidity is used for main targets. Internal liquidity can be used for TP1 or entry inducement.
- Inducement often sits just before the true POI. The engine should mark shallow/front POIs as inducement risk when a deeper protected-range-valid OB sits behind them.

## Dealing Range

- Anchor the range to meaningful swing highs and lows, not random internal noise.
- Buys should originate in discount unless the setup is exceptional.
- Sells should originate in premium unless the setup is exceptional.
- Reset the range only after a valid swing BOS/CHoCH or a clearly new dealing range forms.

## Entry Logic

- Required: HTF bias, valid POI, sweep/inducement, displacement, structure confirmation, and logical R:R.
- Aggressive limit entries require an A+ POI and complete context.
- Confirmation entries require price at POI plus rejection/displacement and internal CHoCH/BOS.
- Structural invalidation sits beyond the level that proves the idea wrong.
- Execution SL must include the configured volatility/structural buffer.
- If the logical SL makes R:R worse than the floor, no trade.

## Validation

Every rule must be specific enough that two analysts would classify the same chart the same way most of the time.
