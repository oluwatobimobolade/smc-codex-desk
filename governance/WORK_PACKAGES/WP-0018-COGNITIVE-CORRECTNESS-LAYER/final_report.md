# WP-0018 Cognitive Correctness Layer - Final Report

Date: 2026-06-26

## Objective

Implement the judgment layer described in the attached plan: market truth must
gate perception, regime must contextualize the read, MTF contradictions must
resolve to one conservative state, uncertainty must block weak signals, and the
colleague must write structured decision memory.

## Implemented

- `smc_desk/data/truth_validator.py`
  - Validates OHLCV completeness, candle finality, monotonic timestamps,
    missing-data gaps, OHLC bounds, expected instrument/timeframes, and optional
    provider-feed consistency.
  - Any issue returns `REFUSE_PERCEPTION`.
- `smc_desk/perception/regime_engine.py`
  - Classifies structure regime, volatility regime, liquidity regime, and a
    confidence score.
  - Confidence below `0.60` is a downgrade signal.
- `smc_desk/decision/contradiction_resolver.py`
  - Applies timeframe hierarchy `1D > 4H > 1H > 15m > 5m`.
  - Produces only `ALIGN`, `WAIT`, or `INVALIDATE_ALL`.
- `smc_desk/decision/uncertainty_engine.py`
  - Scores signal confidence, structure confidence, execution confidence, and
    stability.
  - Anything below `0.60` becomes `NO_SIGNAL`.
- `smc_desk/decision/refusal_engine.py`
  - Centralizes hard refusal and no-signal policy.
- `smc_desk/colleague/decision_memory_graph.py`
  - Writes structured graph records containing market state, regime, FVG state,
    contradiction, final decision, outcome, and correction nodes.
- `smc_desk/colleague/orchestrator_v2.py`
  - Runs the observe-only V2 cognitive pipeline:
    `DATA -> TRUTH -> REGIME -> PERCEPTION -> CONTRADICTION -> UNCERTAINTY -> REFUSAL -> MEMORY`.
  - If truth fails, perception is not constructed or executed.
- `tools/run_colleague_brain_v2.py`
  - Local CLI for running the V2 brain from canonical 15m CSV data.

## Real Data Smoke

Command:

```bash
.venv/bin/python tools/run_colleague_brain_v2.py \
  --symbol BTCUSDT \
  --source data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv \
  --output analysis_runs/BTCUSDT_brain_v2_wp0018_smoke \
  --memory-file analysis_runs/BTCUSDT_brain_v2_wp0018_smoke/decision_memory.jsonl
```

Result:

- Truth status: `PASS`
- Perception status: `completed`
- Regime: `ranging / compression / distribution`, confidence `0.7843`
- Contradiction: `INVALIDATE_ALL`
- Final action: `NO_SIGNAL`
- Memory records written: `1`

Interpretation: the system had valid market truth and enough context to reason,
but refused a signal because HTF evidence was contradictory.

## Validation

- Focused cognitive tests: `9 passed in 1.15s`
- Focused regression suite: `40 passed in 1.50s`
- Compileall: passed
- Full pytest: `478 passed, 1 skipped in 29.43s`

## Authority Boundary

WP-0018 does not create a strategy edge, signal authority, paper execution, live
execution, or capital-risk permission. It adds cognitive refusal and judgment
plumbing before strategy is allowed to speak.

## Next Gate

Integrate selected V2 brain artifacts into normal `analysis_runs` packages while
keeping the current V1 colleague path stable, then rerun live OHLCV route smoke
with truth validation as the first gate.
