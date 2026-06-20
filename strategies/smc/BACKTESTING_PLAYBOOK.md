# SMC Elite Backtesting Playbook

This is the research loop for making the Elite Analyst smarter without fooling ourselves.

## Goal

The system should not promise trades. It should help us find clean SMC conditions, test them without future leakage, expose weak rules, and keep improving one measured change at a time.

## Core Workflow

1. Pull market data.

```bash
.venv/bin/python tools/download_binance_futures_ohlcv.py \
  --symbol BTCUSDT \
  --interval 15m \
  --start 2026-06-01 \
  --end 2026-06-18 \
  --output data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_20260601_20260618.csv
```

2. Run a replay backtest.

```bash
.venv/bin/python tools/backtest_smc_elite.py \
  --ohlcv data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_20260601_20260618.csv \
  --symbol BTCUSDT \
  --timeframe 15m \
  --output-dir backtests/2026-06-18/BTCUSDT_15m_smoke \
  --warmup-bars 250 \
  --entry-wait-bars 24 \
  --max-hold-bars 96
```

Default replay behavior is confirmed-only. `Watch Retrace` is a valid watchlist
state, but it is not counted as a trade unless a diagnostic run explicitly uses
`--watch-entry price-only` or `--include-watch-retrace on`.

3. Read the outputs in this order.

- `summary.md`: quick trader-readable result.
- `summary.json`: exact stats for comparison.
- `trades.csv`: every candidate, fill, exit, and R multiple.
- `near_misses.json`: almost-setups and why they were blocked.

4. Change one thing, then rerun.

Examples:

- Entry wait: 8 bars vs 24 bars.
- Entry mode: boundary vs midpoint.
- Risk/reward floor: keep 3R as default, only lower it for experiments.
- Confirmation lookback: how long a sweep and CHoCH remain valid.

5. Keep a holdout period untouched.

Use one period to explore and one later period to confirm. If a tweak only works on the period where we discovered it, it is probably curve-fit.

## Normal Trader Translation

- `Pass`: there is not enough there. Leave it alone.
- `Watch`: the idea has ingredients, but something is missing.
- `Watch retrace`: displacement already happened, but price has not returned to the POI yet.
- `Execute`: all checklist items are true right now.
- `missed_entry`: the idea was valid, but price never came back to the entry zone in time.
- `stop_has_volatility_buffer`: the execution SL has enough ATR breathing room beyond the structural edge.
- `risk_reward_floor`: the trade does not pay enough for the stop size.

## Current Findings From First BTCUSD Spot Smoke

Input:

- BTCUSD, Bitstamp spot.
- 15m candles.
- 2026-06-01 00:00 UTC to 2026-06-18 00:00 UTC.
- First 500 decision-bar smoke test.

Findings:

- With an 8-bar pending window, 5 watch-retrace candidates appeared and none filled.
- With a 24-bar pending window, 3 watch-retrace candidates appeared, 2 filled, and the sample ended at +0.493R.
- This is not statistical proof. It only tells us the pending-window rule matters.
- These watch-retrace trials are diagnostic only. They should not be reported as
  confirmed live-system trades.
- Most common blockers were sweep-before-break, missing sweep, price not at POI, premium/discount alignment, and risk/reward.

## Current Default Data Source

The live research path is now Binance USD-M futures perps:

- `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `BNBUSDT`.
- Canonical execution feed: `15m`.
- HTF context: resample the same 15m feed into `1h`, `4h`, and `1d` for no-future-leakage backtests.
- Direct `1h`, `4h`, and `1d` downloads are still pulled for validation and visual alignment.

Use:

```bash
bash tools/pull_binance_futures_universe.sh
bash tools/train_pair.sh BTCUSDT
```

## Next Research Questions

1. Should pending orders expire after 8, 16, 24, or 32 candles?
2. Should a Watch retrace become its own explicit setup state instead of being mixed into Watch?
3. Should the system require higher-timeframe bias before 15m entries?
4. Should FVG and OB selection prefer the nearest high-quality POI or the best premium/discount POI?
5. How does the same logic perform on untouched data after June 18, 2026?

## Rule Discipline

Do not loosen a rule because one trade missed.
Do not tighten a rule because one trade lost.
Do not promote Watch or Watch Retrace into a live entry rule unless a separate
confirmation rule survives holdout testing.
Only promote a rule change after it improves out-of-sample behavior and still makes SMC sense to a human trader.
