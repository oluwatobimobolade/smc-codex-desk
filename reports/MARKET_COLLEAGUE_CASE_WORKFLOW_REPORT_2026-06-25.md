# Market Colleague Case Workflow Report - 2026-06-25

## Purpose

The core goal is to make the SMC desk behave like a local market colleague:
use canonical OHLCV data, rebuild comparable charts, annotate the engine view,
optionally attach TradingView/WebBridge evidence, and produce a clean thesis
without pretending the system has validated predictive authority.

This pass implemented the missing operator-facing workflow between the research
lab and live dual-lens tooling.

## What Was Added

### `tools/run_market_colleague_case.py`

One command now builds a complete local-first desk case for any Binance USD-M
perpetual symbol:

```bash
.venv/bin/python tools/run_market_colleague_case.py --symbol BTCUSDT
```

It supports:

- canonical 15m Binance futures CSV input;
- automatic symbol normalization such as `BTCUSD` -> `BTCUSDT`;
- optional decision-time replay;
- optional rules config;
- optional diagnostic bias override;
- optional TradingView/WebBridge `screenshots.json` attachment;
- holdout/exclusion guard;
- configurable chart windows.

Each case writes:

- `manifest.json`;
- `engine_analysis.json`;
- `mtf_snapshot.json`;
- `trade_plan.md`;
- `colleague_thesis.md`;
- `independent_review_prompt.md`;
- visible 15m/1H/4H/1D CSVs;
- clean raw 15m/1H/4H/1D charts;
- annotated 15m engine chart.

### `tests/test_market_colleague_case.py`

Added focused coverage for:

- complete local artifact generation;
- no-future-leakage metadata;
- normalized Binance futures symbol/path handling;
- TradingView/WebBridge evidence attachment without turning screenshots into
  price authority.

### `specs/LOCAL_FIRST_RESEARCH_LAB.md`

Documented the market-colleague command separately from the gold-candidate case
lab. The docs now make the distinction explicit:

- market-colleague cases are daily desk/review artifacts;
- reviewer lab cases are perception gold-candidates;
- neither makes engine labels into gold truth.

## Real Smoke Case Generated

Command:

```bash
.venv/bin/python tools/run_market_colleague_case.py \
  --symbol BTCUSDT \
  --decision-time 2026-06-19T23:45:00Z \
  --output-dir case_library/market_colleague/BTCUSDT/20260619_2345_smoke
```

Output folder:

`/Users/tobimobolade/smc-codex-desk/case_library/market_colleague/BTCUSDT/20260619_2345_smoke`

Result:

- Symbol: `BTCUSDT`
- Decision candle: `2026-06-19T23:45:00`
- Latest close: `63512.6`
- MTF execution consensus: bearish
- Engine verdict: `Pass / Grade C`
- Direction: bearish
- Risk: `0.0%`
- TradingView evidence: not attached in this smoke run

The generated thesis correctly says this is a no-risk Pass, not a trade call,
because the engine lacked a valid 15m POI, recent liquidity sweep,
displacement-backed break, stop buffer, and risk/reward floor.

## Verification

Passed:

```bash
.venv/bin/python -m pytest tests/test_market_colleague_case.py -q
```

Result:

`3 passed in 1.11s`

Passed:

```bash
.venv/bin/python -m compileall -q smc_desk tools tests
```

Passed:

```bash
.venv/bin/python -m pytest -q
```

Result:

`345 passed in 34.20s`

Rendered chart artifacts were checked for existence, dimensions, and file size.
The BTC smoke produced nonblank 2560x1440 clean charts and a 2880x1440 annotated
chart.

## What This Solves

- The desk now has a single local command to create a reproducible analysis
  case for BTC/ETH/SOL/XRP/BNB or any compatible Binance futures CSV.
- The workflow preserves source authority: OHLCV drives levels; screenshots are
  optional visual cross-checks.
- The thesis and independent review prompt make human/AI disagreement capture
  easier without leaking engine labels into the first visual read.
- The manifest records hashes, data quality, no-future-leakage policy, HTF
  derivation policy, bias policy, and authority policy.

## What Is Still Not Solved

- This is not yet an autonomous live trader.
- This does not prove predictive edge.
- TradingView image-to-local-chart pixel reconciliation is not implemented yet;
  the hook is present through `--tradingview-manifest`.
- The engine is still heuristic and must continue through adjudicated
  perception review, state-machine replay, and out-of-sample outcome testing.
- Live screenshots were not captured in this pass because the task was to build
  and verify the local core workflow without relying on external APIs.

## Recommended Next Step

Use this workflow as the standard daily desk artifact:

1. Run `tools/sync_market_data.py --assert-clean`.
2. Capture TradingView screenshots with Kimi WebBridge when visual comparison is
   needed.
3. Run `tools/run_market_colleague_case.py --symbol <SYMBOL>`.
4. Review clean charts first via `independent_review_prompt.md`.
5. Compare against `engine_analysis.json` and log disagreements as training
   cases.

