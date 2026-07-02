# WP-0034 AI SMC Trader Brain

Timestamp: 2026-06-29T14:11:56Z

## Scope

Implemented the local-first WP-0034 vertical slice:

- evidence pack builder;
- strict AI SMC decision schema and reasoning-order contract;
- injected AI brain adapter with no API ownership;
- consistency validator that blocks unsupported model claims;
- clean multi-timeframe chart-pack renderer;
- official validated AI annotation renderer;
- AI SMC thesis writer;
- focused regression tests for the known failure modes.

This work is additive. It does not change live execution, paper execution, account risk, leverage, or the existing no-API/local-first posture.

## What Was Built

### Evidence Pack Builder

Added `smc_desk/brain/smc_evidence_pack_builder.py`.

The evidence pack now gathers:

- local OHLCV summaries and candle windows;
- clean chart image manifests and hashes;
- detector candidates marked as `candidate_only`;
- doctrine/profile constraints;
- provenance hashes;
- an explicit authority contract stating that the pack is evidence-only.

It does not produce `official_state`, entry, stop loss, take profit, or signal authority.

### AI SMC Trader Brain Schema

Added `smc_desk/brain/ai_smc_trader_brain.py`.

The schema requires the AI or manual model workspace to output strict JSON with:

- `official_state`;
- `setup_grade`;
- `direction`;
- `setup_model`;
- `bias_summary`;
- `active_range`;
- `liquidity_story`;
- `displacement_assessment`;
- `active_poi`;
- `entry_plan`;
- `stop_loss_plan`;
- `target_plan`;
- `rr_status`;
- `invalidation`;
- `annotation_plan`;
- `final_thesis`.

The locked reasoning order is:

1. daily context
2. 4H context
3. 1H context
4. active range
5. premium/discount
6. obvious liquidity
7. swept liquidity
8. displacement quality
9. active POI
10. entry model
11. entry readiness
12. structural invalidation
13. model-completion liquidity target
14. RR minimum 3
15. final state

The `AISMCTraderBrain` adapter accepts an injected completion function only. It does not call an external API.

### Consistency Validator

Added `smc_desk/brain/ai_smc_consistency_validator.py`.

The validator converts unsupported claims to `REVIEW_REQUIRED`. It checks:

- locked reasoning order;
- final direction vs bias;
- no 1m official entry/refinement;
- watch/review charts cannot carry entry, SL, TP, or trade boxes;
- trade-plan charts require `TRADE_PLAN_READY`;
- claimed liquidity sweep must match sweep evidence;
- claimed displacement must match structure/FVG evidence;
- active POI must match POI/order-block/FVG evidence;
- stop loss must equal structural invalidation;
- bearish targets must be below entry and bullish targets above entry;
- target must match model-completion liquidity;
- trade-ready RR must be at least 3.0;
- official label-count budget.

If validation fails, the official decision is rewritten to review-only form with no trade box or executable levels.

### Clean MTF Chart Pack

Added `smc_desk/rendering/clean_mtf_chart_pack.py`.

This renders candle-only evidence charts for 1D, 4H, 1H, 15m, and optional 5m. These charts contain no engine labels, no detector objects, and no trade boxes.

### Official AI Annotation Renderer

Added `smc_desk/rendering/smc_trader_annotation_renderer.py`.

This renderer:

- accepts only validated AI decisions;
- uses only the validated annotation plan;
- keeps debug detector charts separate;
- marks debug scenes with `DEBUG ONLY - NOT OFFICIAL TRADE THESIS`;
- enforces max official labels:
  - context chart: 5;
  - watch/review chart: 7;
  - trade-plan chart: 8;
- draws entry/SL/TP only when `TRADE_PLAN_READY`.

### AI Thesis Writer

Added `smc_desk/colleague/smc_thesis_ai_v1.py`.

The thesis writer consumes the validation result and writes the story in the required sequence. Review-required decisions cannot show a trade box.

## Tests Added

Added `tests/test_wp0034_ai_smc_trader_brain.py` with coverage for:

- evidence pack does not decide;
- detectors remain candidates only;
- AI brain prompt receives chart images and structured data;
- reasoning order enforcement;
- strict output schema;
- liquidity sweep validation;
- displacement validation;
- target/liquidity validation;
- wrong-side target rejection;
- structural SL/invalidation validation;
- RR >= 3 enforcement;
- watch chart has no trade box;
- trade chart has entry/SL/TP/RR only when ready;
- official renderer uses validated AI annotation plan;
- debug chart is separate;
- clean annotation max label count;
- no 1m official entry;
- thesis writer uses validated boundary.

## Validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_wp0034_ai_smc_trader_brain.py -q
.venv/bin/python -m pytest tests/test_wp0031_doctrine_profile.py tests/test_wp0031_narrative_and_charts.py tests/test_debug_chart_not_used_as_official_thesis.py tests/test_trade_box_only_when_trade_plan_ready.py tests/test_watch_state_blocks_trade_box.py -q
.venv/bin/python -m pytest -q
```

Results:

- WP-0034 focused suite: 18 passed.
- Nearby doctrine/official-chart suite: 16 passed.
- Full suite: 609 passed, 1 skipped.

## Remaining Cautions

- This is not a trading-edge proof. It is a correctness boundary that prevents unsupported SMC claims from becoming official.
- The AI brain is model-call agnostic. Actual model/manual analysis output still needs to obey the schema and pass validation.
- The repo still has a large dirty worktree from previous work. This package did not revert or clean unrelated files.
- Live/paper execution remains disabled and out of scope.

## Verdict

WP-0034 is implemented as a local-first, no-API decision boundary.

The system can now package evidence, accept a strict SMC trader-brain JSON thesis, validate every important claim against evidence and doctrine, render only validated official annotations, and write a thesis without letting raw detector noise or unsupported AI claims become trade authority.
