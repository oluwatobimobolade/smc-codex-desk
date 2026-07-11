# WP-0043 — Canonical Runtime and Authority Consolidation

**Gate:** `GATE-CANONICAL-RUNTIME-001`
**Status:** `VALIDATED_WITH_LIMITATIONS`
**Gate decision:** `GATE-CANONICAL-RUNTIME-001` PASS
**Date:** 2026-07-10
**Baseline:** `554e499` (frozen at WP-0042)

## Summary

Made it impossible, by import-time test, for the canonical chain to reach
the legacy engine or the legacy rules module. Established a canonical
command surface (``python -m smc_desk.colleague``) and the
``authority_trace.json`` contract that every authoritative run must emit.

## What was delivered

| # | Change | File(s) |
|---|---|---|
| 1 | Canonical command shim | `smc_desk/colleague/__main__.py` (NEW) |
| 2 | Authority-trace writer | `smc_desk/colleague/__main__.py` (`build_authority_trace`, `write_authority_trace`) |
| 3 | Trace wired into v3 | `smc_desk/colleague/orchestrator_v3.py` |
| 4 | Removed R1 leak: `load_ohlcv_csv` from canonical-runtime module | `smc_desk/colleague/run_context.py` (inlined local loader) |
| 5 | Boundary checker extended to brain + perception + canonical tools; removed blanket `mtf.py` allow | `tools/check_authority_boundaries.py` |
| 6 | v1 + v2 + dual_lens tagged `COMPARISON_ONLY` (module docstrings) | `smc_desk/colleague/orchestrator.py`, `orchestrator_v2.py`, `tools/analyze_live_dual_lens.py` |
| 7 | Boundary regression test (9 tests) | `tests/test_canonical_runtime_authority.py` (NEW) |
| 8 | Deprecation register updated | `governance/DEPRECATION_REGISTER.md` |

## What was caught and fixed

The extended boundary checker detected a **silent R1 authority leak**:

```
AUTHORITY BOUNDARY CHECK: FAIL
Found 1 forbidden import(s) in 91 scanned files:
  run_context.py:13 [top_level] imports load_ohlcv_csv
```

`smc_desk/colleague/run_context.py` was reaching the legacy engine through
`load_ohlcv_csv`. WP-0043 inlined the 15-line loader locally (preserving
exact semantics: lowercase columns, `date`→`timestamp` rename, OHLC
coercion, missing-volume fill), so the canonical chain is now legacy-free.

## Authority boundary rules (now enforced)

A canonical-runtime module may NOT import (the checker fails the run):

- `smc_desk.engine.analyze_dataframe`
- `smc_desk.engine.load_ohlcv_csv`
- `smc_desk.rules.RuleConfig`
- `smc_desk.rules.load_rule_config`
- `smc_desk.engine.build_trade_plan` (and family)
- `smc_desk.engine.StrategyEngineV1`

Active-package set (where these are forbidden):

- `smc_desk/colleague`
- `smc_desk/decision`
- `smc_desk/brain`
- `smc_desk/perception`

Canonical-tool set (where these are forbidden):

- `tools/run_live_ai_smc_full_system.py`
- `tools/run_wp0020_market_colleague_gauntlet.py`

Files explicitly allowed (with justification in DEPRECATION_REGISTER):

- `smc_desk/colleague/legacy_comparison.py` (canonical comparison adapter).
- `tools/analyze_live_dual_lens.py` (tagged COMPARISON_ONLY).

## Validation

| Check | Result |
|---|---|
| `python tools/check_authority_boundaries.py` | PASS (91 files scanned, 0 forbidden imports) |
| `pytest tests/test_canonical_runtime_authority.py -v` | 9 passed |
| `pytest tests/ -q` (full suite) | 754 passed, 1 skipped |
| `python -m smc_desk.colleague --smoke` | emitted valid `authority_trace.json` |
| Backward compatibility | full suite ran 0 regressions |

## Headline before/after

| Aspect | Before WP-0043 | After WP-0043 |
|---|---|---|
| Boundary checker coverage | `smc_desk/colleague` + `smc_desk/decision` | + `smc_desk/brain` + `smc_desk/perception` + 2 canonical tools |
| Forbidden target list | 5 names | 7 names (`load_ohlcv_csv`, `load_rule_config` added) |
| Blanket `mtf.py` allow | yes | **removed** |
| Canonical command | `PYTHONPATH=.` required | `python -m smc_desk.colleague` |
| `authority_trace.json` | not emitted | emitted by both `__main__ --smoke` and v3 run |
| R1 silent leak | present in `run_context.py` | **fixed** |

## Explicit Limitations

- The `__main__.py` shim currently exposes `--smoke` and pre-flight checks
  but not the full CLI mapping (the live entrypoint remains
  `tools/run_live_ai_smc_full_system.py`). Full CLI mapping lands in **WP-0047
  (Dataset, Artefact, and Release Separation)** once the run manifest contract
  is fixed.
- `mtf.py` deprecation handling (file move / rename / `legacy_comparison`
  adapter) is deferred to **WP-0044 (Governance Reconciliation)** once the
  deprecation register's category for it is finalised.

## Rollback instructions

```
cd /Users/tobimobolade/smc-codex-desk
git checkout 554e499 -- smc_desk/colleague/ tools/check_authority_boundaries.py tools/analyze_live_dual_lens.py governance/DEPRECATION_REGISTER.md
rm smc_desk/colleague/__main__.py tests/test_canonical_runtime_authority.py
```

The boundary checker will continue to work (it is independent of
`__main__.py`); only the trace emission is reverted.

## Evidence inventory

- `foundation_programme/WP-0042/` — frozen baseline artefacts (HEAD `554e499`, manifest, classification).
- `foundation_programme/pre_outputs/03_import_call_graph.md` — pre-edit call graph.
- `tools/check_authority_boundaries.py` — extended checker.
- `tests/test_canonical_runtime_authority.py` — regression net.
- `smc_desk/colleague/__main__.py` — canonical command surface.
- `smc_desk/colleague/orchestrator_v3.py` — authority_trace.json writer integrated.
