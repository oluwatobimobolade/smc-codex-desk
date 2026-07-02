# WP-0038 AVAX/EURNZD Repair Pack

Timestamp: 2026-06-29T23:12:00Z

## Scope

Fixed the issues found during the AVAXUSDT and EUR/NZD runs without adding execution authority or pretending the system has a proven edge.

This work package is about correctness of perception, chart communication, provider evidence, forex handling, and validation downgrades.

## Repairs Completed

- Chart label overlap: official annotation labels at the same price now get separated instead of stacking on top of each other.
- Chart-image evidence: evidence packs can embed chart images as base64, and `LLMCompletionRequest` exposes both image paths and image bytes for local/vision providers.
- Manual provider export: `ManualJSONProvider` is exported from `smc_desk.brain`.
- Session context: session high/low now uses the latest UTC day and current session only, not many historical days merged together.
- Active range priority: active-range resolution now prefers 4H before 1H by default.
- Perception wiring: orchestrator v3 auto-runs `PerceptionEngineV2` when detector candidates are not supplied.
- Optional TradingView visual stage: WP-0035 has an optional Kimi/TradingView capture stage, disabled by default.
- Thesis formatting: empty POI/displacement fields no longer render as ugly `none none` / `None None` text.
- Direction/range consistency: validator now warns when final direction conflicts with active-range direction.
- Forex depth profile: forex pairs use a separate, more realistic minimum context-depth profile.
- Editable install/imports: added `pyproject.toml` and installed package editable so `tools/` can import `smc_desk` from outside the repo.
- Gold-set honesty: added `tools/audit_ai_smc_gold_readiness.py`; it reports `INSUFFICIENT_GROUND_TRUTH` instead of inventing accuracy.
- Trade-ready honesty: added `tools/replay_trade_ready_cases.py`; it scans real run artifacts for validated `TRADE_PLAN_READY` instead of inferring from synthetic tests.
- Depth downgrade safety: context-depth downgrades now use the validator's shared trade-plan stripping path.
- Live route correctness: `tools/run_live_ai_smc_full_system.py` no longer routes every non-USDT symbol through XAU/GC. Crypto goes to Binance USD-M futures, XAUUSD goes to the gold proxy, forex pairs go to Yahoo FX tickers, unsupported symbols fail loudly.
- Conservative-provider bias repair: HTF consensus remains final bias. Active-range direction is map context only unless HTF consensus is mixed; conflicts are surfaced as validator warnings.
- Forex perception gap repair: recognized forex pairs trim detector input to the latest contiguous trading segment so weekend/session closures do not disable the perception bridge. Crypto gap guards remain strict.

## Files Added

- `tests/test_wp0038_avax_eurnzd_repairs.py`
- `tools/audit_ai_smc_gold_readiness.py`
- `tools/replay_trade_ready_cases.py`
- `pyproject.toml`

## Files Updated

- `smc_desk/brain/ai_smc_consistency_validator.py`
- `smc_desk/brain/smc_evidence_pack_builder.py`
- `smc_desk/brain/llm_provider.py`
- `smc_desk/brain/__init__.py`
- `smc_desk/colleague/orchestrator_v3.py`
- `smc_desk/colleague/smc_thesis_ai_v1.py`
- `smc_desk/data/historical_backfill.py`
- `smc_desk/decision/active_range_resolver.py`
- `smc_desk/gauntlet/wp0035_ai_brain_gauntlet.py`
- `smc_desk/rendering/smc_trader_annotation_renderer.py`
- `smc_desk/session.py`
- `tools/run_live_ai_smc_full_system.py`

## Live Evidence

Successful AVAXUSDT/EURNZD smoke before the later Binance DNS outage:

`/Users/tobimobolade/smc-codex-desk/analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260629_230022/`

- AVAXUSDT: `PASS`, `VALIDATED`, `WATCH_ONLY`, no hard issues.
- EURNZD: `PASS`, `VALIDATED`, `WATCH_ONLY`, no hard issues.
- Both used embedded chart images and auto perception.

Corrected EURNZD smoke after the HTF-bias and forex-session-gap repairs:

