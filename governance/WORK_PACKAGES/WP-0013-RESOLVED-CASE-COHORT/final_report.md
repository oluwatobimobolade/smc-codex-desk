# WP-0013 Resolved Case Cohort - Final Report

Date: 2026-06-26

## Objective

Build a resolved-case cohort across BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, and
BNBUSDT so the Market Colleague can observe outcomes without claiming edge.

## Implementation

- Added `tools/build_resolved_case_cohort.py`.
- Added deterministic decision-time selection with enough future candles.
- Added request-level `outcome_horizon_bars` so case selection and outcome
  contracts use the same horizon.
- Added optional `render_charts=false` support for batch research packages.
- Built each package with legacy comparison disabled and paper/live execution
  disabled.
- Resolved each package through the existing future-candle resolver.

## Real Cohort

Output:

- `analysis_runs/resolved_case_cohort_wp0013_20260626/`

Counts:

- Total packages: `50`
- Resolved packages: `50`
- Unresolved packages: `0`
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT
- Cases per symbol: `10`

Decision actions:

- `NO_SETUP`: `50`

Cohort buckets:

- `no_trade_observation`: `50`
- `watch_observation`: `0`
- `disabled_signal_observation`: `0`
- `ambiguous_resolution`: `0`
- `unresolved`: `0`

## Honest Interpretation

This proves the resolved-cohort machinery. It does **not** prove a trading edge,
because all 50 cases were no-trade observations.

## Validation

- Focused tests included in
  `governance/WORK_PACKAGES/WP-0013-RESOLVED-CASE-COHORT/TEST_REPORT.json`.
