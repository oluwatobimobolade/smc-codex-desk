# WP-SMC-10A Canonical Causal Episode Repair Plan

Status: `PROPOSED_IMPLEMENTATION_PLAN`

Authority: observe-only. This plan creates no signal, prediction, paper, live,
or execution authority.

## 1. Objective

Repair the canonical structure-to-POI chain so the system reads the market in
the order a disciplined SMC trader should:

1. establish the controlling timeframe and active range;
2. identify the exact liquidity interaction and broken structural level;
3. preserve the complete break episode from probe through acceptance;
4. identify the protected origin that causally owns the accepted move;
5. classify parent origin, continuation origin and execution refinement;
6. rank only lifecycle-valid POIs without assuming nearest or deepest always wins;
7. let AI select, challenge, explain and annotate only certified evidence;
8. consider an entry only after price arrives and lower-timeframe confirmation exists.

The target is not a system that always finds a trade. The target is a system
that never silently confuses child structure, probe geometry, displacement,
origin, POI role or readiness state.

## 2. Immediate Containment

Before promotion work begins:

- Treat the current WP-SMC-10 protected-point override and OB-origin gate as
  `SHADOW_RESEARCH`, not certified canonical truth.
- Replace independent boolean behavior with one explicit mode:
  `legacy_observe`, `shadow_repair`, or `candidate_authority`.
- Default to `shadow_repair` until all gates below pass.
- Emit both old and repaired results into an A/B artifact. Do not let the
  repaired branch overwrite the official graph while it is under evaluation.
- Record mode, thresholds, doctrine hash and feature values in every run
  manifest and evidence pack.

This is containment, not endorsement of the legacy detector.

## 3. Non-Negotiable Invariants

### Structure ownership

- An external break may select only an external protected-point candidate on
  the same owning timeframe.
- An internal break may select only an internal candidate on that timeframe.
- Local structure can refine an internal/external origin but cannot replace it.
- Parent structure changes only after accepted evidence violates the parent's
  own protected narrative.
- Equal or nearby prices never make two swing IDs interchangeable.

### Temporal truth

- Every selected object must have `first_knowable_at <= decision_time`.
- A break episode may use only candles closed at its evaluation cutoff.
- A later-confirmed swing cannot be retroactively used at an earlier decision.
- Future mitigation, reaction or outcome data cannot enter POI ranking.

### Break grammar

- Wick penetration is `PROBE`, never BOS/CHoCH/MSS.
- Body close is `BREAKOUT_CANDIDATE`, not automatic accepted structure.
- Displacement is measured from the actual confirming impulse sequence.
- Follow-through or a valid retest is required for external acceptance.
- First accepted direction-establishing break is
  `INITIAL_DIRECTION_BREAK`, not BOS.
- Internal opposite transition is CHoCH; external reversal transition is MSS.

### POI causality

- An OB must predate and causally own the displacement sequence that produced
  the accepted break.
- The selected origin must link by exact candle/event IDs, not proximity alone.
- A non-empty interval between origin and probe is not proof of causality.
- FVG timing must be directional and chronological; an earlier unrelated FVG
  cannot be called created by the break.
- Parent origin, continuation origin and execution refinement remain distinct.
- No rule may state that a POI is guaranteed to react.

## 4. Canonical Causal Episode Object

Create one deterministic object that all downstream systems consume:

```text
CausalBreakEpisode
  schema
  episode_id
  instrument
  owner_timeframe
  structure_scope                external | internal
  direction                      bullish | bearish
  broken_level_id
  broken_level_price
  broken_level_role
  probe_candle_ids
  body_close_candle_id
  displacement_candle_ids
  acceptance_candle_id
  retest_candle_ids
  first_knowable_at
  accepted_at
  event_type
  protected_origin_candidate_ids
  selected_protected_origin_id
  origin_cluster_candle_ids
  supporting_fvg_ids
  lifecycle_status
  rejection_reason
  authority_contract
```

