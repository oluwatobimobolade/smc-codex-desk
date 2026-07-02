# WP-0002 - Colleague Orchestrator

## Problem

The market-colleague workflow was a useful vertical slice, but it was still
legacy-engine centred. The constitution requires a PerceptionEngineV2-led
orchestrator that writes a complete analysis run package.

## Desired Behaviour

One command creates `analysis_runs/<run_id>/` with canonical data, derived
timeframes, data quality, PerceptionEngineV2 objects, MTF graph, confirmed and
provisional state, scenario files, decision file, charts, reports, legacy
comparison, and a hashed run manifest.

## Authority Limits

- PerceptionEngineV2 is primary perception source.
- Legacy engine is comparison-only.
- Prediction remains disabled.
- Paper and live execution remain disabled.
- No market-edge claim is made.

## Acceptance Gates

- Required `smc_desk/colleague/` modules exist.
- `tools/run_market_colleague_case.py` delegates to the orchestrator.
- Package completeness and no-future-leakage tests pass.
- Full pytest passes.
- A BTCUSDT real-data smoke run writes a complete analysis package.
