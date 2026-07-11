# BR-001 to BR-003 Perception Experiment Foundation

**Status:** `VALIDATED_LOCAL_FOUNDATION_SLICE`  
**Date:** 2026-07-10  
**Baseline HEAD:** `b067a9995eff4814cc87661f7cabba0e50a2e0e1`  
**Source manifest:** `foundation_programme/PERCEPTION_READINESS_BRIDGE/BR001_003_SOURCE_MANIFEST.tsv`  
**Source manifest SHA-256:** `e4e3e25681b993a4954f4a739667551bc4f0b3680fcdfccd3259eb9a251f92e5`

## Why This Came First

Structure is the load-bearing layer, but the audit found that canonical
Perception V2 still imported legacy `rules`, while canonical context utilities
imported legacy `case_library` and `mtf`. A BOS/CHoCH experiment could therefore
look clean while running under mixed authority. Redesigning structure on that
foundation would make the result untrustworthy.

## Implemented

1. Added pure canonical hashing, OHLCV contract, and HTF reconstruction modules.
2. Added `market_truth_certificate_v1`: exact decision cutoff, completed 15m
   rows, independently reconstructed 1H/4H/1D, exact source-row lineage and
   hashes, incomplete-bucket exclusions, and future-row non-authority.
3. Moved PerceptionEngineV2 to detector-only
   `PERCEPTION_DETECTOR_CONFIG_V2`; strategy/risk fields cannot enter its
   canonical config model.
4. Strengthened authority lint from selected function names to whole forbidden
   legacy modules: `engine`, `case_library`, `mtf`, and `rules`.
5. Added a CPython 3.14.5 environment record and exact perception dependency lock.
6. Added a sealed deterministic baseline command that writes source,
   environment, input, market-truth, authority, AI-role, perception,
   annotation, and validation manifests.
7. Added the AI-centered reasoning contract. AI owns semantic candidate
   selection, causal episode construction, alternatives, ambiguity, and sparse
   annotation planning. It cannot alter OHLCV, time/price coordinates, use
   future candles, bypass invariants, or promote a trade.
8. Added 14 independent BR-002 fixture scenarios and 19 net repository tests.

## Real BTC Proof

Run: `analysis_runs/BR001_003_BTCUSDT_BASELINE_20260710`

- Source: Binance USD-M `BTCUSDT` canonical 15m archive.
- Decision time: `2026-06-20T00:00:00Z`.
- Certified visible rows: 3,000 x 15m.
- Derived completed rows: 750 x 1H, 187 x 4H, 31 x 1D.
- Market-truth status: `PASS`.
- Validation status: `PASS`.
- Experiment fingerprint:
  `92a25a13e0da2c153994fc00ca8546b256b388910fb3871fcb8cb66bfea66944`.
- A second independent run produced the same fingerprint and identical stable
  output hashes.

## Validation

- New BR foundation tests plus canonical authority tests: 29 passed.
- Affected structure/config/annotation suite: 92 passed.
- Focused foundation/offline suite: 37 passed.
- Authority boundary: pass; 93 active files scanned; zero forbidden imports.
- Compileall: pass.
- `git diff --check`: pass.
- Failed provenance-hardening attempt retained: 1 failed, 797 passed, 1 skipped
  in 114.41 seconds. The canonical baseline was correctly refused inside a
  legacy-contaminated shared test process.
- Final full repository suite: 799 passed, 1 skipped in 113.30 seconds.

## Exact Limits

This tranche does **not** pass `GATE-PERCEPTION-ANNOTATION-READY-001`.

- BR-001 still needs an independently repeated clean-environment install and
  full AI/render/evaluate command mapping.
- BR-003 has complete deterministic-baseline provenance; real AI traces remain
  unpopulated until BR-005.
- BR-004 protected benchmark separation is not yet operational.
- BR-005 role-specific prompts/schemas and governed AI replay are not yet complete.
- BR-006 independent human doctrine/adjudication pilot has not begun.
- ESPP structure semantics and professional annotation redesign remain blocked.

No predictive, signal, paper-execution, or live-execution authority was created.
