# TradingView Alignment WP-0003 Report

WP-0003 adds strict chart-state alignment to the Market Colleague package.

The important behavior is discipline: screenshots alone no longer count as
verified TradingView agreement. A manifest must prove the expected Binance perp
symbol, exchange, instrument, timeframes, candle type, linear scale, timezone,
and last closed candle per timeframe. Wrong evidence forces
`SOURCE_MISMATCH`.

Real smoke evidence:
`analysis_runs/BTCUSDT_20260619_2345_wp0003_wp0004_smoke/external/alignment_report.json`

Current limitation: the live WebBridge controller still needs to populate this
verified chart state automatically from a real TradingView session.

Validation: focused tests passed and full pytest returned `352 passed in 25.68s`.
