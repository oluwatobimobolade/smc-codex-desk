# WP-SMC-12 Evaluation Truth and Adapter Repair — Final Report

## Outcome

The runtime adapter repairs and the complete human-evaluation lifecycle now
fail closed. Cohorts are generated atomically once, all reviewer/system/source
evidence is hash-bound, production detector shapes are indexed without loss,
and incomplete, failed, drifted, or tampered inputs cannot produce metrics.

Status: **PASS / LOCAL / OBSERVE-ONLY**. Empirical certification is unchanged.

## Runtime truth repairs

1. The cohort slice uses the canonical close-visible-at contract. A 15m candle
   opening at 12:00 is excluded from a 12:00 decision, and reconstructed 1h,
   4h, and 1d candles must also be fully closed.
2. Reviewer evidence and system evidence are aligned across 1d, 4h, 1h, and
   15m. The sealed answer records decision time and ATR by timeframe.
3. `collect_liquidity_evidence` reads the production nested level fields and
   joins separate sweep objects through `swept_level_id`.
4. Current price reaches the formal structure graph and market-state path.
5. Production `swings.local/internal/external` lists are recursively indexed.
   Object keys are timeframe-qualified, preventing cross-timeframe ID
   collisions. The real BTC case contained 1,937 priced metadata records and
   zero missing significant-object lookups.

## Evaluation-integrity repairs

1. `smc_desk/evaluation/cohort_integrity.py` is the shared schema and sealing
   authority for the builder and scorer.
2. `definition_set_status_v2` binds analyst identity, review time, rationale,
   case IDs, and the exact case metadata. A status label alone cannot promote a
   placeholder set.
3. `markup_cohort_v2` is built in a sibling staging directory and atomically
   renamed. Existing output paths are refused, so reruns cannot replace a
   system answer beside human markup.
4. Source files, causal slices, charts, templates, metadata, sealed answers,
   instructions, and case/cohort seals are SHA-256 bound and verified before
   scoring.
5. Detector or POI-lifecycle exceptions produce a failed, unscoreable cohort;
   they can never be labelled `READY`.
6. `markup_annotation_v2` requires explicit completion, reviewer/case/source
   identity agreement, valid decision fields, and no post-decision annotation.
   Genuine blank ranges, draws, and POIs remain unscored rather than failed.
7. Structure uses maximum one-to-one semantic matching with the ATR belonging
   to each annotation timeframe. The scored structure contract is BOS, CHoCH,
   swing high, and swing low. Sweeps remain recorded under liquidity until an
   expert-approved significance rule exists.
8. Every aggregate has its own scored denominator; zero-valued defined F1 is
   `0.0`; and system trade/watch/no-trade classification is scored explicitly.
9. Score reports bind the cohort seal, case seal, and completed-markup hashes,
   are written atomically, and never overwrite an existing report.
10. Governance now verifies every current source-manifest entry, including
    size and SHA-256, instead of checking only the manifest file's hash.

## Quarantined artifact

`review_queues/markup_cohort_20260808` remains preserved as
`INVALID_DO_NOT_MARK`. Its original future-candle, placeholder-label,
reviewer-evidence, and scorer-input defects remain visible in the audit trail.

## Verification

- Focused evaluation/runtime/governance ring: **139 passed** in 3.81 seconds.
- Full repository suite: **1,251 passed, 1 skipped** in 438.30 seconds.
- Real BTC diagnostic: requested and sealed cutoff both 12:00 UTC; four chart
  and ATR timeframes; 1,937 detector objects; zero missing significant object
  prices/metadata; non-null market-state price; diagnostic cohort remained
  unscoreable and was moved to Trash after inspection.
- Compileall, diff check, authority boundary, governance consistency, and the
  20-entry source-manifest content audit: **PASS**.

## Explicitly not completed

- No analyst-selected replacement development cohort exists yet.
- No human perception agreement or calibration score exists.
- The sealed 30-case blind cohort remains untouched and is unavailable for
  iterative tuning.
- Sweep-event precision remains deferred until an expert defines which sweeps
  count as significant evaluation claims.
- No predictive edge, signal, paper, live, or execution authority was created.

## Exact next gate

An independent analyst selects 12–15 development cases from charts without
opening system answers, records the complete `definition_set_status_v2`
provenance, then generates one new immutable cohort. One expert completes all
`markup_annotation_v2` reviews before any threshold changes. Only after the
resulting disagreements are classified may detector, liquidity, POI, or
annotation-authority tuning begin.
