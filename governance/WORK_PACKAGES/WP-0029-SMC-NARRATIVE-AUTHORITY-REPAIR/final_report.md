# WP-0029 SMC Narrative Authority Repair

Date: 2026-06-28

## Objective

Repair the failure class where detector outputs, story charts, debug annotations, and thesis text could all exist at the same time without one final professional SMC authority deciding what the desk officially believes.

The key repair is simple: the system must not turn a watch thesis into an executable-looking trade. Unless the final authority says `TRADE_PLAN_READY`, the official chart must be watch/review only, with no entry, no stop loss, no take-profit box, and no hidden signal.

## Implemented

- Added `smc_desk/colleague/smc_narrative_authority.py` as the final SMC authority layer.
- Added an authority contract that blocks premature trade boxes:
  - `entry = null`
  - `stop_loss = null`
  - `take_profit = []`
  - `show_trade_box = false`
  - `official_trade_plan_state = WATCH_ONLY`
- Added official watch/review chart rendering in `smc_desk/rendering/watch_chart_renderer.py`.
- Added protected trade-plan chart rendering in `smc_desk/rendering/trade_plan_chart_renderer.py`; it raises if requested before `TRADE_PLAN_READY`.
- Added SMC Thesis V5 in `smc_desk/colleague/smc_thesis_v5.py` with the fixed sequence:
  - HTF context
  - liquidity taken
  - displacement
  - active POI
  - current state
  - continuation condition
  - inducement condition
  - invalidation
  - final observe-only state
- Wired the authority into `orchestrator_v2` and the WP-0020 gauntlet.
- Added a new gauntlet stage: `04b_official_charts`.
- Marked legacy annotated charts as debug-only so they cannot become official trade thesis evidence.
- Added `decision.smc_narrative_authority` to decision-grade events.
- Added official state/model/watch-only fields to outcome-contract events and pending outcome contracts.

## Acceptance Tests Added

- `tests/test_smc_narrative_authority_selects_one_model.py`
- `tests/test_move_started_not_chaseable_state.py`
- `tests/test_watch_state_blocks_trade_box.py`
- `tests/test_trade_box_only_when_trade_plan_ready.py`
- `tests/test_official_chart_uses_narrative_authority.py`
- `tests/test_debug_chart_not_used_as_official_thesis.py`
- `tests/test_sol_current_case_wait_for_retrace.py`
- `tests/test_btc_current_case_wait_for_retrace.py`
- `tests/test_inducement_conditions_written.py`
- `tests/test_continuation_conditions_written.py`
- `tests/test_thesis_follows_smc_sequence.py`

## Smoke Runs

- BTCUSDT CSV gauntlet:
  - `analysis_runs/WP0029_NARRATIVE_AUTHORITY_REPAIR_20260628/BTCUSDT`
  - Status: `PARTIAL_PASS`
  - Reason: TradingView visual capture intentionally skipped, so visual layer is `REVIEW_REQUIRED`.
  - Official state: `REVIEW_REQUIRED`
  - Official model: `review_required`
  - Official trade-plan state: `WATCH_ONLY`
  - `show_trade_box`: `false`
  - Final colleague action: `NO_SIGNAL`

- SOLUSDT CSV gauntlet:
  - `analysis_runs/WP0029_NARRATIVE_AUTHORITY_REPAIR_20260628/SOLUSDT`
  - Status: `PARTIAL_PASS`
  - Reason: TradingView visual capture intentionally skipped, so visual layer is `REVIEW_REQUIRED`.
  - Official state: `POI_TOUCHED_AWAIT_CONFIRMATION`
  - Official model: `bearish_continuation_watch`
  - Official trade-plan state: `WATCH_ONLY`
  - `show_trade_box`: `false`
  - Final colleague action: `NO_SIGNAL`

## Validation

- Compile check for changed modules/tests: passed.
- WP-0029 focused tests: `11 passed`.
- Expanded integration tests: `22 passed`.
- Post-ledger affected tests: `17 passed`.
- Full suite after all repairs: `562 passed, 1 skipped`.

## Authority Boundary

- No live execution.
- No paper execution.
- No broker logic.
- No signal promotion.
- No edge claim.
- Capital risk remains `0`.
- Debug charts are comparison evidence only.
- Official thesis must follow the SMC Narrative Authority.

## Remaining Work

- Run a real TradingView visual-capture package when the user wants a browser-backed audit instead of deterministic CSV smoke proof.
- Add future `TRADE_PLAN_READY` promotion criteria only after out-of-sample outcome evidence proves the watch states have measurable edge.
- Continue resolving pending observe-only contracts; do not count them as trade performance.
