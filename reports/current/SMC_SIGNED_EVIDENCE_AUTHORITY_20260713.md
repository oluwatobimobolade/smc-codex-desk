# SMC Signed Evidence Authority

## Finding

The earlier empirical loaders were hash-aware but not author-aware. A person could write `real_visual_responses: true`, set `status: PASS`, or place their own key in an unpinned registry. That was not adequate for a genuinely auditable 100/100 claim.

## Repair

The certification chain now requires Ed25519 signatures and a cohort-pinned trust registry.

```text
Frozen charts/data + frozen system source
-> signed independent reviews
-> normalized anonymous submissions
-> signed blind adjudication
-> deterministic ten-dimension score
-> signed cohort score and calibration bundle
-> signed sweep, perturbation and no-evidence reports
-> signed calibration certificate
-> certification gate
```

Every signature binds:

- payload SHA256;
- evidence type and subject;
- cohort content SHA256;
- system code-freeze SHA256;
- signer ID and role;
- signing timestamp.

## Forgery Resistance

Tests now reject:

- payload mutation after signing;
- wrong signer role;
- stale system freeze or cohort hash;
- revoked/inactive or untrusted signers;
- replacement or mutation of the pinned trust registry;
- two reviewer identities sharing one public key;
- unsigned gold, calibration, reviewer, system, adjudication, or external reports;
- duplicate case IDs and duplicate calibration units;
- concentrated calibration from too few cases;
- calibration cohorts that fail ECE/Brier thresholds;
- incomplete 30-case perturbation or sweep cohorts;
- implementation coverage masquerading as empirical perception score.

## Current State

- Full suite: `1030 passed, 1 skipped`.
- Cohort verifier: 1,230 files, 15,900 candles, 30 counterfactuals, zero issues.
- System freeze: `74906372ab6c6b8e77a0611567f11ced4017ad212dbcff140f208705e45e96fa`.
- Cohort content: `28207e847f60d1507f984eb7ca1900ac18ece4cf23b1286242dbf53a08ac584c`.
- Trust registry: `UNPROVISIONED`.
- Empirical certification: `NOT_CERTIFIED`, score unavailable.

## External Boundary

The next step requires six genuinely distinct public-key identities. The system must not generate those identities and then call them independent. After provisioning, reviewers can sign their own work and the adjudication/calibration chain can proceed.
