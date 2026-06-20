# SMC Structure Doctrine

**Purpose:** prevent the engine from promoting lower-timeframe/internal structure into a higher-timeframe bias change.

SMC is a community trading language, not a formal market microstructure standard. This repo therefore uses an explicit house doctrine. The goal is not to label every possible chart idea. The goal is to make two analysts, and the engine, classify the same chart the same way most of the time.

## First Cause Of The BTC Error

The first cause was a taxonomy failure.

The engine had one structure detector and one meaning for `CHoCH`. It treated a break of an active local lower high as if it were a higher-timeframe change of character. On BTCUSD, the local/internal lower high around `62,856` broke, but the protected swing high around `64,364-64,382` did not. That should have been an internal bullish shift at most, not a 1H bullish CHoCH and not a bias flip.

The fix is not "be more confident." The fix is to separate structure into two layers:

```text
Higher-timeframe narrative
Daily / 4H / 1H swing structure
Protected high/low must break by candle close with displacement
Used for: bias, invalidation, major liquidity, swing POIs

Lower-timeframe execution
15m / 5m internal structure
Internal high/low can break after sweep + displacement
Used for: entry confirmation only, never HTF bias by itself
```

## Structure Layers

### Swing / External Structure

Swing or external structure is the layer that carries the market narrative.
The word `swing` is relative to the timeframe being analyzed: 15m swing structure is still execution-timeframe structure, while 1H / 4H / 1D swing structure drives HTF bias.

Use it for:

- Directional bias.
- Real BOS/CHoCH that changes the working story.
- Structural invalidation.
- Major liquidity targets.
- Swing order blocks and breaker/mitigation areas.

Rules:

- In a bearish leg, bullish CHoCH requires a candle-body close through the protected swing high.
- In a bullish leg, bearish CHoCH requires a candle-body close through the protected swing low.
- A wick through a level is not BOS or CHoCH. It may be a liquidity sweep/grab.
- Displacement is required. A slow drift through a level is weaker and should not become an entry signal.
- After a valid CHoCH, same-direction breaks become BOS/continuation events.

### Internal Structure

Internal structure is the lower-order layer inside the larger swing.

Use it for:

- Entry timing after price reaches a POI.
- Confirmation after liquidity is swept.
- Reading the shift from delivery against the trade into delivery with the trade.
- Fine-tuning execution invalidation.

Rules:

- Internal CHoCH can break a local/internal high or low.
- Internal CHoCH must not flip Daily / 4H / 1H bias by itself.
- Internal confirmation is valid only when it lines up with the higher-timeframe idea: HTF bias, POI, liquidity sweep, and displacement.
- If internal structure conflicts with swing structure, the output is `Watch` or `Pass`, not blind reversal.

## Liquidity, Wicks, And Breaks

Liquidity is evidence, not a trade by itself.

- Equal highs/equal lows identify likely liquidity pools.
- A wick above highs or below lows can be a sweep/grab.
- A sweep becomes useful only when followed by displacement and a structure shift in the intended direction.
- Wick-only breaks do not change structure. They can mark liquidity taken.

## POIs: OB, FVG, Breaker

An order block, FVG, or breaker is a point of interest, not an entry alone.

- Order blocks should originate near a meaningful swing and be followed by displacement.
- FVGs are three-candle imbalances. They are useful when fresh, significant, and aligned with the trade idea.
- Breakers are former OB/support/resistance areas that got broken and can act as the opposite side on retest.
- POIs are ranked after structure and liquidity. A pretty FVG against bias is still weak.

## Engine Mapping

The code now enforces this doctrine:

- `StructureEvent.structure_scope` labels events as `swing`, `internal`, `external`, or `unknown`.
- `detect_structure_events(..., structure_scope="swing")` requires protected highs/lows for opposite-direction CHoCH.
- `detect_structure_events(..., structure_scope="internal")` can confirm an internal CHoCH through a local high/low.
- `RuleConfig.internal_pivot_window` and `RuleConfig.swing_pivot_window` separate internal sensitivity from swing sensitivity.
- MTF bias uses only `swing`, `external`, or legacy `unknown` structure events.
- Trade confirmation can use internal events, but bias and order-block construction remain anchored to swing structure.

## BTC Case Rule

For the BTCUSD chart that caused the issue:

- `62,856` was an internal/local lower high.
- `64,364-64,382` was the protected swing high area.
- Breaking `62,856` could support internal confirmation.
- Failing to close above `64,364-64,382` means no 1H bullish CHoCH.
- The correct higher-timeframe read was still bearish or unresolved until the protected high broke.

## Sources Used To Calibrate This Doctrine

- LuxAlgo Price Action Concepts: [Market Structure](https://docs.luxalgo.com/docs/algos/price-action-concepts/market-structures)
- LuxAlgo Price Action Concepts: [Liquidity Concepts](https://docs.luxalgo.com/docs/algos/price-action-concepts/liquidity)
- LuxAlgo Price Action Concepts: [Imbalance Concepts](https://docs.luxalgo.com/docs/algos/price-action-concepts/imbalances)
- LuxAlgo Price Action Concepts: [Volumetric Order Blocks](https://docs.luxalgo.com/docs/algos/price-action-concepts/order-blocks)
- TradingView open-source indicator page: [Smart Money Concepts (SMC) LuxAlgo](https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/)
