# WP-0035 AI Brain Pipeline Integration

Timestamp: 2026-06-29T14:51:56Z

## Scope

Implemented the integration-and-proof package after WP-0034.

WP-0034 built the evidence pack, strict AI SMC decision schema, validator, and clean annotation boundary. WP-0035 wires that brain into an official pipeline and adds the missing proof surfaces:

- provider abstraction and provider audit;
- official AI-brain orchestrator v3;
- WP-0035 gauntlet wrapper;
- historical backfill/pagination;
- HTF context-depth warnings;
- gold-set loader and evaluator;
- tests proving legacy authority cannot become official output.

No live execution, paper execution, broker integration, position sizing, capital-risk authority, leverage, liquidation-risk logic, partial-close automation, breakeven automation, or trailing automation was added.

## What Was Built

### Provider Boundary

Added `smc_desk/brain/llm_provider.py` and provider adapter package under `smc_desk/brain/providers/`.

The provider contract now carries:

- prompt text;
- evidence pack;
- chart image manifest;
- prompt hash;
- evidence hash;
- provider/model audit fields;
- stub vs real-reasoning flag.

Stub providers are explicitly marked:

```text
NOT_REAL_AI_REASONING - STUB_PROVIDER
```

They cannot produce full `PASS`.

External provider placeholders exist for OpenAI, Claude, and Kimi, but they are inert by default to preserve the current local-first/no-API workflow. Real providers must be injected deliberately.

### Official AI Orchestrator V3

Added `smc_desk/colleague/orchestrator_v3.py`.

The official v3 flow is:

```text
timeframe OHLCV
→ clean MTF chart pack
→ evidence pack
→ AISMCTraderBrain
→ provider completion
→ strict JSON parse
→ consistency validation
→ official AI decision
→ clean annotation renderer
→ AI thesis
→ final report
```

The final report records:

- AI brain used;
- provider/model;
- prompt version;
- prompt/evidence hash;
- chart image paths;
- validation result;
- official state;
- hard issues;
- final chart template;
- execution disabled flags.

Legacy narrative authority is explicitly non-authoritative:

```text
DEBUG_LEGACY_COMPARISON_ONLY
```

Official reports fail if they claim legacy authority as the official decision source.

### WP-0035 Gauntlet

Added `smc_desk/gauntlet/wp0035_ai_brain_gauntlet.py`.

Stages:

1. `09_clean_mtf_chart_pack`
2. `10_smc_evidence_pack`
3. `11_ai_smc_trader_brain`
4. `12_ai_consistency_validation`
5. `13_official_ai_decision`
6. `14_clean_annotation_render`
7. `15_ai_thesis`

### Historical Backfill

Added `smc_desk/data/historical_backfill.py`.

It supports:

- pagination beyond the single Binance 1500-candle page limit;
- closed-candle filtering;
- current forming candle exclusion;
- deduplication;
- monotonic timestamp verification;
- interval-gap verification;
- optional cache manifest;
- context-depth reports.

Minimum depth policy:

- 15m: 1500 closed candles;
- 1h: 1000 closed candles;
- 4h: 500 closed candles;
- 1d: 365 closed candles.

If context is shallow, the system records:

```text
context_depth_warning = true
authority_adjustment = reduce_confidence_or_review_required
```

When `enforce_minimum_depth=True`, v3 downgrades the official decision to `REVIEW_REQUIRED`.

### Gold-Set Evaluation

Added:

- `smc_desk/eval/gold_set_loader.py`
- `smc_desk/eval/ai_smc_gold_evaluator.py`

The loader refuses non-adjudicated cases and cases without human SMC labels.

The evaluator compares AI output to human labels for:

- expected state;
- direction;
- setup grade;
- active POI;
- invalidation;
- target.

This is only the evaluation scaffold. It does not claim perception quality until real adjudicated cases exist.

### Renderer Boundary Tightening

Updated `smc_desk/rendering/smc_trader_annotation_renderer.py` so review-required validator outputs can render only review charts with no trade box.

Updated `smc_desk/brain/ai_smc_consistency_validator.py` so hard validation failures strip entry/stop/target levels from annotation plans.

## Tests Added

Added `tests/test_wp0035_ai_brain_integration.py` with required coverage:

- `test_orchestrator_calls_ai_smc_brain`
- `test_orchestrator_rejects_legacy_authority_for_official_output`
- `test_real_provider_must_be_injected_for_ai_pass`
- `test_stub_provider_marks_run_as_not_real_reasoning`
- `test_ai_brain_receives_chart_images`
- `test_ai_brain_receives_evidence_pack`
- `test_validator_hard_issue_strips_trade_plan`
- `test_official_renderer_uses_validated_ai_annotation_plan`
- `test_watch_state_cannot_draw_trade_box`
- `test_trade_ready_requires_entry_sl_tp_rr`
- `test_historical_backfill_paginates_beyond_1500`
- `test_backfill_excludes_current_forming_candle`
- `test_backfill_verifies_monotonic_timestamps`
- `test_htf_depth_warning_when_daily_shallow`
- `test_gold_set_loader_requires_human_labels`
- `test_gold_evaluator_compares_ai_output_to_human_labels`

## Validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_wp0035_ai_brain_integration.py -q
.venv/bin/python -m pytest tests/test_wp0034_ai_smc_trader_brain.py tests/test_wp0035_ai_brain_integration.py -q
.venv/bin/python -m pytest -q
git diff --check -- smc_desk/brain smc_desk/colleague/orchestrator_v3.py smc_desk/data/historical_backfill.py smc_desk/eval smc_desk/gauntlet tests/test_wp0035_ai_brain_integration.py smc_desk/rendering/smc_trader_annotation_renderer.py
```

Results:

- WP-0035 focused suite: 16 passed.
- WP-0034 + WP-0035 integration suite: 34 passed.
- Full suite: 625 passed, 1 skipped.
- Diff check for WP-0035 scope: clean.
- Import smoke: passed.

## Remaining Cautions

- No external LLM/API was called in this implementation or verification.
- Real provider wiring is injectable but intentionally not activated by default.
- Stub/manual fixed JSON output is marked non-real and cannot produce full PASS.
- The gold-set framework exists, but real perception quality is still unproven until at least 20 adjudicated chart cases are loaded and evaluated.
- This work proves authority wiring and correctness boundaries. It does not prove profitability, edge, or live execution readiness.

## Verdict

WP-0035 is implemented.

The official path can now run through the AI SMC trader brain instead of old narrative authority, with provider audit, chart-image/evidence delivery, strict validation, official decision output, clean annotation rendering, AI thesis generation, historical depth checks, and gold-set evaluation scaffolding.

The system is still observe-only.
