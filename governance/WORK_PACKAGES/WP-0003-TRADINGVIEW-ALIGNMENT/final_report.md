# WP-0003 Final Report - TradingView Alignment Contract

## Result

WP-0003 is complete as a strict local alignment-contract slice. The system now
writes a real `external/alignment_report.json` for every colleague analysis run.

## What Was Built

- Added `smc_desk/colleague/tradingview_alignment.py`.
- Validates expected Binance perp TradingView symbol, exchange, instrument,
  required timeframes, screenshot existence, candle type, linear scale,
  timezone, and last closed candle per timeframe.
- Supports optional TradingView OHLCV CSV overlap comparison.
- Treats screenshot-only manifests as attached evidence, but not verified
  alignment.
- Forces `SOURCE_MISMATCH` when attached TradingView evidence contradicts the
  requested symbol/source/state.

## Smoke Evidence

`analysis_runs/BTCUSDT_20260619_2345_wp0003_wp0004_smoke/external/alignment_report.json`

The smoke run has no attached TradingView manifest, so the report correctly
returns `NOT_ATTACHED` instead of pretending verification happened.

## Tests

- No attached manifest remains honest.
- Fully populated manifest passes.
- Wrong TradingView symbol fails and blocks the decision as `SOURCE_MISMATCH`.
- Full pytest passed: `352 passed in 25.68s`.

## Remaining Work

The live WebBridge controller still needs to populate verified `chart_state`
from a real TradingView session. This work package built the gate; the next one
must feed that gate with live browser evidence.
