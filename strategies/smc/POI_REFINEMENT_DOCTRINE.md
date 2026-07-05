# POI Refinement Doctrine - OB, FVG, and Inducement

## Why This Exists

The system made a real SMC mistake on SUIUSDT: it treated `0.7320-0.7348` like the order block when that zone was actually an FVG / imbalance. The actual nearby OB was higher, and the cleaner deeper OB was lower.

This document locks the correction:

- FVG is not OB.
- Nearest zone is not always best POI.
- A shallow OB/FVG in front of a deeper OB can be inducement.
- The deeper origin OB is often the cleaner reaction area, but still needs confirmation.

## Doctrine

### 1. Order Block Authority

A valid order block is the source candle or base before displacement and structure break. It is stronger when it has:

- Clear displacement away from it.
- A visible imbalance/FVG created by the displacement.
- BOS/CHoCH confirmation.
- Fresh or only lightly mitigated status.
- Correct premium/discount location.

### 2. FVG Authority

An FVG is an imbalance, not an order block. It can attract price and can produce reactions, but it should be lower authority than a valid OB unless:

- It overlaps a valid OB.
- It sits inside a higher-timeframe POI.
- Price reaches it and prints fresh rejection/displacement.

### 3. Inducement in Front of POI

Inducement is the visible liquidity or tempting minor zone in front of the more meaningful POI. The system must ask:

1. Is this nearest zone a real reaction area?
2. Or is it the bait that draws price into the deeper origin OB?

For bullish models:

- A shallow demand/FVG above a deeper valid demand can be inducement.
- The deeper lower OB gets reaction priority.

For bearish models:

- A shallow supply/FVG below a deeper valid supply can be inducement.
- The deeper higher OB gets reaction priority.

### 4. Entry Refinement Rule

The engine may map all zones, but entry readiness should prefer:

1. Deeper protected-range-valid OB.
2. OB + FVG overlap.
3. FVG only, with stronger confirmation required.
4. Shallow front POI only if price decisively reacts there and invalidates the deeper-retrace thesis.

This does not create automatic trades. Sweep, displacement, confirmation, stop logic, target logic, and R:R still gate execution.

## Implementation Notes

Implemented in:

- `smc_desk/perception/poi_lifecycle.py`
- `smc_desk/engine.py`

New ranking roles include:

- `front_inducement_risk`
- `deeper_order_block_reaction_candidate`
- `fvg_path_to_deeper_order_block`
- `fvg_order_block_overlap_confluence`
- `fvg_secondary_reaction_candidate`

## Research Sources Used

- 3Commas inducement note: inducement is commonly the liquidity trap before the true POI/order block.
- LiquidityFinder order-block anatomy: valid OBs need displacement, imbalance, BOS, and the return/retest.
- TradeZella ICT concepts: FVG is imbalance/rebalancing, not the same object as an OB.
- Trade The Pool SMC terminology: SMC uses structure, liquidity grabs, OBs, FVGs, and inducement as separate concepts.

These sources are educational, not proof of edge. The doctrine is now testable inside our own backtests and case reviews.
