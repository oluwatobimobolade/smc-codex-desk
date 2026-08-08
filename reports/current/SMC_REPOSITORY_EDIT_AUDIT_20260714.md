# SMC Codex Desk - Deep Edit Audit

Date: 2026-07-14

## Verdict

The repository has advanced materially. It is now a serious observe-only,
evidence-grounded SMC research system with formal structure, deterministic
annotation geometry, an AI-seat contract, signed empirical-evidence gates, and
explicit abstention. The new WP-SMC-10 changes also move displacement and
order-block admission onto the canonical PerceptionEngineV2 path.

The edit set is not ready to be described as a correct causal-POI engine. The
full test suite passes, but direct source tracing and real-candle A/B probes
found canonical defects not represented in the tests. These defects can change
the protected point, displacement classification, and admitted order block.

## Audited Source State

- Branch: `wp-0012a-remove-legacy-authority`
- HEAD: `adb8adc6cb3cd2cc517c58a0b5345c2004f6f381`
- Latest committed programme: WP-SMC-10 causal OB-origin repair
- Working tree: 73 modified tracked files and 69 untracked paths
- Full validation rerun: 1,077 passed, 1 skipped in 367.45 seconds
- `git diff --check`: PASS
- governance checker: PASS
- authority-boundary checker: PASS

The working tree is intentionally preserved. No unrelated change was reverted.

## What The Edit Programme Built

### 1. Repository and doctrine control

- A source-bound repository census and verified gap matrix.
- Constitution V1 and V2 documents with matching SHA-256 seals.
- V2 correctly separates core structure, optional ICT execution doctrine,
  strategy timing, and annotation vocabulary.
- V2 correctly proposes `INITIAL_DIRECTION_BREAK`, internal CHoCH, external
  MSS, wick probes, body-close candidates, displacement, and follow-through.
- Both Constitutions remain proposed. Their contested decisions are not human
  adjudicated and have no execution authority.

### 2. Experimental perception programme

- Multi-generator candidate atlas: fractal, prominence, directional change,
  changepoint, displacement and indicator candidates.
- Isolated `HybridPerceptionEngineV3Experimental` and staged break lifecycle.
- Anchor-preserving context retrieval and a six-role AI structure laboratory.
- Formal causal episode graph, sweep lifecycle, active-range, protected-point,
  inducement-hypothesis and deterministic validation modules.
- This path is substantial but remains experimental and downgrade-only.

### 3. Canonical structure and POI path

- Formal MTF graph subordinates child structure to parent structure.
- Scenario POI mapping preserves both directions instead of deleting an
  opposing candidate before formal adjudication.
- Causal POI authority separates parent origin, continuation origin, execution
  refinement, FVG-only reaction, and unresolved lineage.
- WP-SMC-10 enables canonical displacement scoring, protected-point selection,
  and an OB-origin admission gate by default.

### 4. Annotation system

- AI selects semantic evidence IDs; deterministic code owns prices, timestamps,
  evidence geometry and display geometry.
- Annotation V2 uses local structure segments, bounded POI zones, local
  liquidity lines and optional conditional paths.
- Immutable evidence geometry is separately hashed from renderer display
  geometry.
- Validators reject ungrounded objects, scope mismatches, FVG-as-OB errors,
  trade boxes outside `TRADE_PLAN_READY`, and geometry tampering.
- The renderer and bitmap critic are sparse and downgrade-only.

### 5. AI seat and empirical authority

- External AI packets are bound to exact profile, Constitution, gauntlet,
  mechanical mirror artifacts and a sealed input hash.
- A ten-station exam is mandatory. Failed or detached stations force
  `REVIEW_REQUIRED` and strip trade fields.
- A 30-case, five-symbol blind cohort exists with sequential cutoffs,
  counterfactuals and perturbations.
- Ed25519 envelopes bind evidence to cohort, system freeze, signer and role.
- The six-role trust registry remains unprovisioned, so the system cannot
  manufacture independent reviewers or certify itself.
- Empirical perception remains `NOT_CERTIFIED`; implementation coverage is not
  accuracy and no predictive edge is proven.

## Critical Findings

### F1 - External protected structure can be overwritten by a child/local swing

`structure._run_causal_protected_point_selection` sends every swing scale into
one candidate pool. The adapter does not preserve structure scope. The matching
function then matches by direction and price, without requiring the selected
candidate ID, timeframe, or external/internal scope.

A direct probe selected `internal_low_99#internal` for an external bullish break
and matched it as the external protected low. On stored 1,500-candle samples:

- BTCUSDT: 34 overrides; 13 external breaks were overridden by non-external
  swings, including local swings.
- SOLUSDT: 19 overrides; 6 external breaks were overridden by non-external
  swings.

This contradicts the parent/child authority doctrine and can recreate the exact
failure the formal graph was intended to prevent.

### F2 - Delayed break confirmation mixes two candles in one displacement score

The break object stores `price_low`, `price_high`, and `candle_body_ratio` from
the first wick/probe candle. When a later candle body-closes through the level,
`_confirm_break` updates only `body_close_penetration`. The canonical scorer
therefore combines probe-candle body/range with confirmation-candle penetration.

