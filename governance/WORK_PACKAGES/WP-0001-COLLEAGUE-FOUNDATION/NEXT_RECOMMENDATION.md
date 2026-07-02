# Next Recommendation

Start `WP-0002-COLLEAGUE-ORCHESTRATOR`.

Goal: migrate `tools/run_market_colleague_case.py` from a transitional legacy
engine workflow into a canonical run-package orchestrator that writes
`analysis_runs/<run_id>/` and makes PerceptionEngineV2 the primary perception
source.

Minimum slice:

1. Define `smc_desk/colleague/analysis_package.py`.
2. Convert 15m/1H/4H/1D OHLCV rows into `smc_desk.data.schemas.Candle`.
3. Run PerceptionEngineV2 for each timeframe.
4. Write `perception/objects.json`.
5. Preserve legacy engine output as `legacy_comparison/engine_analysis.json`.
6. Write `run_manifest.json` with hashes.
7. Add tests for no-future-leakage and package completeness.
