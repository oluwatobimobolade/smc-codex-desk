# WP-0019 Live OHLCV Reliability Repair - Final Report

Date: 2026-06-27

## Objective

BTCUSDT live-shadow must either acquire verified closed Binance candles or cleanly write
NO_VALID_LIVE_TRADE with route diagnostics. It must never hang, timeout silently, or pretend
visual data is market truth.

## What Was Done

### 1. TradingView removed from canonical OHLCV market-truth routing

`smc_desk/data/live_ohlcv.py` already excluded TradingView before WP-0019. The live-shadow
pipeline was audited to confirm `tradingview_used_as_market_truth` is always `False` in both
success and failure manifests. Browser fallback navigates directly to Binance REST endpoints,
not through TradingView pages. TradingView remains visual alignment and screenshot review only.

### 2. Route-health preflight module added

`smc_desk/data/live_route_health.py` provides:

- `check_dns(host)` — DNS resolution check
- `check_https(base_url)` — HTTPS/fapi/v1/ping reachability
- `check_server_time(base_url)` — `/fapi/v1/time` endpoint
- `check_klines(base_url, symbol, interval)` — `/fapi/v1/klines` endpoint
- `check_closed_candle_validation(symbol, interval, rows, server_time_ms)` — closed-candle batch validation
- `run_route_health_preflight(symbol, interval)` — full ordered preflight (DNS → HTTPS → server time → klines → closed candle)

Stage output format:

```json
{
  "route": "binance_usdm_rest",
  "overall": "READY",
  "stages": [
    {"stage": "dns", "status": "PASS", "latency_ms": 5},
    {"stage": "https", "status": "PASS", "latency_ms": 120},
    {"stage": "server_time", "status": "PASS", "latency_ms": 80},
    {"stage": "klines", "status": "PASS", "latency_ms": 150},
    {"stage": "closed_candle_validation", "status": "PASS", "latency_ms": 0}
  ],
  "required_action": null
}
```

If DNS fails, all downstream stages are marked SKIPPED and `required_action = NO_VALID_LIVE_TRADE`.

### 3. Binance USD-M Futures REST is the primary route

`acquire_verified_closed_ohlcv` already used Binance REST as primary with browser fallback.
No changes needed here — the pre-existing route was already correct.

Route order:
1. Direct Binance REST (`https://fapi.binance.com/fapi/v1/klines`)
2. Browser direct navigation to same Binance endpoint (optional diagnostic fallback)
3. Failure manifest

### 4. Forming candle exclusion uses Binance server time

Already implemented in `_parse_and_verify_klines`: candles with `close_ms > server_time_ms` are excluded. The `current_forming_candle_excluded` flag is recorded in the manifest.

### 5. Retry/backoff added

`execute_with_retry()` added to `smc_desk/data/live_ohlcv.py`:
- 3 attempts max per route
- Backoff: 1s, 2s, 4s
- `acquire_verified_closed_ohlcv` now wraps each route call with retry
- Route attempts record `retry_attempts` count on success, `retry_attempts_exhausted: true` on failure

### 6. Browser fallback is optional and diagnostic only

`allow_browser_fallback` parameter (default `True`) controls whether the browser route is attempted after REST failure. Browser route navigates directly to `https://fapi.binance.com/fapi/v1/klines?symbol=...`, not through TradingView.

### 7. Failure manifest always written on total failure

`verified_closed_ohlcv_failure.json` contains:
- `required_action: NO_VALID_LIVE_TRADE`
- `tradingview_used_as_market_truth: false`
- Full `route_attempts` array
- DNS diagnostic

### 8. Regression tests

`tests/test_live_ohlcv_reliability.py` — 21 tests covering:

1. DNS failure writes NO_VALID_LIVE_TRADE
2. REST timeout retries exactly 3 times
3. REST success writes verified manifest
4. Current forming candle is excluded
5. Stale candle batch is refused
6. Malformed Binance row is refused
7. Non-decimal Binance row is refused
8. Browser fallback only used after REST failure
9. TradingView never used as market truth (success case)
10. TradingView never used as market truth (failure case)
11. Failure manifest contains all route attempts
12. Route health preflight blocks on DNS failure
13. Route health preflight READY when all checks pass
14. Stage independence checks for each health stage
15. Symbol validation
16. Retry counter recorded in route attempts
17-21. Existing `tests/test_live_ohlcv.py` tests (3 tests) all still pass

## Validation

- Focused live OHLCV suite: `21 passed in 42s`
- The existing `tests/test_live_ohlcv.py` (3 tests) still pass with retry integration
- compilall: passed

## Authority Boundary

WP-0019 does not create strategy edge, paper execution, live execution, or capital-risk authority.
It is a live data reliability repair. The system still requires verified closed Binance candles
before perception can run, and still writes NO_VALID_LIVE_TRADE when market truth is unavailable.

## Next Gate

WP-0019 is complete. Next: either run a real BTCUSDT live route smoke, or freeze a clean
foundation release package (WP-0019-NEXT / WP-0020).
