# Baseline Reconciliation WP-0017C Report

Date: 2026-06-26

## Executive Verdict

The attachment was right to stop the line: the local repo had a real FVG
compile blocker and a malformed `NEXT_ACTIONS.yaml` entry. Both are now fixed.

Current verified baseline:

- `469 passed, 1 skipped`
- compileall passed
- governance consistency passed
- strict duplicate-key YAML parse passed
- no live/paper execution authority added

## Reconciled Claims

Older evidence files mention multiple baselines:

- `389` tests from pre-live-integration/WP-0016 era
- `405` tests from WP-0012A evidence
- `426` tests from WP-0012A-D evidence
- `453` tests from an audit verdict file

Those are historical claims. The current local truth after repair is:

- Git HEAD: `c54860a3b00a869d67a4b781b7fb9cae16c7b5c8`
- Python: `Python 3.14.5`
- Working tree: dirty, 98 status lines
- Full pytest: `469 passed, 1 skipped in 26.40s`

## Repairs Made

- Fixed `smc_desk/perception/fvg.py` syntax and indentation.
- Removed the duplicate local FVG model so the canonical ontology
  `FairValueGapObject` owns `mitigation_percent` and `mitigated_price`.
- Fixed bearish FVG mitigation percent math.
- Prevented contradictory FVG terminal lifecycle transitions.
- Added a regression for FVG invalidation precedence.
- Repaired `governance/NEXT_ACTIONS.yaml`.
- Added a governance YAML duplicate-key regression test.

## Remaining Risks

- This is a green dirty-working-tree baseline, not a clean release tag.
- WP-0012A/B/C/D and WP-0017A/B are referenced in current governance but do not
  yet have the same formal work-package folders as WP-0011 through WP-0016.
- Live OHLCV reliability still needs a fresh route smoke under this repaired
  baseline.
- No edge or execution authority is proven by this reconciliation.
