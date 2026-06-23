# State-Machine Research Decision

## Bottom Line

The narrative-state-machine idea is worth testing. It is not yet evidence of
an edge, and it must not replace the current engine or alter default rules
until it clears a separate no-lookahead validation branch.

The current frozen research geometry remains `NO_GO` after costs. A better
story about a setup is useful only if it later produces a better, reproducible
outcome distribution.

## Accepted Now

1. **Stateful sequence logging:** HTF-aligned sweep -> displacement -> a POI
   frozen on the displacement candle -> POI revisit -> confirmation.
2. **Explicit terminal states:** `EXPIRED` and `INVALIDATED` are recorded
   before an attempt returns to `WATCHING`.
3. **Closed-candle, no-lookahead replay:** every transition must be explainable
   from data available at that bar.
4. **Case provenance:** state transitions and future human disagreements belong
   in case artifacts, not in undocumented chat memory.

## Rejected or Deferred

1. **Replacing the snapshot engine now:** rejected. The baseline remains a
   comparator and a safety fallback.
2. **Calling displacement “poison”:** rejected. BTC/ETH and SOL calibration
   signs differ, so the existing evidence is not causal or universal.
3. **Changing pivots, FVG thresholds, sessions, and defaults together:**
   rejected. That would make an eventual result uninterpretable.
4. **Wick-volume absorption from OHLCV:** rejected as a claim. A candle has one
   aggregate volume value; multiplying it by wick proportion is only a proxy,
   not intrabar volume or institutional order-flow evidence.
5. **Fast retrace = institutional / slow retrace = retail:** deferred as a
   measurable feature, not a causal explanation. It must be specified in ATR
   distance and elapsed bars, then tested independently.
6. **Hard UTC session rules:** deferred. The cited PF `0.809` is below one,
   and fixed UTC London/New York windows mishandle daylight saving time.
7. **Human override to Execute:** rejected. Human annotations may create a
   disagreement case or a paper observation, never an unvalidated trade.

## Corrections to the Proposed Validation Plan

- Use the canonical Binance USD-M futures symbols: `BTCUSDT`, `ETHUSDT`, not
  legacy spot `BTCUSD`, `ETHUSD`.
- Separate transition instrumentation from entry research. The first phase has
  no profit-factor target because it emits no trades.
- Pre-register a momentum-entry branch only after the exact signatures and
  their calculation windows exist in code.
- Evaluate selected rules on a final untouched period at 10 bps, per pair and
  in aggregate, with outcome count, average R, PF, confidence interval, and
  chronological-fold gates. PF alone is insufficient.
- Keep research geometries, Watches, paper observations, and literal Execute
  performance as separate populations.

## Current State

`smc_desk/state_machine.py` and `tools/replay_setup_states.py` are
observability-only. They produce a setup narrative and terminal reasons, but
cannot create a `TradePlan`, fill, or live order.

The next decision is empirical: run representative multi-period transition
replays, inspect how often valid sequences reach `POI_ACTIVE`, then decide
whether a separately defined momentum-signature branch deserves pre-registration.
