# WP-0037 Active Range + AI Self-Review Repair

Timestamp: 2026-06-29T17:33:00Z

## Scope

Fixed the issue where the live AI SMC path could reason from broad OHLCV summary highs/lows instead of a trader-grade active dealing range.

The goal was not to make the system force trades. The goal was to make the system more structurally correct:

- active ranges must come from recent protected swing structure;
- broad dataset/window extremes must be rejected;
- the AI must self-review its range, POI, annotation, and refusal state;
- official annotations must remain watch-only unless the validated setup is truly trade-ready.

## What Was Built

Added:

- `smc_desk/decision/active_range_resolver.py`
- `tests/test_wp0037_active_range_authority.py`

Updated:

- `smc_desk/brain/smc_evidence_pack_builder.py`
- `smc_desk/brain/ai_smc_trader_brain.py`
- `smc_desk/brain/ai_smc_consistency_validator.py`
- `smc_desk/brain/prompt_system/prompt_builder.py`
- `tools/run_live_ai_smc_full_system.py`
- WP-0034/WP-0035/WP-0036 tests where fixture contracts needed the new self-review/range authority fields.

## Core Behavior

The new active range resolver:

- detects recent swing pivots;
- selects the latest alternating swing high/low pair that brackets current price;
- rejects unresolved, too-narrow, and too-wide ranges;
- records `source=protected_swing_pair`;
- explicitly forbids `ohlcv_summary_high_low`, dataset extremes, and raw visible-window extremes.

The evidence pack now carries:

```text
active_range_authority
```

The AI decision schema now carries:

```text
active_range.source
active_range.range_id
active_range.protected_high
active_range.protected_low
active_range.width_atr
active_range.max_allowed_width_atr
self_review
```

The validator now hard-fails:

- active ranges sourced from OHLCV summary highs/lows;
- active ranges that disagree with `active_range_authority.selected_range`;
- active ranges wider than allowed ATR limits;
- failed AI self-review checks;
- `TRADE_PLAN_READY` outputs without completed self-review.

The prompt OS now requires:

- use `evidence_pack.active_range_authority.selected_range`;
- refuse/review if the range is unresolved or visibly wrong;
- run a second-pass challenge against broad/stale/summary-sourced ranges;
- remove unsupported annotation levels before official output.

## Live Test

Final live run:

`/Users/tobimobolade/smc-codex-desk/analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260629_173159/`

Results:

- BTCUSDT: `PASS`, `VALIDATED`, `WATCH_ONLY`
  - selected range: 1H bullish structural range `58,850.0-60,758.3`
  - width: `3.4719 ATR`
- SOLUSDT: `PASS`, `VALIDATED`, `WATCH_ONLY`
  - selected range: 1H bullish structural range `72.09-74.55`
  - width: `2.0271 ATR`
- XAUUSD: `PASS`, `VALIDATED`, `WATCH_ONLY`
  - selected range: 1H bearish structural range `4038.1001-4090.3999`
  - width: `2.859 ATR`

All three had:

- no hard validation issues;
- no trade box;
- no entry;
- no stop loss;
- no take profit.

This is the correct behavior because the run still had no validated sweep/displacement/active POI promoted into execution readiness.

## Validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_wp0037_active_range_authority.py tests/test_wp0035_ai_brain_integration.py tests/test_wp0036_prompt_operating_system.py -q
.venv/bin/python -m compileall smc_desk/decision/active_range_resolver.py smc_desk/brain/smc_evidence_pack_builder.py smc_desk/brain/ai_smc_trader_brain.py smc_desk/brain/ai_smc_consistency_validator.py smc_desk/brain/prompt_system/prompt_builder.py tools/run_live_ai_smc_full_system.py
.venv/bin/python tools/run_live_ai_smc_full_system.py --symbols BTCUSDT SOLUSDT XAUUSD --output-root analysis_runs
.venv/bin/python -m pytest tests/test_wp0034_ai_smc_trader_brain.py tests/test_wp0035_ai_brain_integration.py tests/test_wp0036_prompt_operating_system.py tests/test_wp0037_active_range_authority.py -q
git diff --check -- smc_desk/decision/active_range_resolver.py smc_desk/brain/smc_evidence_pack_builder.py smc_desk/brain/ai_smc_trader_brain.py smc_desk/brain/ai_smc_consistency_validator.py smc_desk/brain/prompt_system/prompt_builder.py tools/run_live_ai_smc_full_system.py tests/test_wp0034_ai_smc_trader_brain.py tests/test_wp0035_ai_brain_integration.py tests/test_wp0036_prompt_operating_system.py tests/test_wp0037_active_range_authority.py
.venv/bin/python -m pytest -q
```

Results:

- WP-0037 focused suite: 5 passed.
- WP-0037 + prompt focused suite: 17 passed.
- WP-0034 + WP-0035 + WP-0036 + WP-0037: 51 passed.
- Full suite: 642 passed, 1 skipped.
- Diff check for touched files: clean.
- Final live run: BTCUSDT/SOLUSDT/XAUUSD all `PASS`, `VALIDATED`, `WATCH_ONLY`, zero hard issues.

## Remaining Cautions

- This improves structural correctness and prevents broad-range hallucination. It does not prove market edge.
- The local live provider is still conservative and observe-only.
- The next improvement is to promote validated sweep, displacement, active POI, and liquidity-sequence candidates into the AI brain payload so it can distinguish `WAIT_FOR_POI`, `POI_TOUCHED_AWAIT_CONFIRMATION`, `MISSED_TRADE_NO_CHASE`, and true `TRADE_PLAN_READY` more precisely.
- No external LLM API was called.
- No paper/live execution capability was added.

## Verdict

WP-0037 is implemented.

The live AI path can no longer silently use broad OHLCV summary ranges as its active dealing range. It now receives a structural range authority, self-reviews the decision, and is blocked by the validator if it tries to drift back into summary-sourced or oversized market geometry.
