# Legacy Authority Isolation WP-0012 Report

Date: 2026-06-26

## Result

The Market Colleague can now build a full analysis package without running the
legacy engine. Current decisions and scenarios are derived from
`PerceptionEngineV2` plus MTF context only.

## Files Changed

- `smc_desk/colleague/decision_summary.py`
- `smc_desk/colleague/orchestrator.py`
- `smc_desk/colleague/thesis_builder.py`
- `tools/run_market_colleague_case.py`
- `tests/test_market_colleague_case.py`

## Important Behavior

- Legacy comparison remains available by default for side-by-side evidence.
- `--no-legacy-comparison` disables the legacy engine entirely.
- The no-legacy path writes `legacy_comparison/status.json` instead of
  `engine_analysis.json` and `trade_plan.md`.
- Current `decision.json` records `legacy_trade_plan_used=false`.
- No execution targets, stop loss, or liquidity targets are invented when the
  current system has no execution plan.

## Validation

- Focused market-colleague suite: `7 passed`.
- Neighboring regression suite: `28 passed`.
- Compileall: passed.
- Real BTCUSDT no-legacy smoke package built successfully:
  `analysis_runs/BTCUSDT_20260619_2345_wp0012_no_legacy_smoke/`.

## Remaining Limitation

This is an authority-boundary repair, not an edge proof. The next meaningful
step is a resolved-case cohort with outcomes, not live signal promotion.
