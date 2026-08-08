# Perception Programme Deep Audit - 2026-07-11

## Scope

Reviewed commits `dfa4108` through `4aa1a23` plus the two untracked step-10
files:

- `smc_desk/perception/programme_run.py`
- `tests/test_perception_programme_run.py`

The mistakenly supplied website note was excluded from this audit.

## Verdict

`BLOCK_PROMOTION_REPAIR_REQUIRED`

The direction is strong: proposed doctrine, candidate plurality, explicit
lifecycles, separated scores, deterministic validators, abstention, and
metamorphic/counterfactual tests are the right categories of work. The current
implementation is not ready to become perception, graph, annotation, or
certification authority.

The new programme is mostly isolated from the canonical runtime, and several
core functions fail adversarial contract checks. The existing WP-0041B
annotation path has not been modified by these commits.

## Validation Performed

- New focused tranche: `97 passed`.
- Full repository: `922 passed, 1 skipped in 119.51s`.
- Governance consistency: PASS.
- Authority boundary check: PASS, 110 active files scanned.
- Compileall and `git diff --check`: PASS.
- Adversarial contract probes: FAIL in the cases documented below.

Passing tests currently proves that the new modules agree with their own
synthetic fixtures. It does not prove integration with the real formal graph or
correct market semantics.

## Blocking Findings

### 1. The validator can certify no interpretation at all

`certify_interpretation({})` returns `certified=true`. A role-style payload
containing `active_leg_evidence_ids=["ghost"]` also certifies because the
evidence walker recognises only five exact field names. There is no required
schema, no minimum evidence set, and no completeness check before zero
violations becomes certification.

Impact: after doctrine approval, an empty or structurally incomplete AI answer
could become `CERTIFIED`.

Relevant code:

- `smc_desk/validation/evidence.py:58-94`
- `smc_desk/validation/validators.py:24-69`

### 2. The advertised end-to-end programme is not end to end

The untracked `programme_run.py` does not build an atlas, run the six AI roles,
execute retrieval tools, build protected points/ranges, run level lifecycles,
rank POIs, evaluate inducement, or render annotations. It hashes supplied IDs,
builds and discards a context payload, then certifies a caller-supplied
interpretation.

The existing six-role runtime still calls `build_role_prompt(role, payload)`
without the new `anchor_tools` design, and there is no tool-call execution loop.

Impact: the step-10 envelope can create the appearance of integration while
none of steps 2-6 or the AI role run supplied the certified interpretation.

Relevant code:

- `smc_desk/perception/programme_run.py:55-106`
- `smc_desk/brain/structure_lab/runtime.py:131-140`

### 3. The retriever targets a graph schema the real system does not emit

The retriever expects `high_object_id`, `low_object_id`, top-level
`protected_point`, `accepted_breaks`, `active_htf_pois`, and
`unswept_external_liquidity`. The real `formal_mtf_structure_graph_v1` emits
`protected_high_swing_id`, `protected_low_swing_id`, and per-timeframe nodes.

On the recorded BTC graph the retriever preserved only the range ID as a
missing placeholder and omitted both actual protected swing anchors. Its fill
sort also orders equal-ranked timestamps oldest first, despite claiming recency
priority.

Impact: the new AI context can omit precisely the parent anchors it promises
never to lose.

Relevant code:

- `smc_desk/brain/structure_lab/context_retriever.py:135-190`
- `smc_desk/brain/structure_lab/context_retriever.py:222-250`
- `smc_desk/perception/formal_structure_graph.py:317-331`

### 4. Candidate semantics contain market-direction and causality errors

- A standard bullish FVG (`later low > earlier high`) is labelled `down`; the
  up/down formulas and documentation are reversed.
- Fractals use right-side candles but store no `confirmed_at` or availability
  time, so a replay can treat a pivot as known at its pivot candle.
- Displacement origin tracing selects the global pre-impulse minimum/maximum,
  not the local opposing origin immediately before the impulse.
- The atlas accepts a `decision_time` but does not enforce or slice by it.
- Atlas candidates use `candidate_id`; the retriever/tools only index
  `object_id`.

