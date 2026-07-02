# Test Plan

- Focused orchestrator tests.
- Existing market-colleague wrapper tests.
- Compileall.
- Full pytest.
- Real BTCUSDT smoke run on local Binance futures data.

Assertions:

- `perception/objects.json` exists and uses PerceptionEngineV2.
- `legacy_comparison/engine_analysis.json` exists and is comparison-only.
- `authority_manifest.json` keeps execution disabled.
- `run_manifest.json` records no-future-leakage policy.
- The package writes clean charts and reports.
