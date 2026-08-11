# WP-SMC-19 — Colleague Memory and Narrative Planner Shadow

**Authority mode:** `additive_observe_only_run_package_evidence`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_EMPIRICAL_CERTIFICATION_UNCHANGED`
**Gate:** `GATE-WP-SMC-19-COLLEAGUE-MEMORY-NARRATIVE-SHADOW-001`

## Why this package exists

Two documented capabilities were built but never wired, leaving the run
packages weaker than the design intended:

1. **Cross-run memory.** `build_market_state` has derived the trader sequence
   per run since WP-SMC-11 phase 2, and `diff_states` could always compare two
   states, but no run ever persisted the previous state. Every run started
   with amnesia: it could not say what changed since the last look, which
   liquidity was taken while it was not watching, or whether the setup had
   advanced or regressed.
2. **Narrative compositionality evidence.** `plan_narrative_annotations`
   (range, then the draw, then the causal POI, then structure per rendered
   timeframe; evidence IDs only) was built in WP-SMC-11 P1, and its canonical
   wiring was recommended on 2026-08-08. It was never connected, so its
   compositional selection has never been recorded anywhere measurable.

## What changed

- `smc_desk/perception/market_state_memory.py` (new): durable per-symbol
  `market_state` store under `analysis_runs/market_state_store/`, atomic
  writes, fail-soft reads, and `record_run_transition`, which diffs the
  current state against the stored one and then persists the current one.
- `tools/run_live_ai_smc_full_system.py`: after a symbol's canonical run
  completes, the runner writes two artifacts into a new
  `18_colleague_memory_narrative/` stage folder:
  - `market_state_transition.json` — what changed since the symbol's previous
    run (newly swept liquidity, bias or primary-POI change, advance or
    regression along the trader sequence);
  - `narrative_annotation_plan_shadow.json` — the narrative planner's
    compositional selection, explicitly `shadow_comparison_only`, not
    rendered, not validated.
- The live summary (`live_full_system_summary.json/.md`) carries the memory
  status and the human-readable "Since last look" transition notes.
- `tests/test_market_state_memory.py`: 13 tests (round-trip adapter, advance/
  regress/newly-swept/bias/POI diff detection, corrupt-store recovery, atomic
  store envelope, run-number selection, fail-soft paths, canonical artifacts
  byte-identical).

## Boundaries held

- The sealed evidence pack is untouched: both artifacts are written post-run
  from the pack artifact, so `pack_hash` remains a pure function of evidence.
- The canonical composer, annotation context authority, validator, and visual
  critic keep full authority over rendered charts. The shadow cannot
  influence any of them and exists so the WP-SMC-13 analyst-marked cohort can
  measure planner-versus-composer selections against human markup before any
  selector is promoted or retired.
- No thresholds were changed (prohibited before WP-SMC-13). No provider
  orchestration (P6) was started. No signal, paper, live, or predictive
  authority was created; both artifacts carry `signal_allowed: false`.

## Validation

- Full suite R1 (pre-rebind): 1390 passed, 1 skipped, 1 governance-only
  source-manifest mismatch (this package's own rebind); no behavioral
  failures.
- Focused ring (market state, narrative planner, live runner, acceptance
  package, context authority, POI contract): 81 passed.
- Real-evidence smoke on the sealed ETHUSDT 2026-08-10 pack: first
  observation recorded; repeat run reads `still NO_CONTEXT` (matching the
  V1/V3 causal disagreement); shadow composed 4H dealing range, 1D equal-lows
  draw, then per-timeframe structure (10 selections,
  RETRACEMENT_WITHIN_PARENT).
- R2 (post-rebind): see the append-only validation registry record
  `WP-SMC-19-COLLEAGUE-MEMORY-NARRATIVE-SHADOW-R2-20260811`.
