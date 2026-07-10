# WP-0043 — Canonical Runtime and Authority Consolidation

**Gate:** `GATE-CANONICAL-RUNTIME-001`
**Status:** in progress
**Date started:** 2026-07-10

## Goal

Make it impossible, by import-time test, for the canonical chain to reach:

- `smc_desk.engine.analyze_dataframe` (legacy engine entry)
- `smc_desk.rules.RuleConfig` (legacy rule system)
- `smc_desk.colleague.orchestrator` v1 or v2 (superseded orchestrators)

## Approach

1. Add `smc_desk/colleague/__main__.py` so canonical command is "python -m smc_desk.colleague …" without PYTHONPATH.
2. Add `tests/test_canonical_runtime_authority.py` — boundary tests that run `python -m smc_desk.colleague` and inspect the loaded module graph for forbidden imports.
3. Move `tools/analyze_live_dual_lens.py` to `tools/comparison_only/dual_lens_runner.py` with explicit "comparison_only" docstring.
4. Add `authority_trace.json` writer to `orchestrator_v3` so every canonical run emits a trace.
5. Update `governance/DEPRECATION_REGISTER.md` and `governance/AUTHORITY_MATRIX.yaml` to mark v1 + v2 as `comparison_only`.
