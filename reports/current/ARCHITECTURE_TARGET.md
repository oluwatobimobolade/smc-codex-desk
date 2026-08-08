# Target Architecture

The target architecture follows the Market Colleague constitution.

## Package Layers

```text
smc_desk/
  colleague/      request, context, orchestrator, analysis package, thesis
  market_truth/   data adapters, quality, timeframe builder, provenance, reconciliation
  perception/     ontology-led structure/FVG/swing lifecycle
  temporal/       event ledger, MTF graph, confirmed/provisional state, replay
  scenarios/      scenario contract, evidence graph, decision policy
  rendering/      clean, perception, audit, scenario, and MTF mosaic renderers
  vision/         Kimi/TradingView evidence and independent visual observations
  prediction/     research-only models and calibration
  memory/         case store, similarity, outcome store, failure memory
  execution/      paper-only after certification, live disabled
  governance/     authority and release state
```

## Canonical Run Package

Every market-colleague run should eventually write:

- `request.json`
- `run_manifest.json`
- `authority_manifest.json`
- `source_manifest.json`
- `data_quality.json`
- `decision_time.json`
- canonical and derived data
- external capture manifest and alignment report
- perception objects and event ledger
- MTF state graph
- provisional and confirmed state
- scenario tree and decision file
- vision/reconciliation output
- prediction/abstention files when certified
- clean/perception/audit/scenario charts
- `reports/colleague_thesis.md`
- pending and resolved outcome files

## Migration Rule

Move files only when the migration reduces ambiguity or duplicate authority.
Do not reorganise source modules for appearance.