The object must be immutable after acceptance. Later lifecycle events append
to a separate ledger; they do not rewrite what was knowable at acceptance.

## 5. Phase A - Repair Break Candle Lineage

### Implementation

- Modify `smc_desk/perception/structure.py` so a pending break stores separate
  probe and body-close evidence.
- Never reuse probe `price_low`, `price_high` or body ratio as confirmation
  candle evidence.
- Preserve exact IDs for every candle in the episode.
- Add an acceptance stage using the already-tested experimental lifecycle from
  `experimental_break_engine.py` rather than duplicating its grammar.
- Promote behavior incrementally behind `shadow_repair` mode.

### Tests

- wick and body close on the same candle;
- wick probe followed by body close one candle later;
- probe followed by failed reclaim;
- body close without displacement;
- body close with displacement but no acceptance;
- valid follow-through;
- valid retest;
- first-break classification;
- future-candle append invariance.

### Gate

- Zero mixed-candle displacement records.
- Every confirmed episode has exact probe, body-close and acceptance IDs.
- No accepted event uses a candle after its cutoff.

## 6. Phase B - Coherent Displacement Measurement

### Deterministic features

Measure the actual impulse sequence, not one overloaded break object:

- directional body-to-range ratio per impulse candle;
- aggregate directional body divided by ATR(14) known at impulse start;
- close penetration beyond structure in ATR and bps;
- consecutive directional closes;
- distance travelled before meaningful overlap/retrace;
- chronological FVG created by the impulse;
- wick rejection against movement;
- follow-through distance and duration;
- optional volume participation, recorded separately and never required where
  venue volume is unavailable.

### Classification

- Emit factual features first.
- Emit `weak`, `moderate`, or `strong` only from a versioned research config.
- Do not call the score confidence or probability.
- Keep `valid_for_external_acceptance` separate from POI quality.
- Thresholds remain proposed until preregistered and adjudicated.

### Gate

- Real ATR is always supplied when an ATR-labelled field is emitted.
- `impulse_candle_count` equals the actual sealed sequence length.
- Every FVG supporting the episode is timestamped within the impulse window.
- Mirror and decimal-rescale metamorphic tests preserve semantics.

## 7. Phase C - Scope-Locked Protected Origin

### Candidate generation

Generate candidates only from the episode's owning timeframe and scope:

- latest eligible opposing swing of the same scope;
- origin-cluster extreme that predates displacement;
- prior unbroken parent origin, explicitly typed as parent evidence;
- nested lower-timeframe origin, explicitly typed as refinement evidence.

Parent and child candidates may be compared semantically, but cannot occupy the
same authority slot.

### Selection

- Match by exact evidence ID first and always.
- Remove fuzzy price matching as an authority mechanism.
- Price tolerance may only verify geometry after identity is established.
- If the causal origin is a cluster and not a SwingObject, represent it with a
  typed `ProtectedOrigin` union instead of falling back silently to recency.
- Abstain on a causal tie or incomplete lineage.

### Gate

- Zero external-to-internal/local protected-point substitutions.
- Zero cross-timeframe substitutions.
- Duplicate/equal-price swings preserve distinct identities.
- Every selection explains candidate, runner-up, rejection and abstention.

## 8. Phase D - True OB Origin And POI Roles

### Origin search

- Search backward from the first displacement candle, not from the initial
  probe timestamp.
- Generate every plausible opposing candle/cluster inside the bounded causal
  retrieval window.
- Stop at structural boundaries: prior opposing pivot, consolidation origin,
  parent range edge or earlier accepted origin.
- Link candidate origin -> departure sequence -> body close -> acceptance.
- Reject candidates whose departure does not contain the actual displacement
  and acceptance evidence.

### POI role classification

Every admitted POI receives exactly one role:

