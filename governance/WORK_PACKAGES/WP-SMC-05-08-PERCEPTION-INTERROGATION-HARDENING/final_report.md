# WP-SMC-05/08 Final Report

Date: 2026-07-13  
Gate: `GATE-SMC-PERCEPTION-INTERROGATION-001`  
Status: `IMPLEMENTED_AND_FULLY_VALIDATED_EMPIRICAL_CERTIFICATION_OPEN`

## Result

All internally addressable requirements from the SMC AI Perception Interrogation audit are implemented and exercised. The implementation contract coverage is `100.0/100.0`. That is not a perception-accuracy score. Empirical certification remains `NOT_CERTIFIED` because the repository contains no eligible independently adjudicated gold cases, no linked calibration cohort, and no real visual response reports.

## Completed Repairs

- Split immutable evidence geometry from renderer-only display geometry and hash-sealed both.
- Added a complete evidence contract registry for every exported object, including anchors, first-knowable candle, causal IDs, alternatives, invalidation, doctrine assumptions, evidence strength, and abstention state.
- Removed probability semantics from uncalibrated heuristics; confidence remains unavailable until calibrated.
- Added hash-verified calibration certificates and dynamic human-adjudicated evaluation input loading.
- Added pre-reaction POI ranking freeze with forbidden future-outcome fields.
- Added sequential replay, runtime candle/contract causality checks, real PNG perturbation generation, semantic response comparison, and no-evidence abstention evaluation.
- Added explicit sweep lifecycle states separating penetration, reclaim, acceptance, local rejection, and structurally confirmed sweep.
- Repaired order-block object identity so multiple break lineages cannot collide.
- Added future-unlockable but fail-closed loaders for sweep/breakout gold replay, real visual perturbation reports, and no-evidence baselines.
- Integrated all evidence artifacts and certification paths into every full orchestrator report.
- Corrected research scope: RefChartQA and Thinking with Visual Grounding support grounding methodology, not SMC competence; Look-Ahead-Bench supports point-in-time evaluation, not proof of this implementation.

## Final BTC Observe-Only Proof

Run: `analysis_runs/PERCEPTION_INTERROGATION_HARDENING_FINAL_20260713/LIVE_FULL_SYSTEM_AI_SMC_V3_20260713_000734/BTCUSDT`

- Binance USD-M data: 15m 1500 rows, 1h 1000, 4h 500, 1d 365.
- Runtime causal audit: `PASS`; 480 visible candles and 5,772 contracts checked; zero violations.
- Evidence contracts: 5,772 complete of 5,772; zero incomplete and zero duplicate contract IDs.
- POI freeze: `FROZEN_VALID`; two ranked POIs; zero future-field violations.
- Annotation: `VALIDATED`; two local structure segments; zero issues; no trade box.
- Perturbation assets: seven real PNG variants generated; semantic response evaluation remains pending.
- Official state: `REVIEW_REQUIRED`, because the stricter causal replay rejects three controlling V1 break/lineage claims. This is correct fail-closed behavior.
- Certification: `NOT_CERTIFIED`; no synthetic numeric score is emitted.

## Validation

- Focused hardening suite: `68 passed`.
- Full repository suite: `1015 passed, 1 skipped` in 149.26 seconds on the final post-recording pass.
- `git diff --check`: passed.
- `.venv/bin/python -m compileall -q smc_desk tools tests`: passed.
- Working tree was already dirty and remains intentionally unclean; unrelated changes were not reverted. HEAD at validation: `4aa1a23`.

## Remaining Empirical Gates

The code can now reach certification when real evidence exists, but it cannot manufacture that evidence.

1. At least 30 independent multi-reviewer adjudicated cases.
2. At least 50 calibration records linked to those adjudicated case IDs, with acceptable ECE and Brier score.
3. A point-in-time sweep-versus-accepted-breakout gold replay over at least 30 adjudicated cases.
4. Real visual responses for all seven chart perturbations with at least 0.95 semantic consistency.
5. Real no-chart, blank-chart, random-chart, and unreadable-chart abstention responses.

No perception accuracy, predictive edge, paper authority, live authority, or guaranteed POI reaction is claimed.

## Empirical Cohort Addendum

The next evidence layer was completed after the initial hardening report:

- `review_queues/SMC_INTERROGATION_30_V1_20260713` contains 30 engine-blind selected historical cases across BTC, ETH, SOL, XRP, and BNB.
- Selection uses only timestamp and rolling 96-bar true-range fraction; no detector output, future reaction, or profitability is used.
- Every case has four completed-candle MTF charts, exact candle maps, 15 OHLC-preserving presentation variants, four sequential replay cutoffs, one exact one-candle counterfactual, two independent reviewer templates, one normalized blind-adjudication template, and one frozen system-submission template.
- The verifier passed 1,230 files, 15,900 visible candles, and 30 counterfactuals with zero issues.
- The exact system source state is frozen across 410 files under aggregate SHA256 `7fdf58769aec4cdb68cbf9d1cf134124e0732c2420fa9e42b7607debb1dece91`.
- Blind scoring implements all ten framework dimensions and all ten catastrophic gates. Quarantined system confidence becomes calibration data only after blind adjudication.
- Final expanded repository validation: `1022 passed, 1 skipped` in 145.33 seconds.

The cohort is `NOT_GOLD`. Two real independent reviews and one blind adjudication are still required for every case. Because these are historical cases from the development-era dataset, a later untouched/future holdout remains required for the strongest release-level generalisation claim.

## Signed Evidence Chain Addendum

The empirical authority boundary was hardened again after an adversarial provenance audit:

- Ed25519/OpenSSL envelopes bind payload hash, evidence type, subject, cohort hash, frozen system hash, signer identity, signer role, and timestamp.
- Gold cases, calibration bundles, reviewer submissions, frozen system submissions, blind adjudications, sweep reports, perturbation reports, no-evidence reports, cohort scores, and calibration certificates cannot unlock authority while unsigned.
- A cohort-pinned trust-registry hash prevents replacement with attacker-controlled keys.
- Trust provisioning requires six distinct public keys: two reviewers, adjudicator, system operator, visual auditor, and calibration authority. Duplicate keys are rejected.
- Implementation coverage can no longer substitute for empirical perception. Certification requires a signed unique-case 30-case score with all ten framework dimensions present and weighted to 100, plus zero catastrophic failures.
- Duplicate case IDs cannot inflate the cohort. Calibration requires unique case/question units, at least 50 records, at least 30 distinct adjudicated cases, ECE <= 0.10, and Brier <= 0.25.
- Visual consistency requires 30 unique adjudicated cases with all 15 perturbations per case. Sweep/breakout validity requires 30 unique cases with at least four sequential cutoffs each.
- Any non-observe vision authority requires a signed calibration certificate from the pinned calibration-authority key.

Final signed-chain source freeze: 410 files under SHA256 `74906372ab6c6b8e77a0611567f11ced4017ad212dbcff140f208705e45e96fa`. Cohort content SHA256: `28207e847f60d1507f984eb7ca1900ac18ece4cf23b1286242dbf53a08ac584c`. Full repository: `1030 passed, 1 skipped` in 159.95 seconds.

The trust registry is intentionally `UNPROVISIONED`; the system cannot create independent reviewer identities for itself. This is now a visible hard blocker rather than an unsigned JSON convention.
