# Risk Assessment

## Risks

- PerceptionEngineV2 currently covers only part of full SMC semantics.
- CSV is used for package data because Parquet dependencies are not installed.
- Scenario tree is minimal and legacy-comparison-informed in this slice.
- Verified Kimi/TradingView alignment remains pending.

## Mitigations

- Mark prediction and execution disabled.
- Record legacy engine as comparison-only.
- Register package storage format in source/run manifests.
- Keep the next work focused on verified Kimi alignment and richer MTF graph.
