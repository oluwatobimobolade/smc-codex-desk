# WP-0021A Parent Subordination And Authority Cleanup

Status: `PASS_ACCEPTED`

I reconciled the two user-provided briefs against the actual repo.

Confirmed:

- The parent-subordination structure repair exists.
- The BTC supply-retrace regression exists and passes.
- `final_state` is now a first-class output beside `final_action`.

Fixed:

- Removed the direct legacy `analyze_dataframe` import from the active
  WP-0020 gauntlet.
- Routed annotation-only legacy analysis through
  `smc_desk/colleague/legacy_comparison.py`.
- Updated the annotation test to patch the new adapter.

Validation:

- WP-0021/WP-0021A focused tests: `10 passed`
- Boundary check: PASS
- Focused gauntlet/annotation set: `13 passed`
- Full pytest: `516 passed, 1 skipped`

No execution authority or edge claim was created.

Next:

- WP-0022 is the Stage A/B SMC detector rebuild.
- WP-0023 is the Stage C/D decision wiring, data-depth, and story-renderer pass.
- Do not treat WP-0021A as full detector maturity; it is a verified
  cross-timeframe authority repair.
