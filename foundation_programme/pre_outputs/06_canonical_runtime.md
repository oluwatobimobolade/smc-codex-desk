# Proposed Canonical Runtime (WP-0042 pre-output #6)

Generated 2026-07-10 against frozen baseline `554e499`. This is a *proposal* — it must be approved inside WP-0043 with explicit boundary tests before becoming authoritative.

## Canonical command

```
python -m smc_desk.colleague.orchestrator_v3 --symbol <SYM> \
       --provider <binance|yahoo|csv> \
       --decision-time <UTC ISO 8601> \
       --output-root analysis_runs/
```

(An `__main__.py` shim will be added in WP-0043 so this command works without `PYTHONPATH=.`. Until then, callers use `PYTHONPATH=. python -m smc_desk.colleague.orchestrator_v3 …`.)

## Canonical chain (proposed)

```
┌──────────────────────────────────────────────────────────────────────┐
│  (1) DATA TRUTH                                                      │
│      smc_desk/data/canonical_loader.py                               │
│      - completed-candle validation (no partial HTF row at decision)  │
│      - 15m canonical, derived 1H/4H/1D                                │
│      - hash every dataset + transformation                            │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  (2) MTF RECONSTRUCTION                                              │
│      smc_desk/perception/formal_structure_graph.py                   │
│      - WP-0040 graph authority (observe-only)                          │
│      - 6 invariants (body-close, no internal flip, etc.)              │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  (3) PERCEPTION INTERFACE                                            │
│      smc_desk/perception/engine_v2.py (PerceptionEngineV2)            │
│      - emits detector candidates + structure events                   │
│      - subscribes to the graph for parent-child context               │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  (4) EVIDENCE PACK                                                   │
│      smc_desk/brain/smc_evidence_pack_builder.py                      │
│      - bundles graph + detector + ohlcv windows into evidence_pack   │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  (5) GOVERNED AI INTERPRETATION (observe-only this programme)        │
│      smc_desk/brain/ai_smc_trader_brain.py  (AISMCTraderBrain)       │
│      smc_desk/brain/ai_smc_consistency_validator.py                  │
│      smc_desk/brain/annotation_plan_validator.py                      │
│      smc_desk/brain/annotation_visual_critic.py (downgrade-only)     │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  (6) DECISION + ANNOTATION                                           │
│      smc_desk/colleague/orchestrator_v3.py  ← final write            │
│      smc_desk/rendering/smc_trader_annotation_renderer.py            │
│      - writes annotation_plan_v2.json, validation, self-review        │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  (7) RELEASE ARTEFACTS (per run)                                     │
│      analysis_runs/<run_id>/                                         │
│        ├── run_manifest.json                                          │
│        ├── authority_trace.json                                       │
│        ├── environment_manifest.json                                  │
│        ├── input_manifest.json                                        │
│        ├── config_manifest.json                                       │
│        ├── result_manifest.json                                       │
│        └── validation_summary.json                                    │
└──────────────────────────────────────────────────────────────────────┘
```

## Authority boundary rules (proposed for WP-0043 boundary tests)

The canonical command **must fail at import** if any of:

1. `smc_desk.engine.analyze_dataframe` is imported.
2. `smc_desk.colleague.orchestrator` (v1) or `smc_desk.colleague.orchestrator_v2` is imported.
3. `smc_desk.rules.RuleConfig` (legacy rule system) is reachable from the canonical module tree.
4. `tools/analyze_live_dual_lens.py` is in `sys.path` for a run tagged `canonical=true`.
5. Any path under `strategies/smc/` (the deprecated strategy docs) is referenced by the canonical command's config.

Each rule gets a regression test in `tests/test_canonical_runtime_authority.py` (to be added in WP-0043).

## What is NOT in the canonical chain

- `tools/analyze_live_dual_lens.py` (legacy engine entry). Allowed only under `comparison_only` runs.
- `tools/build_smc_case.py` (older case builder). Moved to `tools/legacy/` under WP-0043.
- `strategies/smc/` documents. Stay non-authoritative until WP-0044 relocates or labels them.
- All `analysis_runs/*` content. Always non-authoritative evidence (re-derivable).

## Canonical-data whitelist

The canonical loader only accepts:

- Binance USD-M 15m completed candles (UTC).
- Yahoo Finance 15m/1h/1d for XAUUSD and FX (no native HTF, derived internally from 15m).

Rejected at load:

- Partial HTF candles (`status: PARTIAL_HTF`).
- Duplicate timestamps (`status: DUPLICATE_CONFLICT`).
- Future rows beyond decision time (`status: STALE` or `REJECTED`).
- Visual-only screenshots (`status: UNVERIFIED_VISUAL_ONLY`).

Status taxonomy is per WP-0046 design (`VALID_COMPLETE`, `VALID_WITH_DOCUMENTED_GAPS`, `STALE`, `PARTIAL_HTF`, `DUPLICATE_CONFLICT`, `SOURCE_MISMATCH`, `UNVERIFIED_VISUAL_ONLY`, `REJECTED`).

## Authority trace (per run)

Every canonical run must emit `authority_trace.json` containing:

- the canonical command line;
- the resolved module versions (commit SHA of every `smc_desk.*` module loaded);
- the prompt template hash (if AI was called);
- the model + provider + version (if AI was called);
- the dataset hash + transformation hash;
- the chart-class hashes for any rendered image;
- the legacy-engine reachability assertion result;
- the gate status (passed / failed / skipped).

This is the foundation for WP-0047 (release separation) and WP-0049 (governed AI runtime).