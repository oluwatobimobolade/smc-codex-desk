# WP-0001 Handoff

## What Existed Before

No governance folder existed. Strategy authority lived mostly in
`strategies/smc/` and the transitional market-colleague workflow.

## What Changed

The repo now has a governance foundation, a machine-readable current state, a
dataset registry, capability matrix, authority matrix, initial strategy truth
audit, and one active strategy research candidate: RASC-SMC-V1.

## Why It Changed

The PDFs require the project to align around one Market Colleague constitution,
one active strategy candidate, explicit authority limits, preserved failures,
and no unsupported profitability claims.

## Evidence

See `TEST_REPORT.json` and `BASELINE_EVIDENCE_MANIFEST.json`.

## What Remains Unproven

No strategy edge is proven. No predictive model is certified. Vision remains
observe-only. The orchestrator still needs PerceptionEngineV2 migration.

## Authoritative Files Now

- `governance/README_FIRST.md`
- `governance/CORE_MEMORY.md`
- `governance/CURRENT_STATE.yaml`
- `governance/AUTHORITY_MATRIX.yaml`
- `governance/STRATEGY_EVIDENCE_REGISTRY.yaml`
- `strategies/active/REGIME_ALIGNED_SMC_CONTINUATION_V1/`

## Must Not Be Changed Casually

- Holdout policy.
- Dataset contamination labels.
- Strategy authority mode.
- Perception ontology definitions.
- Any historical failure or negative-result records.

## Next Step

Implement the PerceptionEngineV2-led market-colleague analysis package under
`analysis_runs/<run_id>/`, while preserving legacy engine output as comparison.
