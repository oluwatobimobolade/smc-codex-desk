# Live BTCUSDT Full System Test

Date: 2026-06-27

Run folder:

`analysis_runs/WP0020_LIVE_BTCUSDT_20260627_095711/`

## Result

Final gauntlet status: `PASS`

Final colleague action: `NO_SIGNAL`

This was a true live test with no CSV fallback. Binance USD-M Futures REST was
used as canonical market truth. Kimi/TradingView was used only for visual audit.

## Live Market Truth

- Route result: `READY`
- Provider: `binance_rest_direct`
- Verified source: Binance USD-M perpetual BTCUSDT 15m candles
- Fetched at: `2026-06-27T09:57:17.219614+00:00`
- Binance server time: `2026-06-27T09:57:16.449000+00:00`
- Last verified closed candle open: `2026-06-27T09:30:00+00:00`
- Last verified closed candle close: `2026-06-27T09:44:59.999000+00:00`
- Last verified closed candle OHLC: `60342.4 / 60420.2 / 60342.3 / 60372.6`
- Verified closed 15m rows acquired: `1499`
- Current forming candle excluded: `true`
- TradingView used as market truth: `false`

## MTF Package

- 15m rows used: `600`, last timestamp `2026-06-27 09:30:00`
- 1h rows used: `374`, last timestamp `2026-06-27 08:00:00`
- 4h rows used: `94`, last timestamp `2026-06-27 04:00:00`
- 1d rows used: `16`, last timestamp `2026-06-26 00:00:00`

## Visual Audit

- TradingView symbol: `BINANCE:BTCUSDT.P`
- Screenshots captured: `4`
- Screenshot dimensions: `2400x1366`
- Visual reconciliation: `VISUAL_AUDIT_AVAILABLE`
- Caveat: TradingView chart state was requested, but last-closed candle timing
  was not independently read from the TradingView DOM.

## Cognitive Result

- Regime: `ranging / compression / distribution`
- Regime confidence: `0.8298`
- Contradiction result: `INVALIDATE_ALL`
- Dominant direction: `bullish`
- Conflict reason: `4h` bearish while `1h` bullish
- Uncertainty score: `0.6441`
- Refusal result: `NO_SIGNAL`
- Blocking code: `contradiction_invalidates_all`

## What Worked

- Live route health passed: DNS, HTTPS, Binance server time, klines, and closed-candle validation.
- Live OHLCV acquisition succeeded directly from Binance REST in one attempt.
- Current forming candle was excluded.
- 15m/1h/4h/1d package was built from verified 15m data.
- Clean charts and annotated charts were generated for all four timeframes.
- Kimi/TradingView captured four nonblank screenshots.
- Visual reconciliation stayed in the correct authority lane: audit only, no market-truth override.
- Thesis and decision memory were generated.
- The engine refused to force a trade when HTF evidence conflicted.

## What Still Needs Improvement

- Live REST single-call limit gives only `1499` 15m candles, so the live-derived daily context is about 16 daily candles, not multi-year context.
- TradingView visual capture does not yet DOM-verify last closed candle timing.
- The thesis is evidence-linked but still compact; a richer human-style SMC narrative can be layered on top after the authority gates stay stable.
- This is an observation/reasoning pass, not a strategy edge, win-rate, or execution proof.

## Key Artifacts

- Final report: `analysis_runs/WP0020_LIVE_BTCUSDT_20260627_095711/11_final_report/gauntlet_report.json`
- Verified OHLCV manifest: `analysis_runs/WP0020_LIVE_BTCUSDT_20260627_095711/01_verified_ohlcv/verified_closed_ohlcv_manifest.json`
- TradingView manifest: `analysis_runs/WP0020_LIVE_BTCUSDT_20260627_095711/07_tradingview_visual/webbridge_session_manifest.json`
- SMC thesis: `analysis_runs/WP0020_LIVE_BTCUSDT_20260627_095711/09_smc_thesis/smc_trade_thesis.md`
