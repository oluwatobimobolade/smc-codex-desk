# Legacy Authority Dependency Report (WP-0012A)

## Classification of every `analyze_dataframe` dependency

| File | Line | Dependency | Classification |
|------|------|-----------|----------------|
| `smc_desk/mtf.py` | 16, 192 | imports and calls `analyze_dataframe()` | **ACTIVE_AUTHORITY — must remove** |
| `smc_desk/colleague/orchestrator.py` | 29, 216 | imports and calls `analyze_dataframe()` | **ACTIVE_AUTHORITY — must isolate** |
| `smc_desk/colleague/run_context.py` | 13 | imports `load_ohlcv_csv` | **DATA_LOADING — acceptable** |
| `smc_desk/__init__.py` | 3 | public API export | **BACKWARD_COMPAT — can stay** |
| `smc_desk/perception_panel.py` | 25, 209 | legacy perception panel | **DEPRECATED — can stay** |
| `smc_desk/case_library.py` | 11, 170 | legacy case library | **DEPRECATED — can stay** |
| `tools/*` (backtest_elite, backtest_mtf, build_research, replay) | various | comparison/backtest tools | **COMPARISON_ONLY — can stay** |

## Impact of `mtf.py` dependency

`build_mtf_snapshot()` at line 340 calls `slice_15m_to()` then calls `_context_for()` which calls `analyze_dataframe()` at line 192. This means:

1. Every HTF context (1H, 4H, 1D) is computed using the legacy engine
2. HTF bias, protected structure, POIs are all legacy-derived
3. This flows into `orchestrator.py` via `build_mtf_snapshot()` → `build_scenario_tree()` → `build_decision()`

**The MTF layer is the hidden legacy authority. It must use PEV2 on each timeframe instead.**

## Remediation plan

1. Create `smc_desk/mtf_current.py` — new MTF module using PEV2
2. Run PEV2 on 15m, 1H, 4H, 1D separately
3. Build MTF graph from PEV2 snapshots + event ledger
4. Isolate `smc_desk/mtf.py` as `legacy_adapter`
5. Add boundary test that fails if active modules import legacy engine
