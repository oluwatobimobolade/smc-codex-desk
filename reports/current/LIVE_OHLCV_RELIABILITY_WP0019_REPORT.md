# Live OHLCV Reliability WP-0019 Report

Date: 2026-06-27

## Executive Verdict

Live Binance OHLCV acquisition is now reliable: retry/backoff protects transient failures,
route-health preflight blocks bad routes before fetch, and TradingView is permanently
excluded from market-truth authority.

## What Changed

- Added `smc_desk/data/live_route_health.py` — standalone route-health preflight
  (DNS → HTTPS → server time → klines → closed-candle validation).
- Added `execute_with_retry()` to `smc_desk/data/live_ohlcv.py` — 3 attempts max
  per route with 1s / 2s / 4s backoff.
- `acquire_verified_closed_ohlcv` now uses retry for each route.
- Confirmed `tradingview_used_as_market_truth: false` is universal in all manifests.
- Browser fallback navigates directly to Binance REST, not TradingView.

## Validation

- Focused live OHLCV suite: `21 passed in 42s`
- Full pytest: `496 passed, 1 skipped`
- Governance consistency: PASS
- Compilall: passed

## Boundary

No strategy edge, paper execution, live execution, or capital-risk authority.
This repair fixes live data plumbing only.