Impact: wrong FVG labels, ancient origins, and premature pivots can poison
structure selection and every annotation derived from it.

Relevant code:

- `smc_desk/perception/candidates/indicators.py:109-130`
- `smc_desk/perception/candidates/fractal.py:29-68`
- `smc_desk/perception/candidates/displacement.py:66-102`
- `smc_desk/perception/candidates/atlas.py:82-105`

### 5. Protected-point selection does not implement its claimed causal test

The "opposing" candidate list does not filter pivot direction. A bullish break
can select the latest swing high as its protected point. `predates_break` and
`unviolated` are hardcoded true rather than replayed. The cluster branch uses
only candle lows even for bearish origins. Candidates share the same impulse
score, so ties are resolved by descending candidate ID.

Impact: the most important invalidation anchor can be directionally wrong and
still be presented as causally certified.

Relevant code:

- `smc_desk/structure/protected_point.py:107-168`
- `smc_desk/structure/protected_point.py:215-236`

### 6. Level interactions can promote a non-touch to accepted breakout

When a candle never reaches a level, `classify_at_event` still returns `PROBE`.
At later horizons, `closes_within=false` plus any supplied internal break and
displacement promotes that non-interaction to `ACCEPTED_BREAKOUT`. Direction,
side, actual horizon candles, and sustained-close count are not reconstructed.

Impact: false BOS/breakout labels can be created without a level interaction.

Relevant code:

- `smc_desk/structure/level_interactions.py:126-180`
- `smc_desk/structure/level_interactions.py:184-237`

### 7. The inducement state machine destroys its waiting state

After the intermediate object is touched but before the deeper POI is reached,
the function briefly sets `PATH_ACTIVE` and immediately changes it to
`REJECTED` because all three final conditions are not yet true.

Impact: the exact prospective inducement path the system is intended to track
cannot survive across bars.

Relevant code:

- `smc_desk/structure/inducement.py:99-129`

### 8. Active-range premium and discount zones are outside the range

For a range `[100, 120]`, the code emits premium `[120, 140]` and discount
`[80, 100]`. Correct dealing-range halves are `[110, 120]` and `[100, 110]`.
Activation also performs no prerequisite validation, and the parent/child test
does not exercise an overwrite operation.

Impact: location logic and annotation zones become geometrically false.

Relevant code:

- `smc_desk/structure/active_range.py:104-147`

### 9. POI ranking does not let the AI ranking affect order

The combined key is lexicographic `(-deterministic, -AI, -empirical)`. Therefore
AI and empirical scores only break deterministic ties. A POI with deterministic
10 / AI 0 outranks deterministic 9 / AI 100. Actual detector POIs also do not
carry the nested feature schema this scorer expects, so most real candidates
would score zero or lose their timeframe.

Impact: the documented AI-semantic comparison is not the implemented ranking.

Relevant code:

- `smc_desk/structure/poi_ranker.py:147-190`
- `smc_desk/structure/poi_ranker.py:222-246`

### 10. Narrative grounding misses XRP/forex and most actual role fields

The price regex requires at least three digits before a decimal, so an
ungrounded XRP claim such as `0.5234` and a forex claim such as `1.0835` pass.
Numeric price fields are not checked at all. Only a nearby exact
`evidence_ids` list counts, while actual role fields such as
`active_leg_evidence_ids` are ignored.

Impact: low-priced crypto and forex annotations can contain invented levels
and still certify.

Relevant code:

- `smc_desk/validation/narrative.py:20-25`
- `smc_desk/validation/narrative.py:28-76`

### 11. The proposed doctrine contains unresolved internal contradictions

- BOS is defined as breaking a "protected" swing in trend direction, which
  conflates the continuation target with the opposing protected invalidation
  point.
- BOS requires displacement in semantic selection, calls it optional evidence,
  and separately says two of four confirmation features are enough.
- MSS is formally external, while its unresolved default says it may be the
  same event as internal CHoCH.
- Inducement says "at least one of five necessary conditions" while the module
  and programme narrative require all five.

The doctrine is correctly marked `PROPOSED`, but the loader fails open when the
hash file is absent and treats any unknown non-empty status as authoritative.