`/Users/tobimobolade/smc-codex-desk/analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260629_230943/`

- EURNZD: `PASS`, `VALIDATED`, `WATCH_ONLY`.
- Direction/final bias: bullish from Daily/4H/1H consensus.
- Active range: 4H bearish map `2.0147199630737305-2.0224499702453613`.
- Validator warning correctly surfaced: `direction_conflicts_with_active_range`.
- Perception bridge auto-ran and trimmed forex session gaps:
  - 15m: 5551 original rows -> 89 analyzed rows.
  - 1h: 17260 original rows -> 23 analyzed rows.
  - 4h: 4442 original rows -> 7 analyzed rows.
  - 1d: 516 original rows -> 1 analyzed row.
- No entry, stop loss, take profit, or trade box.

Later AVAX retry:

`/Users/tobimobolade/smc-codex-desk/analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260629_230808/`

- AVAXUSDT failed at the data route due to DNS resolution failure for `fapi.binance.com`.
- This was recorded as a network/data-route failure, not an engine/perception failure.

## Validation

Commands run:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -m pytest tests/test_wp0038_avax_eurnzd_repairs.py -q
.venv/bin/python -m pytest tests/test_wp0034_ai_smc_trader_brain.py tests/test_wp0035_ai_brain_integration.py tests/test_wp0036_prompt_operating_system.py tests/test_wp0037_active_range_authority.py tests/test_wp0038_avax_eurnzd_repairs.py -q
.venv/bin/python -m compileall smc_desk/brain smc_desk/colleague smc_desk/gauntlet tools/audit_ai_smc_gold_readiness.py tools/replay_trade_ready_cases.py tools/run_live_ai_smc_full_system.py tests/test_wp0038_avax_eurnzd_repairs.py
git diff --check -- smc_desk/brain/ai_smc_consistency_validator.py smc_desk/colleague/orchestrator_v3.py smc_desk/brain/smc_evidence_pack_builder.py tools/run_live_ai_smc_full_system.py tools/audit_ai_smc_gold_readiness.py tools/replay_trade_ready_cases.py tests/test_wp0038_avax_eurnzd_repairs.py pyproject.toml
.venv/bin/python /Users/tobimobolade/smc-codex-desk/tools/audit_ai_smc_gold_readiness.py --cases-root /tmp/smc_missing_gold_cases --minimum-cases 20
.venv/bin/python /Users/tobimobolade/smc-codex-desk/tools/replay_trade_ready_cases.py --runs-root /Users/tobimobolade/smc-codex-desk/analysis_runs
.venv/bin/python tools/run_live_ai_smc_full_system.py --symbols AVAXUSDT EURNZD --output-root analysis_runs
.venv/bin/python tools/run_live_ai_smc_full_system.py --symbols EURNZD --output-root analysis_runs
.venv/bin/python -m pytest -q
```

Results:

- WP-0038 focused suite: 15 passed.
- WP-0034 through WP-0038 focused suite: 67 passed.
- Full suite: 658 passed, 1 skipped.
- Diff whitespace check: clean.
- Editable install: succeeded.
- Gold readiness audit: `INSUFFICIENT_GROUND_TRUTH`, 0 adjudicated cases in the missing test root, no weak labels promoted.
- Trade-ready replay audit: scanned 22 real official-decision artifacts, 0 validated `TRADE_PLAN_READY`, edge claim not allowed.

## Remaining Cautions

- AVAX live route is currently dependent on Binance DNS availability. The system correctly records DNS failures as data-route failures.
- EURNZD Yahoo FX data is a chart proxy, not broker/exchange execution data.
- Forex session trimming makes perception usable after market closures, but long-horizon FX detector context is still thinner immediately after a weekend/session reopen.
- No paper/live execution was added.
- No strategy edge or win-rate claim was made.

## Verdict

WP-0038 is implemented.

The AVAX/EURNZD issue pack is fixed as an engineering and truth-boundary repair. The system is stricter, clearer, more honest, and better able to analyze crypto and forex without confusing chart/readability failures, provider evidence gaps, session gaps, or active-range conflicts for trade authority.
