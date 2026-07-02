# WP-0010 Final Report - Outcome Resolution

## Result

Pending outcome contracts can now be resolved from future 15m OHLCV candles.
The resolver explicitly separates market observation from performance claims.

## What Changed

- Added `smc_desk/colleague/outcome_resolution.py`.
- Added `tools/resolve_colleague_outcome.py`.
- Added regression coverage in `tests/test_colleague_outcome_resolution.py`.

## Real Historical Evidence

Run:
`analysis_runs/BTCUSDT_20260618_1200_outcome_resolution_smoke/`

Resolution:
`analysis_runs/BTCUSDT_20260618_1200_outcome_resolution_smoke/outcome/resolution.json`

Observed:

- Decision action: `NO_SETUP`.
- Future candles available: `96`.
- Future candles required: `96`.
- Resolution status: `resolved_no_setup_observation`.
- Market edge claimed: `false`.
- Paper/live execution enabled: `false`.

The resolver records watched scenario outcomes but marks no-trade cases as
observations, not wins or losses.

## Boundary

This is not a backtest engine and not a win-rate report. It is the truth
accounting layer needed before outcome cohorts and walk-forward tests can be
trusted.

## Validation

- Focused resolver tests: covered target first, invalidation first, same-candle
  ambiguity, incomplete future windows, no-setup observation handling, and CLI
  file writing.
- Focused colleague regression: `13 passed in 1.25s`.
- Full pytest: `361 passed in 26.08s`.
