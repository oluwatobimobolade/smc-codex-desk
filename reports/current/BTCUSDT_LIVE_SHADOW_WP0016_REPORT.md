# BTCUSDT Live Shadow WP-0016 Report

Date: 2026-06-26

## Verdict

No executable BTCUSDT signal was produced.

The correct system decision is:

- `NO_VALID_LIVE_TRADE`
- `live_execution_enabled=false`
- `paper_execution_enabled=false`
- `market_edge_claimed=false`
- `capital_risk=0`

## What Worked

- Kimi WebBridge daemon was healthy:
  - `running=true`
  - `extension_connected=true`
  - version `v1.10.0`
- TradingView opened `BINANCE:BTCUSDT.P`.
- Visual screenshots were captured for:
  - `15m`
  - `1h`
  - `4h`
  - `1d`
- The screenshots show a visible BTCUSDT.P chart around the 60.19k area.

Visual evidence:

- `analysis_runs/live_btcusdt_wp0016_20260626/visual_only/screenshots/BTCUSDT_15m.png`
- `analysis_runs/live_btcusdt_wp0016_20260626/visual_only/screenshots/BTCUSDT_1h.png`
- `analysis_runs/live_btcusdt_wp0016_20260626/visual_only/screenshots/BTCUSDT_4h.png`
- `analysis_runs/live_btcusdt_wp0016_20260626/visual_only/screenshots/BTCUSDT_1d.png`

## What Failed

The live candle acquisition lane failed before the engine could claim decision
authority.

1. First TradingView live-shadow attempt:
   - Output: `analysis_runs/live_shadow_btcusdt_wp0016_20260626/summary.json`
   - Failure: local WebBridge HTTP wrapper timed out while waiting for
     TradingView OHLCV.

2. Retry after increasing the wrapper timeout:
   - Output: `analysis_runs/live_shadow_btcusdt_wp0016_20260626_retry/summary.json`
   - Failure: TradingView OHLCV fetch timed out inside the browser after 180
     seconds for `BINANCE:BTCUSDT.P`, `15m`, 220 requested bars.

3. Binance REST fallback:
   - Failure: DNS resolution error for `fapi.binance.com`.

4. Browser-side Binance fetch fallback:
   - Failure: browser `fetch` failed.

## Why This Is The Right Outcome

The system must not invent levels or force a trade from a screenshot. The
current authority rule is:

> Engine decisions require verified closed OHLCV candles. Screenshots are
> visual evidence and reconciliation context only.

Since current closed BTCUSDT OHLCV was unavailable through both TradingView and
Binance routes, the full engine did not receive a valid live candle set. A live
signal would have been a hallucination.

## Visual Read Only

The screenshots visually show BTCUSDT.P under broader bearish pressure on
1h/4h/1d, with price rebounding inside the lower part of the recent range near
60.19k. This is useful context but not an executable trade thesis because the
data-authority lane failed.

## Required Next Fix

Create a live OHLCV reliability work package:

- add route-level health checks for TradingView OHLCV and Binance REST;
- add retry/backoff with smaller bar windows;
- store provider-specific failure payloads;
- add a fallback that can use recent verified local candles plus explicitly
  marked stale/live-gap metadata;
- keep the default decision as `NO_VALID_LIVE_TRADE` whenever current closed
  candles are unavailable.
