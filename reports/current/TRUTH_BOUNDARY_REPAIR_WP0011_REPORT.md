# Truth Boundary Repair Report - WP-0011

## Summary

WP-0011 repaired the first failure introduced by the no-future-leakage work:
analysis now consistently treats `decision_time` as candle availability time,
while TradingView alignment still compares the last closed candle open and close
explicitly.

## Why This Matters

A 15m candle opened at `19:15` is not available at `19:15`. It becomes eligible
only at its close/availability time, `19:30`. The system now keeps that boundary
without causing live-shadow alignment to drift back one candle.

## Repairs

- Live shadow passes `last_closed_candle_close` into colleague runs.
- TradingView test manifests were corrected to match availability-time
  semantics.
- `StructureBreakObject` now has one canonical ontology shape with `break_type`.
- Canonical event ledger tests now validate against the same structure object
  used by perception snapshots.

## Evidence

- Work package: `governance/WORK_PACKAGES/WP-0011-TRUTH-BOUNDARY-REPAIR/`
- Focused tests: `27 passed in 1.88s`
- Full pytest: `381 passed in 23.87s`

## Boundary

This is a truth-boundary repair, not a strategy-promotion result. Prediction,
paper execution, live execution, and capital risk remain disabled.

