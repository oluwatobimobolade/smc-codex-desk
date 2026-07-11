# README First

This is the first project document to read before changing SMC Codex Desk.

## Product Goal

Build a dual-lens, evidence-grounded SMC market colleague that validates market
data, reconstructs multi-timeframe charts, forms falsifiable interpretations,
produces professional evidence-linked annotations, and abstains when truth is
insufficient.

## Current Scope And Limits

- Certified market scope: Binance USD-M BTCUSDT perpetual.
- Canonical source: completed 15m candles in UTC.
- Derived timeframes: 1H, 4H, and 1D from canonical 15m data.
- Runtime authority: research and observe-only analysis.
- Predictive deployment: not certified.
- Paper and live-capital execution: disabled.
- Vision and Kimi/TradingView: visual audit only, never market truth.
- Engine and AI labels: weak/research labels until human adjudication.

## Canonical Runtime

- Canonical module: `smc_desk.colleague.orchestrator_v3`.
- Canonical command surface: `python -m smc_desk.colleague`.
- Temporary full live-research wrapper: `tools/run_live_ai_smc_full_system.py`.
- `orchestrator.py`, `orchestrator_v2.py`, and
  `tools/analyze_live_dual_lens.py` are comparison-only.

The command surface currently provides smoke and authority preflight. Full CLI
mapping remains a named limitation of WP-0043 and belongs to the compact bridge.

## Authority Order

Read these in order for current operational work:

1. `governance/AUTHORITY_PRECEDENCE.yaml`
2. `governance/CURRENT_STATE.yaml`
3. `governance/AUTHORITY_MATRIX.yaml`
4. `governance/STATUS_VOCABULARY.yaml`
5. `evidence/VALIDATION_REGISTRY.json`
6. `governance/NEXT_ACTIONS.yaml`
7. The active work package under `governance/WORK_PACKAGES/`

Controlling PDFs and their exact hashes are registered in
`governance/SOURCE_DOCUMENT_REGISTER.yaml`. The repository at
`/Users/tobimobolade/smc-live-market-truth-integration` is historical reference
only and has no current authority.

## Status Language

`IMPLEMENTED`, `VALIDATED`, `CERTIFIED`, and `PROMOTED` are not synonyms. New
work must use the definitions and evidence requirements in
`governance/STATUS_VOCABULARY.yaml`.

## Mandatory Working Process

1. Read the authority files above.
2. Confirm the current gate and source state in the validation registry.
3. Preserve user changes and negative results.
4. Keep market truth, perception, strategy, prediction, and narrative separate.
5. Record source, data, prompt/model, tests, limitations, and rollback per work package.
6. Do not use outcome candles when labeling a decision-time case.

## Current Gate And Next Work

- WP-0042 baseline census: accepted.
- WP-0043 canonical runtime: `VALIDATED_WITH_LIMITATIONS`.
- WP-0044 governance reconciliation: validated.
- BR-001 through BR-003 local foundation: validated for deterministic baseline
  reproducibility, certified candle/HTF lineage, provenance, and AI role authority.
- BR-004 through BR-006 AI-first local slice: validated protected public
  partitions, governed AI role execution, and source-grounded doctrine
  consensus. The blind set remains unpopulated and human certification is
  deliberately later, not a daily operating dependency.
- Next work: isolated blind positive/negative/ambiguous cases and repeated
  AI-assisted evaluation after an explicit freeze.
- Final bridge target: `GATE-PERCEPTION-ANNOTATION-READY-001`.

Do not redesign authoritative BOS, CHoCH, range, liquidity, or POI semantics
before the readiness bridge passes. Existing perception and annotation remain
observe-only research authority while the bridge is built.