- `PARENT_REVERSAL_ORIGIN`
- `EXTERNAL_CONTINUATION_ORIGIN`
- `INTERNAL_REACTION_ORIGIN`
- `EXECUTION_REFINEMENT`
- `FVG_SUPPORT_ONLY`
- `INDUCEMENT_HYPOTHESIS`
- `UNRESOLVED_OR_REJECTED`

### Trader-style ranking

Nearest does not automatically win. Deeper does not automatically win. Rank in
this order:

1. ownership of the controlling accepted break;
2. correct timeframe and structure scope;
3. protected-origin relationship;
4. lifecycle validity and mitigation depth;
5. compatibility with the active parent range and current narrative;
6. external before internal authority;
7. displacement and departure quality;
8. liquidity path and inducement hypothesis;
9. lower-timeframe refinement confluence;
10. depth or distance only as a final tie-break.

The engine must show the primary POI, alternate POI and the exact condition
that would make the alternate become primary.

### Gate

- Every admitted OB has a complete exact-ID causal path.
- No FVG-only pocket is labelled OB.
- A tested/partial POI is never labelled fresh.
- Lower-timeframe testing updates higher-timeframe lifecycle truth.
- Ambiguity produces a map and watch condition, not a fabricated entry.

## 9. Phase E - Trader Narrative State Machine

Use the formal episode and POI roles to express the market as a sequence:

```text
MAP_CONTEXT
  -> LIQUIDITY_EVENT_IDENTIFIED
  -> ACCEPTED_DISPLACEMENT
  -> POI_MAPPED
  -> PRICE_APPROACHING_POI
  -> PRICE_AT_POI
  -> LTF_CONFIRMATION_PENDING
  -> TRADE_PLAN_READY | INVALIDATED | EXPIRED
```

Required trader behavior:

- Always map a valid prospective POI even when there is no immediate trade.
- Distinguish a watch from a pass.
- Do not chase price after displacement near target liquidity.
- Do not call a wick through a protected point a reversal.
- Entry requires arrival plus a fresh liquidity event, displacement and valid
  lower-timeframe structural confirmation.
- Stop belongs beyond the actual structural invalidation with volatility and
  spread allowance. It is never moved because a user merely says it is tight.
- Targets are ordered liquidity objectives, not arbitrary fixed multiples.

## 10. Phase F - AI Brain And Self-Challenge

The AI remains central, but it reasons over certified objects rather than
inventing geometry.

### Required AI sequence

1. Read the parent active range and formal graph.
2. Read accepted causal episodes and their evidence IDs.
3. Build the liquidity map.
4. Compare primary and alternate protected origins.
5. Compare primary and alternate POIs pairwise.
6. State the strongest counter-story.
7. Decide map/watch/confirmation/trade readiness.
8. Select annotation evidence IDs.
9. Review the rendered image against the exact graph.

### Authority

- AI may select, rank semantically, explain, challenge and abstain.
- AI may not set OHLC, timestamps, evidence identity or geometry.
- The challenger may downgrade or request review, never promote.
- Detector dissent is append-only and cannot silently replace market truth.
- No numerical AI confidence until calibrated on adjudicated cases.

## 11. Phase G - Professional SMC Annotation

Render one visual story per native timeframe:

- 4H/1H context: protected parent range, controlling external break, primary
  origin and external liquidity.
- 15m execution: local liquidity interaction, confirmation structure, bounded
  POI refinement and conditional path.
- BOS/CHoCH/MSS lines run only from the relevant swing to the break candle.
- POI rectangles cover their origin candles and stop at the useful review span.
- IDM is labelled hypothesis unless adjudicated.
- Maximum object budgets remain enforced.
- No entry/SL/TP or trade box outside `TRADE_PLAN_READY`.
- A bare chart is valid when the evidence does not support a clean story.

The AI selects what matters. Deterministic code resolves exact geometry. The
visual critic checks semantic correctness and cleanliness after rendering.

