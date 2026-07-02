# Implementation Plan

1. Create `smc_desk/colleague/` request, context, package, decision, thesis,
   and orchestrator modules.
2. Convert visible OHLCV dataframes to validated `Candle` objects with proper
   timeframe close times.
3. Run PerceptionEngineV2 for 15m, 1H, 4H, and 1D.
4. Keep the legacy engine under `legacy_comparison/`.
5. Write canonical package files under `analysis_runs/<run_id>/`.
6. Add tests for package completeness, authority boundaries, and no future
   leakage.
7. Smoke on real BTCUSDT data.