Impact: simply changing the doctrine status could activate contradictory and
fail-open semantics.

Relevant code:

- `specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml:451-507`
- `specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml:562-608`
- `specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml:970-1000`
- `smc_desk/structure/doctrine.py:86-141`

### 12. Synthetic labels are incorrectly described as expert ground truth

The synthetic cases were authored inside this implementation and validate the
implementation's own assumptions. No independent expert labelled them. The
commit title and test text call them "expert-labelled ground truth," which
conflicts with the existing no-fabricated-human-gold policy.

Impact: internal contract fixtures may be mistaken for perception accuracy or
expert validation.

Relevant code:

- `tests/test_perception_harness.py:90-97`
- commit `4aa1a23`

## Annotation-Specific Verdict

The new commits do not modify the professional annotation planner, annotation
validator, semantic-to-geometry bridge, renderer, or `orchestrator_v3`.
Therefore annotation label quality has not yet improved through this programme.

Before these concepts can power annotations, the system needs one canonical
annotation ontology that maps certified states to exact labels:

- external continuation: `BOS`
- internal opposite break: `Internal CHoCH`
- confirmed external reversal: one explicitly adjudicated `MSS`/`External CHoCH`
- wick interaction: `Probe`
- reclaimed interaction awaiting confirmation: `Sweep Candidate`
- completed lifecycle: `Confirmed Sweep`, `Accepted Breakout`, or `Failed Breakout`
- invalidation anchor: `Protected High` / `Protected Low`
- POI identity: `OB`, `FVG`, `Supply`, `Demand`, or `Composite POI`, never a
  generic relabel

Each visible mark must retain object ID, scope, owning timeframe, confirmation
status, lifecycle state, and local geometry. The existing WP-0041B renderer
already provides the correct evidence-to-geometry boundary; the new programme
must integrate into that boundary rather than create another renderer.

## Governance Status

The append-only current validation record remains
`WP-0041B-AI-ANNOTATION-RENDER-LOOP-FINAL-20260711`, bound to git head
`b067a99`. Current HEAD is `4aa1a23`; no source-bound registry record or work
package covers these eight new commits. The two step-10 files remain untracked.

The governance checker passes because it does not require every new commit to
have a work-package record. That PASS must not be treated as validation of this
programme.

## Recommended Repair Order

1. Freeze the new programme as `EXPERIMENTAL_NOT_AUTHORITY`.
2. Repair the doctrine contradictions and make doctrine loading fail closed.
3. Define one shared schema adapter for actual PEV2 candidates and the real
   formal graph; eliminate `candidate_id` versus `object_id` drift.
4. Repair FVG direction, candidate availability time, and local displacement
   origin tracing.
5. Rebuild protected-point, active-range, interaction, inducement, and POI
   lifecycles from actual candles/events rather than caller booleans.
6. Make validators schema-first and fail closed on empty/incomplete outputs;
   cover every real role evidence field and all price scales.
7. Wire atlas -> retriever/tool loop -> six AI roles -> validators -> formal
   graph -> WP-0041B annotation bridge in one replayable command.
8. Replace "expert-labelled" with `synthetic_contract_fixture`; later evaluate
   against frozen AI-weak and independently adjudicated cases.
9. Add real BTC/XRP positive, negative, and ambiguous integration cases before
   any promotion.
10. Create a source-bound work package and validation record only after the
    adversarial probes pass.

## Final Decision

Keep the existing canonical system and WP-0041B annotation loop as the active
observe-only path. Do not merge the new programme into authority or use its
labels on live charts yet. The architecture is salvageable, but the current
implementation needs a deliberate repair pass rather than incremental
patching.

## Repair Resolution

The deliberate repair pass was completed later on 2026-07-11. See
`reports/current/PERCEPTION_PROGRAMME_INTEGRITY_REPAIR_20260711.md` and
`governance/WORK_PACKAGES/PERCEPTION-PROGRAMME-INTEGRITY-REPAIR/final_report.md`.
The programme remains experimental and observe-only; the global readiness gate
is still closed.