## 12. Phase H - Adversarial And Real-Market Validation

### Mandatory regression families

- external and internal swings at the same price;
- local swing newer than external protected origin;
- wick probe followed by delayed body close;
- false nearest opposing candle before an unrelated break;
- deeper protected origin versus shallow continuation origin;
- FVG before, during and after the impulse;
- partial mitigation visible only on a lower timeframe;
- sweep versus accepted breakout over multiple horizons;
- parent/child conflict;
- appended-future invariance;
- vertical mirror and decimal rescale;
- no-evidence, blank, random and unreadable chart abstention;
- renderer locality, label overlap and trade-box prohibition.

### Frozen A/B cohort

- BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT and BNBUSDT.
- Balanced external/internal, bullish/bearish, reversal/continuation,
  delayed-confirmation, FVG-only, shallow/deep and ambiguous cases.
- Existing 30-case cohort may be used for development evaluation.
- A new untouched holdout is required for final promotion.
- Two independent reviewers plus blind adjudication remain mandatory.

### Metrics

Measure separately:

- break event/type/scope agreement;
- protected-origin identity/zone agreement;
- OB origin identity/zone agreement;
- POI role and lifecycle agreement;
- abstention correctness;
- annotation object and geometry agreement;
- calibration only after enough adjudicated records;
- economic outcomes only after perception promotion.

Never mix perception accuracy with trade win rate.

## 13. Promotion Gates

### Gate 1 - Contract integrity

- All causal episode contracts complete and hash-bound.
- Zero temporal, identity, scope or geometry violations.
- Full tests, compile, diff, governance and authority checks pass.

### Gate 2 - Shadow stability

- Repaired path completes across all five crypto symbols.
- No cross-scope substitution or mixed-candle scoring.
- Every disagreement with current V2 is logged and reviewable.

### Gate 3 - Human adjudication

- Required cohort independently reviewed and adjudicated.
- Zero catastrophic gate failures.
- Promotion thresholds preregistered before opening the holdout.

### Gate 4 - Canonical promotion

- Only the repaired episode graph becomes candidate authority.
- Old WP-SMC-10 flags are removed after migration, not left as hidden forks.
- Observe-only remains mandatory.

### Gate 5 - Outcome research

- Only after perception promotion, test POI classes and confirmation states
  with costs, slippage, walk-forward folds and an untouched holdout.
- Paper/live authority remains a separate future decision.

## 14. Implementation Commit Sequence

1. `WP-SMC-10A/1`: containment mode and manifest sealing.
2. `WP-SMC-10A/2`: causal episode schema and break-candle lineage.
3. `WP-SMC-10A/3`: coherent ATR/impulse displacement.
4. `WP-SMC-10A/4`: scope-locked typed protected origin.
5. `WP-SMC-10A/5`: exact origin-to-acceptance OB lineage.
6. `WP-SMC-10A/6`: POI roles and trader narrative state machine.
7. `WP-SMC-10A/7`: AI reasoning, challenger and annotation integration.
8. `WP-SMC-10A/8`: adversarial suite and five-symbol shadow A/B.
9. `WP-SMC-10A/9`: governance reconciliation and frozen review cohort.

Each commit must be independently reversible and must include focused tests.
No commit may claim completion based only on the full suite staying green.

## 15. Definition Of Done

This repair is done only when:

- the engine can show exactly which candles formed the probe, displacement,
  acceptance and origin;
- parent and child structure cannot cross-contaminate authority;
- the chosen POI is causally linked, lifecycle-correct and role-labelled;
- alternative POIs and invalidation conditions are explicit;
- AI annotations are sparse, local and graph-consistent;
- real human adjudication has measured the system's errors;
- the system still refuses when the chart is genuinely ambiguous.

That is the trader-faithful version of perfection: not certainty about the
future, but complete honesty and precision about what the market has actually
done and what evidence would be required next.
