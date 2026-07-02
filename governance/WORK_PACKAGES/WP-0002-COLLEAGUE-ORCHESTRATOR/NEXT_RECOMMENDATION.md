# WP-0002 Next Recommendation

The next best work package is `WP-0003-TRADINGVIEW-ALIGNMENT`.

## Objective

Make Kimi/WebBridge and TradingView a verified visual comparison layer for
`analysis_runs/`, without giving screenshots authority over OHLCV.

## Build Requirements

1. Open the exact TradingView symbol, preferably Binance perp such as
   `BINANCE:BTCUSDT.P`.
2. Verify symbol, exchange/source, timeframe, candle type, scale, timezone, and
   visible time window from DOM/screenshot evidence where available.
3. Capture 15m, 1H, 4H, and 1D screenshots into the active analysis run.
4. Compare TradingView visible OHLC/time window against local reconstructed
   OHLCV.
5. Write `external/alignment_report.json` with explicit PASS/FAIL reasons.
6. Add negative tests for wrong symbol, wrong timeframe, wrong exchange/source,
   stale chart, and mismatched visible window.

## Promotion Rule

Only after this passes should the visual renderer be judged against TradingView
as a chart-level verification layer.
