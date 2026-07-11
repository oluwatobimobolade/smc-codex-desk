# WP-0044 Governance and Evidence Reconciliation

**Gate:** `GATE-GOVERNANCE-CONSISTENCY-001`
**Status:** `VALIDATED`
**Date:** 2026-07-10
**Baseline HEAD:** `b067a9995eff4814cc87661f7cabba0e50a2e0e1`
**Source manifest SHA-256:** `ec7155e83cb66bf04b77e43771bb0b31c1a6af9bba9b974fe5dc85f171dc9101`

## Decision

The Perception and Annotation Bridge programme is sound, but the repository
could not responsibly start new structure semantics while governance and source
continuity contradicted each other. WP-0044 closes that prerequisite.

## Corrections

1. Replaced stale `latest_validation=WP-0022` semantics with an append-only,
   source-bound validation registry and explicit current gate.
2. Registered both controlling PDFs by path, byte size, modified time, and
   SHA-256. Issued a historical amendment to WP-0042's incomplete PDF finding.
3. Established domain-scoped authority precedence and a controlled status
   vocabulary that separates implemented, validated, certified, and promoted.
4. Marked the companion repository historical and non-authoritative.
5. Corrected root onboarding and `README_FIRST` to identify orchestrator v3 and
   the compact bridge as current.
6. Marked WP-0043 `VALIDATED_WITH_LIMITATIONS`; full CLI mapping remains deferred.
7. Corrected blanket deprecation of `smc_desk.mtf`: resampling is canonical,
   while old snapshot helpers are comparison-only.
8. Restored the WP-0041A/partial-HTF/offline-XAU stash and reconciled it with
   WP-0043. The recovery stash remains intact.
9. Added executable governance lint and ten focused regression tests.

## Validation

- Focused integration: 44 passed.
- Governance foundation plus WP-0044 contract: 17 passed.
- Governance consistency: pass.
- Authority boundary: pass, 91 files, zero forbidden imports.
- Full suite attempt 1: 1 failed, 778 passed, 1 skipped. Failure retained.
- Full suite final: 779 passed, 1 skipped in 137.89 seconds.
- Compileall and diff check: pass.

## Gate Meaning

`VALIDATED` means the declared WP-0044 controls behave as specified for the
recorded source state. It is not `CERTIFIED` or `PROMOTED` because the current
source state is not yet represented by a new commit and the readiness bridge is
not complete.

## Next Work

Run BR-001 through BR-006 as one compact programme. Start with reproducibility,
market-truth fixtures, and mandatory provenance. Do not modify authoritative SMC
structure semantics before `GATE-PERCEPTION-ANNOTATION-READY-001` passes.

No prediction, paper execution, or live-capital authority was created.
