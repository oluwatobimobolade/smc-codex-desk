# WP-0017C Baseline Reconciliation - Final Report

Date: 2026-06-26

## Objective

Reconcile the attached other-AI/V4 transfer audit with the actual local
workspace, repair stop-the-line defects, and establish the current verified
baseline before any further strategy expansion.

## What Was Confirmed

The attached audit was correct about two local issues:

- `smc_desk/perception/fvg.py` did not compile because of a stray indentation
  fragment.
- `governance/NEXT_ACTIONS.yaml` contained duplicate keys in the first action
  item, collapsing two work items into one ambiguous YAML mapping.

The local repo had also moved beyond the older WP-0016 state:

- `CURRENT_STATE.yaml` referenced WP-0012A/B/C/D and WP-0017A/B work.
- Evidence files recorded inconsistent test baselines: 389, 405, 426, and 453.
- The validation registry still pointed at the older WP-0016 baseline.

## Repairs

- Removed the local shadow `FairValueGapObject` class from
  `smc_desk/perception/fvg.py` and used the canonical ontology object.
- Fixed the syntax/indentation blocker in `smc_desk/perception/fvg.py`.
- Fixed bearish FVG mitigation math so gap size is positive
  (`price_high - price_low`).
- Reordered FVG lifecycle handling so body-close invalidation wins before
  full/partial mitigation and each FVG enters only one terminal state.
- Added a regression in `tests/stress_tests/test_C_minimal_pairs.py` proving a
  candle that both touches and closes through a bullish FVG invalidates it once
  instead of creating conflicting terminal events.
- Split the malformed first item in `governance/NEXT_ACTIONS.yaml` into
  `WP-0012A` and `WP-0001-A`.
- Added duplicate-key detection for governance YAML in
  `tests/test_governance_foundation.py`.

## Verified Current Baseline

- Git HEAD: `c54860a3b00a869d67a4b781b7fb9cae16c7b5c8`
- Python: `Python 3.14.5`
- Working tree: dirty, 98 `git status --short` lines at final verification time.
- Compileall: passed.
- Full pytest: `469 passed, 1 skipped in 26.40s`.
- Governance consistency: passed.
- Strict duplicate-key YAML parse: passed.
- JSON parse: passed.
- Timeframe/replay focused suite: `19 passed, 1 skipped in 1.57s`.

## Honest Interpretation

The local workspace is now green again, but it is not a clean release package
yet because the working tree remains dirty and historical evidence files still
preserve older baselines. Those older baselines are useful provenance, not the
current truth.

The current active truth is the WP-0017C baseline above. No strategy edge,
paper execution, live execution, or capital-risk authority is created by this
repair.

## Next Gate

Freeze a clean foundation release only after:

- the dirty working tree is intentionally staged or archived;
- WP-0012A/B/C/D and WP-0017A/B evidence is either promoted into formal work
  packages or explicitly marked as supporting evidence;
- live OHLCV route smoke is repeated under the current green baseline;
- release hashes and transfer manifest are regenerated from the current files.
