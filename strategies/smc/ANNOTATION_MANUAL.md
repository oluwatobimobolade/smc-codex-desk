# SMC Perception Annotation Manual

This manual provides strict definitions for labelling the 20-chart definition set. Adherence to these definitions is required for both human annotators and the V2 Perception Engine.

## General Rules
1. **No Future Leakage**: Annotate objects based strictly on information available at the `decision_time` of the chart.
2. **Precision**: All prices must be exact to the instrument's tick size.
3. **Wicks vs Bodies**: Structural breaks (BOS/CHoCH) require body closure confirmation. Swings are defined by wick highs/lows.

## 1. Swings (Local, Internal, External)
A swing is a prominent peak or trough.
- **Swing High**: A candle whose high is strictly greater than the highs of `N` bars to its left and right.
- **Swing Low**: A candle whose low is strictly less than the lows of `N` bars to its left and right.
- **Confirmation**: A swing is only confirmed *after* the `N` right-side bars have closed.
- **Scales**:
  - `local`: `N=1` (3-bar fractal)
  - `internal`: `N=3`
  - `external`: `N=5`

## 2. Protected Structure
- **Protected High**: The highest point that originated a move which broke a confirmed swing low.
- **Protected Low**: The lowest point that originated a move which broke a confirmed swing high.
- A protected point is invalidated only when price breaks and closes beyond it.

## 3. Break of Structure (BOS)
A BOS occurs when price breaks a protected high/low in the direction of the prevailing trend.
- **Trigger**: Price wick crosses the protected level.
- **Confirmation**: A candle body closes beyond the protected level.
- **Direction**: Must continue the current structural direction.

## 4. Change of Character (CHoCH)
A CHoCH occurs when price breaks a protected high/low *against* the prevailing trend.
- **Trigger**: Price wick crosses the protected level.
- **Confirmation**: A candle body closes beyond the protected level.
- **Significance**: Indicates a potential shift in structural direction.

## 5. Fair Value Gaps (FVG)
A 3-candle imbalance.
- **Bullish FVG**: `candle[1].high < candle[3].low`. The gap is the zone between these two prices.
- **Bearish FVG**: `candle[1].low > candle[3].high`. The gap is the zone between these two prices.
- **Mitigation**: An FVG is partially mitigated when price enters the zone, and fully mitigated (invalidated) when price crosses the origin boundary.

## Disagreement Resolution
If two human reviewers disagree on a label based on this manual, the manual is ambiguous. Do not proceed to algorithm design until the manual is clarified to produce 100% agreement on the definition set.