A direct probe produced:

- probe body ratio: 0.0091
- probe stored range: 11.0
- later confirmation penetration: 2.0
- resulting score: 0.4030 / weak

The confirming candle itself was a strong body candle. The classification is
therefore not describing one coherent candle or impulse.

Real stored samples contain this path frequently:

- BTCUSDT: 35 of 178 confirmed breaks were delayed confirmations.
- SOLUSDT: 41 of 144 confirmed breaks were delayed confirmations.

### F3 - The OB gate validates the eventual break, not the selected cluster

The detector still chooses the nearest opposing-color cluster before
`candidate_at`. The gate then checks only that the eventual break has a moderate
displacement profile and that some candles exist between cluster and probe.
It does not prove that the selected cluster caused the displacement.

For delayed confirmations, the actual confirmation candle is outside the
recorded departure trace. Under WP-SMC-10 defaults:

- BTCUSDT: 13 admitted OBs linked to delayed breaks omitted the confirmation
  candle from their departure trace.
- SOLUSDT: 15 admitted OBs had the same problem.

The metadata phrase `explicit_break_departure_trace` is therefore stronger than
the evidence in these cases.

### F4 - The canonical displacement profile is partly mislabeled

- `body_to_atr_ratio` is calculated with candle range when the engine supplies
  no ATR. The canonical call currently supplies no ATR.
- `impulse_candle_count` defaults to 1 and has no canonical producer.
- `fvg_created_after_break` uses absolute time distance, so an earlier nearby
  FVG can count as "after" the break.

These fields are useful heuristics, but not yet the measurements their names
claim.

### F5 - Proposed doctrine was enabled canonically before its benchmark gate

The three environment flags default to ON. The OB threshold of score >= 0.45
and penetration >= 4 bps is still a proposed, unadjudicated doctrine choice.
The verified gap matrix says to benchmark before flag lock, but the cutover
already occurred. Observe-only authority limits the damage, but the authority
model is internally untidy.

### F6 - Feature-flag state is not sealed into run provenance

The three WP-SMC-10 environment variables are not recorded in the canonical run
manifest or evidence pack. Two runs at the same commit and data cutoff can emit
different structure/POI objects without the manifest explaining why.

### F7 - Governance validation is narrower than its PASS wording

`governance/CURRENT_STATE.yaml` is dated 2026-07-13 and names the perception
interrogation gate, while `VALIDATION_REGISTRY.json` names WP-SMC-10 as the
current gate. `NEXT_ACTIONS.yaml` does not record WP-SMC-10. The checker passes
because it validates the registry internally but does not compare its current
gate with CURRENT_STATE or NEXT_ACTIONS.

The WP-SMC-10 validation record also identifies a dirty worktree with 141 status
lines but does not bind that dirty state to a source manifest or patch hash.
The recorded Git commit alone cannot reconstruct the exact tested source.

## A/B Impact On Stored Candles

Last 1,500 stored 15m candles per symbol:

| Symbol | Mode | Confirmed breaks | OBs | Strong/moderate/weak |
|---|---:|---:|---:|---:|
| BTCUSDT | Legacy | 178 | 126 | unavailable |
| BTCUSDT | WP-SMC-10 | 178 | 83 | 41 / 76 / 61 |
| SOLUSDT | Legacy | 144 | 92 | unavailable |
| SOLUSDT | WP-SMC-10 | 144 | 60 | 42 / 58 / 44 |

The gate is materially changing the candidate universe. That is expected, but
it confirms that an end-to-end blind benchmark is required before the defaults
can be called correct.

## Honest Readiness

### Strong and working

- closed-candle truth and observe-only boundaries;
- formal parent/child refusal;
- evidence-grounded annotation architecture;
- AI packet integrity and downgrade behavior;
- signed empirical-evidence infrastructure;
- explicit refusal to claim accuracy without gold truth;
- broad regression coverage and deterministic artifact generation.

### Not yet earned

- correct causal protected-point selection on the canonical path;
- causal proof that an admitted OB is the displacement origin;
- calibrated displacement thresholds;
- expert perception accuracy;
- reliable POI reaction probability;
- predictive edge, paper authority, live authority, or execution authority.

## Correct Next Repair Order

1. Preserve break-candle roles explicitly: probe candle, body-close candle,
   displacement sequence and acceptance candle.
2. Score displacement from the confirming impulse sequence with real ATR and
   directional FVG chronology.
3. Scope-lock protected-point candidates and match by exact evidence ID before
   any price fallback.
4. Make OB admission prove cluster -> departure sequence -> accepted break,
   including the actual confirming/acceptance candles.
5. Seal all causal-repair flags and thresholds into every run manifest.
6. Add delayed-confirmation, cross-scope, false-nearest-cluster and FVG-before-
   break adversarial tests.
7. Run a frozen A/B cohort before keeping the flags ON by default.
8. Reconcile CURRENT_STATE, NEXT_ACTIONS, registry and a source manifest for the
   exact tested working tree.

No strategy code was changed during this audit.
