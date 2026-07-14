# WP-SMC-10 Causal OB-Origin Repair - Final Report

## Status: COMPLETE / PASS / OBSERVE-ONLY

**Completion date:** 2026-07-14
**Commits:** 07f74f4 (1), 13aaf5b (2), 0c3acc0 (3)
**Full validation:** 1077 passed, 1 skipped
**Focused WP-SMC-10 validation:** 23 passed (across 3 new test files)
**Governance:** PASS
**Authority:** PASS (no forbidden legacy imports)
**Empirical certification:** unchanged (observation only)

---

## What Exists

WP-SMC-10 repairs the canonical order-block selection chain. Per SMC/ICT
doctrine an order block IS the origin of displacement -- the last opposing base
whose departure produced the impulsive, structure-breaking move. The canonical
`PerceptionEngineV2` path was picking the geometric "nearest opposing-color
candle cluster" instead, with two further structural problems downstream:

1. **Displacement was dead.** `structure.py:203` hardcoded `displacement_strength=0.0`
   on every break. `score_break_displacement` was only called from
   `structure_hierarchy.py:121`, which `engine_v2.py:120` bypassed. The causal
   POI authority's ranking axis was therefore always zero.
2. **Protected bounds were recency, not causal.** `structure.py:282,287` set
   protected_low/high to the most-recently-confirmed pivot (VGM-006, the exact
   entry Constitution V1 lists under `forbidden_shortcuts`). The POI lifecycle
   classifier used those bounds as the containment fence for
   `VALID_ACTIVE_SETUP_POI`, so the right OB was often dropped before ranking.

The repair promotes the already-built shadow machinery (displacement scorer,
causal-necessity protected-point algorithm, OB-origin admission gate) onto the
canonical path via three env-var-backed flags, each shipable independently
behind the flag. Commit 3 cut over all three defaults to ON. Legacy behaviour
remains opt-in via env (set the flag to `0`).

## Commits

| Commit | Subject |
|--------|---------|
| 07f74f4 | feat(perception): wire displacement scoring into canonical engine_v2 (WP-SMC-10/1) |
| 13aaf5b | feat(perception): causal protected-point selection with abstention fallback (WP-SMC-10/2) |
| 0c3acc0 | feat(perception): causal OB-origin gate + flag cutover (WP-SMC-10/3) |

## Core Files

| File | Purpose |
|------|---------|
| `smc_desk/perception/causal_repair_flags.py` | Env-var-backed feature flags (read at call time; defaults ON post-cutover). |
| `smc_desk/perception/engine_v2.py` | Calls `_enrich_breaks_with_displacement` after FVG detection so confirmed breaks carry real `displacement_strength` and `metadata['displacement']`. |
| `smc_desk/perception/displacement.py` | (pre-existing) `score_break_displacement` -- the canonical scorer, now actually invoked on the canonical path. |
| `smc_desk/perception/structure.py` | `_confirm_break` threads `candles`/`swings`/`current_time` into the call chain; when the flag is ON runs `protected_point.select` and overrides the protected assignment only when the causal pick maps to an actual SwingObject. Full selection always recorded in `brk.metadata['protected_point_selection']`. |
| `smc_desk/structure/protected_point.py` | (pre-existing) causal-necessity algorithm; now promoted onto the canonical path with abstention fallback. |
| `smc_desk/perception/order_blocks.py` | `_admit_origin_cluster` admits a cluster as an OB only when the linked break carries a displacement profile of at least moderate quality and a non-empty departure trace. Admission record always attached. |
| `tests/test_wp_smc10_displacement_wiring.py` | 6 tests (flag default on, strong-displacement scoring, probe skip, scorer-error fallback, flag-gated analyze call/no-call). |
| `tests/test_wp_smc10_causal_protected_point.py` | 10 tests (flag default on, adapter, match in/out/direction/str, flag-gated confirm metadata + legacy fallback + error swallow). |
| `tests/test_wp_smc10_causal_ob_origin_gate.py` | 7 tests (gate default on, disabled admits anything, no-profile reject, no-departure reject, weak reject, moderate accept, strong accept). |
| `tests/test_wp0022_smc_detector_rebuild.py` | Two existing detector-unit tests updated to supply the displacement profile that engine_v2 would have produced, so the OB/FVG/inducement wiring assertions hold under the cutover. Comment in each test explains the contract. |

## What Did NOT Change

- **Authority contract.** `signal_allowed: False`, `execution: disabled`,
  `ai_may_override_ineligible_candidate: False`. No signal, paper, live, or
  execution authority was created.
- **AI brain.** No change to evidence-grounding, the validator, or the
  `NARRATIVE_NAKED_CLAIM` / `EVIDENCE_ID_NOT_GROUNDED` contracts. The AI is
  still constrained to select from the certified evidence set -- but that set
  is now correct.
- **Constitution V1 / V2 YAML.** Untouched. The repair honours V2's
  `break_lifecycle` (wick → body → displacement → accept) and V1's
  `forbidden_shortcuts` entry on protected-point selection.
- **Perception config surface.** The frozen `PerceptionRuntimeConfig` (pydantic
  `extra=forbid`) is untouched. Flags live in a separate, lightweight module.

## Decision Log / Out of Scope

- **Fix D -- BR-004-006 contested decisions (deeper-OB priority, displacement
  thresholds).** Still `PROPOSED` in
  `foundation_programme/pre_outputs/08_constitution_adjudication.md`. With
  displacement now live, the depth tiebreak at `causal_poi_authority.py:683`
  is reached far less often (displacement now breaks ties first), so urgency
  drops -- but the system continues to apply a `PROPOSED` rule as doctrine.
  Adjudication is a doctrine action for the project owner, not code.
- **Promoting `experimental_break_engine.py`** (VGM-001/002/005 -- wick-then-body
  displacement gate, first-break-not-BOS, bounded retrieval loop) onto the
  canonical path. Separate, larger work package.
- **Replacing legacy `_confirm_break`'s recency assignment** in the flag-OFF
  code path. Legacy remains the fallback of last resort (abstain, not-a-swing,
  error). Reversible.

## Verification

- **Full suite:** `python -m pytest -q` → **1077 passed, 1 skipped** in 347s
  (was 1054 / 1 before WP-SMC-10; +23 new, no regressions).
- **Governance consistency:** `python tools/check_governance_consistency.py` →
  `GOVERNANCE CONSISTENCY: PASS`.
- **Authority boundaries:** `python tools/check_authority_boundaries.py` →
  `AUTHORITY BOUNDARY CHECK: PASS. Scanned 123 files across 4 active packages + 2 canonical tools. No forbidden legacy imports found.`

## Reversibility

Each of the three flags can be turned off independently by setting the env var
to `0`:

- `SMC_CANONICAL_DISPLACEMENT_SCORING=0` → breaks carry legacy `0.0` displacement.
- `SMC_CAUSAL_PROTECTED_POINT=0` → protected_* uses legacy recency assignment.
- `SMC_CAUSAL_OB_ORIGIN_GATE=0` → every geometric candidate is admitted as an OB.

The cutover (defaults ON) can be reverted in one line per flag in
`causal_repair_flags.py`.