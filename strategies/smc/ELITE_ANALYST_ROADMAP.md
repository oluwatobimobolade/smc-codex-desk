# Elite SMC Analyst Roadmap

This system is meant to become a disciplined TradingView-facing analyst, not a signal bot. The target standard is:

> Look at the same chart a strong SMC trader would inspect, explain the thesis clearly, define structural invalidation, execution stop, and conditions, and refuse weak setups.

It must not promise profitable trades. It should make the decision cleaner.

## Data Standard

Use three evidence layers for every serious setup.

1. Market data
- 15m execution OHLCV from a named venue.
- 1H, 4H, and 1D resampled from the same 15m source unless native higher-timeframe candles are being audited.
- Source hash, row count, date range, gap count, duplicate count, and NaN count recorded.
- Costs, spread/slippage assumptions, and session/news notes recorded separately.

2. TradingView chart evidence
- Screenshot source must match the OHLCV source where possible, for example `BINANCE:BTCUSDT.P` with Binance USD-M futures OHLCV.
- Capture 1D, 4H, 1H, and 15m for every live case.
- Keep screenshots for wins, losses, missed entries, fake CHoCHs, HTF conflicts, and no-trade chop.

3. Expert labels
- Every important case needs a human review label: bias, HTF narrative, dealing range, liquidity, POI quality, confirmation, grade, verdict, structural invalidation, execution stop, targets, and outcome.
- The machine is not allowed to train itself on unreviewed cases as if they were expert truth.

## Promotion Rules

A rule can become trusted only if it survives:

- at least 20 entered trades in one comparable configuration,
- separate in-sample and holdout periods,
- at least one cross-instrument check,
- visual chart review of representative wins and losses,
- no known future leakage or source mismatch.

More signals do not equal better signals.

## BTCUSD First Build

Use BTCUSDT perpetual as the default crypto source because the local stack now pulls Binance USD-M futures OHLCV and TradingView capture can open `BINANCE:BTCUSDT.P`.

1. Capture exchange-explicit TradingView charts with `BINANCE:BTCUSDT.P`.
2. Build case folders with `tools/build_smc_case.py`.
3. Review the human label templates and mark the first gold-standard examples.
4. Run `tools/audit_case_library.py` after every batch so source alignment, missing files, stale CSV hashes, and unreviewed labels are visible.
5. Generate TradingView Pine overlays with `tools/generate_tradingview_overlay.py` so levels are drawn from deterministic data rather than model eyesight.
6. Backtest only candidate rules that come from reviewed case failures.
7. Re-run BTCUSDT holdout, then ETHUSDT/SOLUSDT/XRPUSDT/BNBUSDT or a proper Forex data source before promotion.

## Screenshot And Annotation Guardrail

Screenshots are evidence, not the source of truth. The correct visual pipeline is:

1. Get exchange-matched OHLCV.
2. Compute swings, liquidity, FVGs, order blocks, BOS/CHoCH, POI, structural invalidation, execution stop, and targets deterministically.
3. Export those exact levels into a TradingView Pine overlay.
4. Capture the overlayed chart with Kimi WebBridge.
5. Ask the model to explain the structured levels and screenshot together.

This avoids the failure mode where a weak model invents support/resistance from pixels. Direct browser drawing with mouse coordinates should not be the core annotation method because it is brittle and layout-dependent.

## Dual-Lens Live Workflow

The current live workflow has two lenses:

1. **Engine lens:** exchange/source-matched OHLCV, closed candles only, MTF context, deterministic POI, execution stop, targets, and verdict.
2. **Vision lens:** TradingView screenshot gestalt, structure cleanliness, visible context, and possible veto.

Reconciliation rules:

- Engine owns all prices. Vision never writes entry, stop, target, or POI prices into a plan.
- `Watch` and `Watch Retrace` remain risk-0 states unless the engine itself produces `Execute`.
- Source mismatch, such as OANDA chart vs Yahoo/OANDA-like data, must be called out and should reduce confidence.
- A strong visual agreement can increase confidence in the explanation, not promote a no-trade into a trade.
- Live data must drop any candle whose open time plus timeframe is later than the decision time.

## Expansion To Other Markets

For Forex, do not use crypto data as a proxy. Use a real Forex source such as OANDA, Dukascopy/tick-derived bars, or a paid aggregate feed. Match TradingView screenshots to the same source prefix where possible, such as `OANDA:EURUSD`.

For metals or indices, record the exact TradingView source and the data source. If those differ, mark the case as useful for visual review but weaker for strict OHLCV replay.

## Current Known Risks

- The engine is heuristic. It detects candle structure, not full discretionary chart context.
- The current research grid is diagnostic and has too few comparable entered trades.
- `wait48` is a hypothesis, not a live upgrade.
- Best-location POI and no-HTF-bias variants are rejected for now.
- The case library needs human labels before it can become training data.
- Forex cases are weaker when the chart source and OHLCV data source differ; use source-matched feeds before treating them as strict replay evidence.
