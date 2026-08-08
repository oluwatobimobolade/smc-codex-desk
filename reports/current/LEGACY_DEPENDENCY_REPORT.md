# Legacy Dependency Report

Status: initial WP-0001 dependency map.

## Legacy Or Transitional Components Still Used

- `smc_desk/engine.py`: still provides trade plans, legacy zones/events, and
  markdown trade-plan output.
- `smc_desk/render.py`: still renders the market-colleague annotated chart.
- `strategies/smc/*.md`: older strategy documents and research notes still sit
  in the main strategy folder.
- `strategies/smc/rules_*.json`: research configs remain in the old folder.

## Current Active Or Emerging Components

- `smc_desk/perception/engine_v2.py`: intended perception authority.
- `smc_desk/rendering/`: emerging structured rendering stack.
- `tools/run_market_colleague_case.py`: useful but transitional market-colleague
  package builder.
- `governance/`: new authority and memory layer.
- `strategies/active/REGIME_ALIGNED_SMC_CONTINUATION_V1/`: new active strategy
  research candidate.

## Required Migration

1. Keep legacy engine output as comparison.
2. Make PerceptionEngineV2 the primary object source for market-colleague runs.
3. Build MTF graph and scenario state from perception objects.
4. Move strategy/risk parameters into active strategy profiles.
5. Archive or relabel old strategy material only after dry-run authority audit.
