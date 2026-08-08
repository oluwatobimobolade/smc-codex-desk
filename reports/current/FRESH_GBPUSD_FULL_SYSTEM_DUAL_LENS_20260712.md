# Fresh GBPUSD Full-System Dual-Lens Run

Date: 2026-07-12

## Result

- Final run: `analysis_runs/FRESH_GBPUSD_FULL_SYSTEM_20260712_163004/FINAL_GRAPH_AUTHORITY/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_164144/GBPUSD`.
- Data: fresh Yahoo `GBPUSD=X` closed OHLCV across 15m/1H/4H/Daily.
- Visual audit: Kimi WebBridge TradingView `OANDA:GBPUSD` 1D/4H/1H/15m.
- Official state: `WATCH_ONLY`.
- Graph invariants: `PASS`.
- Causal POI authority: `UNRESOLVED`.
- Entry, SL, TP, RR, trade box, paper execution, and live execution: none.

## Structural Read

- Daily formal structure is unknown.
- 4H external structure is bullish.
- 1H external structure is bullish with a bearish internal pullback.
- 15m execution structure is bearish after a confirmed BOS through 1.339908.
- Controlling range: 1.338151-1.345153; current location is discount.
- Reaction candidate: 1.338652-1.340034, explicitly not a certified causal POI.

## Integrity Repair During Run

The first run exposed a graph-authority leak: raw Daily candle drift was printed
as `Daily bullish` even though the formal graph said `unknown`. The repair now:

- makes formal-graph timeframe nodes authoritative over narrative labels;
- preserves authoritative `unknown` instead of filling it with raw drift;
- prevents the live display/vote helpers from rehydrating raw bias afterward;
- retains opposing internal pullback wording beneath the external structure;
- adds regression tests for both authority boundaries.

Focused validation: 29 tests passed. Full repository validation: 957 passed,
1 skipped; compileall passed. The corrected full rerun validated with no hard
issues and now prints `Daily=unknown`.

## Honest Boundary

This run is weekend/market-closed analysis. Yahoo and OANDA differ by about 3.9
pips at their displayed cutoffs, so exact cross-provider price agreement is not
claimed. The charts agree on the structure story. No predictive or execution
authority was created.
