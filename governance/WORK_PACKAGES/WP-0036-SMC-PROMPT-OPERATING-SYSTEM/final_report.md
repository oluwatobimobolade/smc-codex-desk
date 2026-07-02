# WP-0036 SMC Prompt Operating System

Timestamp: 2026-06-29T15:07:00Z

## Scope

Implemented a versioned prompt operating system for the AI SMC trader brain.

The problem was that WP-0034/WP-0035 gave the brain evidence, schema, validation, provider injection, and official pipeline wiring, but the prompt itself was still a single generic JSON contract. The AI mind needs explicit doctrine, safeguards, refusal discipline, target/SL rules, and annotation rules before it reasons.

## What Was Built

Added `smc_desk/brain/prompt_system/`.

Prompt modules:

- `master_identity_prompt.py`
- `smc_doctrine_prompt.py`
- `reasoning_order_prompt.py`
- `evidence_guardrail_prompt.py`
- `trade_readiness_prompt.py`
- `target_sl_prompt.py`
- `annotation_prompt.py`
- `json_schema_prompt.py`
- `prompt_contract.py`
- `prompt_registry.py`
- `prompt_builder.py`

Each prompt module has:

- name;
- version;
- purpose;
- text;
- required output schema;
- stable hash.

The registry exposes:

- prompt system name;
- prompt system version;
- combined prompt-system hash;
- module metadata;
- optional full text.

## Core Doctrine Added

The prompt stack now explicitly enforces:

- top-down reasoning: Daily -> 4H -> 1H -> 15M -> optional 5M;
- 1M is forbidden for official entries;
- no account risk, leverage, liquidation, position sizing, partial closes, breakeven, or trailing decisions;
- detector outputs are candidates, not truth;
- external structure has authority over internal noise;
- being correct about direction is not enough;
- weak setups should become watch/no-trade/review states;
- targets must be model-completion liquidity, not nearby random levels;
- stop loss must equal structural invalidation;
- RR must be at least 1:3 for `TRADE_PLAN_READY`;
- watch charts cannot show entry, SL, TP, RR, or trade boxes;
- output must be strict JSON only.

## Integration Changes

Updated `smc_desk/brain/ai_smc_trader_brain.py`:

- `build_ai_smc_prompt()` now delegates to the layered prompt OS.
- Official states were expanded to include stricter refusal/watch vocabulary:
  - `WAIT_FOR_POI`
  - `VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY`
  - `MISSED_TRADE_NO_CHASE`
  - `INDUCEMENT_RISK`
  - `INVALIDATED_REMAP`

Updated `smc_desk/colleague/orchestrator_v3.py`:

- final reports now include a prompt registry manifest with prompt system version/hash and module hashes.

Updated `smc_desk/brain/__init__.py`:

- exported prompt registry helpers.

## Tests Added

Added `tests/test_wp0036_prompt_operating_system.py`.

Required tests covered:

- `test_prompt_contains_reasoning_order`
- `test_prompt_contains_user_doctrine`
- `test_prompt_forbids_1m_entries`
- `test_prompt_forbids_risk_or_position_sizing`
- `test_prompt_requires_model_completion_target`
- `test_prompt_requires_structural_invalidation`
- `test_prompt_requires_no_trade_for_weak_setups`
- `test_prompt_requires_watch_state_without_trade_box`
- `test_prompt_requires_strict_json_schema`
- `test_prompt_version_hash_changes_on_edit`

Additional coverage:

- prompt registry has versioned modules and hashes.

## Validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_wp0036_prompt_operating_system.py -q
.venv/bin/python -m pytest tests/test_wp0034_ai_smc_trader_brain.py tests/test_wp0035_ai_brain_integration.py tests/test_wp0036_prompt_operating_system.py -q
.venv/bin/python -m pytest -q
git diff --check -- smc_desk/brain smc_desk/colleague/orchestrator_v3.py tests/test_wp0036_prompt_operating_system.py
```

Results:

- WP-0036 focused suite: 11 passed.
- WP-0034 + WP-0035 + WP-0036: 45 passed.
- Full suite: 636 passed, 1 skipped.
- Diff check for WP-0036 scope: clean.
- Prompt registry smoke check: passed.

## Remaining Cautions

- Prompts guide the AI mind; they do not prove the model will reason correctly on real charts.
- The validator remains the authority boundary after the AI responds.
- Real quality still requires adjudicated gold-chart evaluation.
- No API was called and no execution capability was added.

## Verdict

WP-0036 is implemented.

The AI brain now has a prompt operating system: versioned, hashable, test-covered doctrine and guardrails that tell the AI how to think before it produces the strict JSON decision. This makes the brain stricter, more auditable, and less likely to force weak SMC trade plans.
