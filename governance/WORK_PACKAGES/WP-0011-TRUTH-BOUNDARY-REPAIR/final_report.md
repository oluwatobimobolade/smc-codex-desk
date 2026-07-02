# WP-0011 Final Report - Truth Boundary Repair

## Result

The truth-boundary repair is now integrated and validated. The system uses
closed-candle availability time consistently, and the live-shadow one-candle
alignment drift has been repaired.

## What Was Found

After the initial truth-boundary edits, the repo was red:

- Full pytest before repair: `4 failed, 377 passed`.
- TradingView alignment failed because colleague runs now treated
  `decision_time` as data availability time, while live-shadow still passed the
  last closed candle open time.
- Canonical event-ledger tests failed because structure-break objects existed in
  two incompatible shapes.

## What Changed

- `smc_desk/colleague/live_shadow.py` now reads
  `chart_state.timeframes.15m.last_closed_candle_close` as the colleague
  request `decision_time`.
- `tests/test_market_colleague_case.py` now uses a TradingView chart state
  consistent with availability-time semantics.
- `smc_desk/perception/ontology.py` now carries `break_type` on the canonical
  `StructureBreakObject`.
- `smc_desk/perception/structure.py` now uses that canonical
  `StructureBreakObject` instead of defining a competing subclass.
- `smc_desk/colleague/event_ledger.py` now handles ontology enum values
  correctly when emitting confirmed break events.

## Verified Behavior

Saved ETHUSDT live-shadow manifest rerun under current code:

- Requested decision time: `2026-06-25T19:30:00`
- Decision candle open: `2026-06-25T19:15:00`
- Decision available at: `2026-06-25T19:30:00`
- Alignment status: `PASS`
- Blocking failures: `0`

## Boundary

This work restores truth and reproducibility. It does not promote strategy
authority, predictive authority, paper execution, live execution, or market-edge
claims.

## Validation

- Focused repair suite: `27 passed in 1.88s`.
- Full pytest: `381 passed in 23.87s`.
- Compileall: passed.

