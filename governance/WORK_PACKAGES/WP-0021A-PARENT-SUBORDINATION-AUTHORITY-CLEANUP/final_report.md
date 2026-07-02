# WP-0021A Parent Subordination And Authority Cleanup

Status: `PASS_ACCEPTED`

The two user-provided briefs were reconciled against the actual repository.

The strategy correctness audit is correct: WP-0021 improved the report/watch
language, but the deeper structure engine still needs Stage A/B/C work before
the system can claim professional-grade structure reading at the detector level.

The WP-0021A brief was also accurate: the current code already contains the
parent-subordination repair in `structure_hierarchy.py`, plus the `final_state`
headline in `orchestrator_v2.py`.

## Confirmed Present

- `build_mtf_structure_hierarchy()` builds HTF to LTF.
- Child timeframe hierarchy receives `parent_context`.
- A child opposing break can only flip external bias if its confirmed body
  close breaches the parent protected level.
- Otherwise the child break is recorded as an internal retracement.
- `ColleagueBrainV2Result.to_dict()` now exposes both:
  - `final_action`: authority stamp, still observe-only.
  - `final_state`: trader-story headline such as
    `WATCH_BEARISH_RETRACE_TO_SUPPLY`.
- Regression tests exist in
  `tests/decision/test_btc_supply_retrace_regression.py`.

## Additional Cleanup Done

The authority-boundary checker was red because `wp0020_gauntlet.py` directly
imported the legacy `analyze_dataframe` engine for annotation-only rendering.
That was not decision authority, but it still violated the project boundary.

Fix:

- Added `run_legacy_annotation_analysis()` to
  `smc_desk/colleague/legacy_comparison.py`.
- Updated `smc_desk/colleague/wp0020_gauntlet.py` to call that adapter.
- Updated `tests/test_smc_annotation_correctness.py` to patch the adapter
  instead of the old forbidden gauntlet symbol.

The checker now passes without weakening the policy.

## Validation

- WP-0021 + WP-0021A focused tests: `10 passed`.
- Gauntlet/annotation/thesis focused tests after boundary cleanup: `13 passed`.
- Authority boundary check: PASS.
- Compileall on touched files: PASS.
- Full pytest: `516 passed, 1 skipped`.

## Authority Boundary

No edge, paper execution, live execution, or capital-risk authority was created.
The repair makes the system stricter and clearer, not more eager.

## Remaining Truth

The base detector still needs the larger Stage A/B/C structure rebuild:

- real internal-break track in `structure.py`
- BOS-anchored CHoCH
- inducement detector
- prominence-ranked swing hierarchy
- equal highs/lows liquidity pools
- sweep/reclaim detector
- certified order-block detector
- premium/discount enforcement in watch states

## Next Work Package

WP-0022 is now defined as the Stage A/B SMC detector rebuild. It should fix the
base perception layer before more live-signal work is trusted: internal and
external breaks must be separate detector outputs, CHoCH must be tied to the
protected swing created by the last BOS, and trader primitives such as
inducement, sweeps, equal highs/lows, order blocks, and POI-grade FVGs must
exist as real objects rather than narrative guesses.
