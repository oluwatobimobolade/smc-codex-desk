# WP-SMC-10 Causal OB-Origin Repair - Validation Report

**Date:** 2026-07-14
**Work package:** WP-SMC-10-OB-ORIGIN-CAUSAL-REPAIR
**Gate:** GATE-WP-SMC-10-CAUSAL-OB-ORIGIN-001
**Authority mode:** deterministic_classification_lineage_repair_observe_only
**Status:** PASS_LOCAL_OBSERVE_ONLY_EMPIRICAL_CERTIFICATION_UNCHANGED

## Source

- git_head: 0c3acc0 (WP-SMC-10/3 cutover)
- source_state: dirty_worktree_preserved (pre-existing in-flight WP-SMC-09 work untouched by this WP)
- python_version: 3.14.5

## Commands run by `tools/run_validation_registry.py`

1. `python -m pytest -q` → exit 0 → **1077 passed, 1 skipped** in 347s
   (was 1054 / 1 before WP-SMC-10; +23 new tests, no regressions).
2. `python tools/check_governance_consistency.py` → exit 0 →
   `GOVERNANCE CONSISTENCY: PASS`.
3. `python tools/check_authority_boundaries.py` → exit 0 →
   `AUTHORITY BOUNDARY CHECK: PASS. Scanned 123 files. No forbidden legacy imports.`

## Primary result

The canonical `PerceptionEngineV2` path now produces order blocks selected by
displacement into the accepted break, ranked by live `displacement_strength`,
with POI-lifecycle eligibility fenced by causally-correct protected points.
The three flags are default ON; legacy behaviour is opt-in via env.

## Limitations

- No perception accuracy, predictive edge, signal, paper, live, or execution
  authority was created. `authority_contract` is untouched (signal_allowed:
  False, execution: disabled).
- The AI self-exam is not run here; the repair is to deterministic
  classification + lineage, not to AI reasoning.
- Constitution V2 remains proposed with ten pending human-adjudication decisions.
- BR-004-006 (deeper-OB priority, displacement threshold) remains PROPOSED.
  The system still applies a PROPOSED rule as doctrine; adjudication is
  deferred to the project owner (DECISION_LOG.md).
- The causal protected-point override fires only when the algorithm's pick maps
  to an actual SwingObject (cluster/candle picks fall back to the legacy
  recency assignment). This is a conservative invariant-preservation choice,
  not a doctrinal limit.