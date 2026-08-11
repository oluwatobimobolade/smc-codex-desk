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

## Self-audit repair (2026-08-11, R3/R4)

A post-validation self-audit found one real gap in the new memory layer and
closed it before anything depended on it:

- **Time-order guard.** The store previously accepted any run as "latest". A
  historical replay through the same runner would have overwritten the stored
  state with an older `decision_time`, and the next live run would then have
  reported a false regression. `record_run_transition` now compares decision
  times: when the stored state is strictly newer, the record is flagged
  `forward_transition: false`, the diff is descriptive only, and the store is
  NOT updated. Equal decision times (sealed-pack reruns) remain forward
  re-observations; unparseable times are disclosed as unverifiable order.
  Naive timestamps are treated as UTC so naive/aware comparison cannot crash.
- **Caller-side guard.** The runner wraps the memory/shadow helper so even a
  future regression inside the helper can never fail an analysis run.
- 4 new tests (out-of-order replay flagged and store preserved, forward
  update, equal-time re-observation, unverifiable-order disclosure): 17/17
  in `tests/test_market_state_memory.py`; focused ring 85 passed.

## Validation

- Full suite R1 (pre-rebind): 1390 passed, 1 skipped, 1 governance-only
  source-manifest mismatch (this package's own rebind); no behavioral
  failures.
- Focused ring (market state, narrative planner, live runner, acceptance
  package, context authority, POI contract): 85 passed.
- Real-evidence smoke on the sealed ETHUSDT 2026-08-10 pack: first
  observation recorded; repeat run reads `still NO_CONTEXT` (matching the
  V1/V3 causal disagreement); shadow composed 4H dealing range, 1D equal-lows
  draw, then per-timeframe structure (10 selections,
  RETRACEMENT_WITHIN_PARENT).
- R2 (first rebind validation): registry record
  `WP-SMC-19-COLLEAGUE-MEMORY-NARRATIVE-SHADOW-R2-20260811` (PASS, 1391/1).
- R3/R4 (self-audit repair rebind and revalidation): see the append-only
  records `WP-SMC-19-COLLEAGUE-MEMORY-NARRATIVE-SHADOW-R3-20260811` and
  `...-R4-20260811` (R4 PASS, 1395/1).

## Live-exercise closures (2026-08-11, R5/R6)

A live three-symbol exercise (ETHUSDT, HYPEUSDT, XAUUSD; run
`analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260811_104810`) surfaced two
surfacing gaps, both closed at the text/evidence level only:

- **The liquidity draw was computed but never surfaced.** Every pack's
  `narrative_context.draw` held an exact, evidence-bound target (ETH 1820.61
  equal lows; HYPE 57.999 equal highs; XAU 4363.5 equal lows), while the
  thesis Liquidity Story printed one canned sentence. The local provider now
  appends the draw to that narrative, explicitly labelled "descriptive and
  unpromoted, not a validated sweep target". Real-pack proof: the sealed
  ETHUSDT pack renders the sentence and the decision remains
  `mixed / REVIEW_REQUIRED`.
- **Silent fail-closed perception.** XAUUSD 15m/1h perception raised
  `ValueError` on COMEX daily-settlement gaps (the `forex_5d` session model
  covers weekend closures, not daily settlement), leaving bare charts that
  read as "nothing here" instead of "not analysed". Per-timeframe perception
  failures are now surfaced into the run summary JSON and markdown
  ("Perception gaps (fail-closed)"), via the post-run helper. The underlying
  session-model question (a daily-settlement profile or a 24h spot feed for
  metals) is a doctrine/data decision and is deliberately NOT changed here.

5 new tests (draw note content and silence, failure extraction and ordering,
helper integration): 22/22 in `tests/test_market_state_memory.py`; brain,
validator, and acceptance ring 90 passed. R5/R6 registry records follow the
same rebind-then-validate pattern.
