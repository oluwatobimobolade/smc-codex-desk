# WP-0016 Runtime Config Split - Final Report

Date: 2026-06-26

## Objective

Migrate runtime rule loading away from the mixed
`PERCEPTION_ONTOLOGY_V2.yaml` monolith while preserving compatibility for older
rule files.

## Implementation

- Added split runtime config models in `smc_desk/rules.py`:
  - `PerceptionDetectorConfig`
  - `StrategyExecutionConfig`
- Switched default `RuleConfig` loading to:
  - `specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml`
  - `specs/STRATEGY_EXECUTION_CONFIG_V1.yaml`
- Kept compatibility adapters for:
  - old monolithic ontology/rule files;
  - detector-only split files plus default strategy config;
  - strategy-only split files plus default detector config;
  - legacy JSON strategy/rule files.
- Updated the ontology authority audit so it reports runtime migration truth,
  not only split-contract readiness.
- Added regression coverage for default split runtime loading and legacy
  compatibility.
- Fixed the WebBridge HTTP wrapper timeout path so long TradingView OHLCV
  attempts are allowed to report their own timeout payload instead of being
  cut off by the local wrapper.

## Audit Result

Output:

- `reports/current/RUNTIME_CONFIG_SPLIT_WP0016.json`
- `reports/current/RUNTIME_CONFIG_SPLIT_WP0016.md`

Status:

- `runtime_config_migrated_to_split_contracts`

## Live BTCUSDT Shadow Result

The BTCUSDT live-shadow path was attempted after the migration.

Result:

- `NO_VALID_LIVE_TRADE`
- `market_edge_claimed=false`
- `paper_execution_enabled=false`
- `live_execution_enabled=false`

Reason:

- TradingView visual screenshots succeeded through Kimi WebBridge.
- TradingView OHLCV fetch timed out.
- Binance REST live OHLCV failed with DNS resolution error.
- Browser-side Binance fetch also failed.
- Therefore the full engine did not receive verified, closed, current BTCUSDT
  candles and correctly refused to produce an executable signal.

Evidence:

- `analysis_runs/live_shadow_btcusdt_wp0016_20260626/summary.json`
- `analysis_runs/live_shadow_btcusdt_wp0016_20260626_retry/summary.json`
- `analysis_runs/live_btcusdt_wp0016_20260626/visual_only/screenshots/`
- `reports/current/BTCUSDT_LIVE_SHADOW_WP0016_REPORT.md`

## Honest Interpretation

WP-0016 successfully fixes the runtime config authority problem. It does not
prove predictive edge, does not enable paper/live execution, and does not turn
visual TradingView screenshots into market-data authority.

The live BTCUSDT test exposed a separate operational risk: current live OHLCV
acquisition can still fail even when the browser chart is visible. That must be
handled as the next reliability gate.
