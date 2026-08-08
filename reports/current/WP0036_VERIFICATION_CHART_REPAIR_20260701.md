# WP-0036 Verification Chart Repair Report

Date: 2026-07-01  
Run repaired from: `/Users/tobimobolade/Downloads/verification_charts.zip`  
Critique source: `/Users/tobimobolade/.codex/attachments/babff43b-be44-4966-882c-ed5923e667b5/pasted-text.txt`

## Verdict

The previous verification chart set was not acceptable as an official evidence package. The main failure was not cosmetic. It was a truth-layer failure: BTCUSDT could show `TRADE_PLAN_READY` and a trade box while its own labels and thesis said there was no validated sweep/displacement and the state was effectively watch-only.

This repair makes that contradiction impossible through the official validator and renderer path.

## Issues Confirmed

1. BTCUSDT official chart contradiction:
   - Old chart title: `TRADE_PLAN_READY`.
   - Old chart displayed entry/SL/TP trade box.
   - Old labels said no validated sweep/displacement was promoted.
   - Old text said watch-only / wait for confirmation.

2. Clean chart candles were visually broken:
   - The old clean renderer used datetime-width candle bodies, causing block-like candles over larger windows.

3. Context depth was too shallow:
   - Old chart package used about 240 candles.
   - Required minimums are now enforced:
     - 15m: 1500 candles
     - 1h: 1000 candles
     - 4h: 500 candles
     - 1d: 365 candles

4. Verification package was incomplete:
   - The old ZIP only contained images.
   - It did not contain the required JSON truth artifacts.

5. Watch-only path drawings looked too trade-like:
   - AVAX-style watch charts could imply a forecast/entry even when the system had not promoted a trade.

## Code Changes Made

1. `smc_desk/brain/ai_smc_consistency_validator.py`
   - Added hard preconditions for `TRADE_PLAN_READY`.
   - A trade-ready state now requires:
     - bullish or bearish displacement,
     - displacement direction matching final direction,
     - clean or strong displacement quality,
     - `structure_broken=true`,
     - displacement evidence IDs,
     - no watch/no-trade/refusal contradiction in final thesis,
     - no watch/no-trade contradiction in annotation labels.

2. `smc_desk/rendering/smc_trader_annotation_renderer.py`
   - Removed title/subtitle collision.
   - Demoted watch-only path arrows to dashed grey guide paths with no arrow head.
   - Watch charts now label path drawings as `possible path only`.
   - Trade boxes remain blocked unless `TRADE_PLAN_READY` is validated.

3. `smc_desk/rendering/clean_mtf_chart_pack.py`
   - Clean chart titles now show actual candle count.
   - Clean chart rendering uses the full required context window.

4. `tools/run_wp0036_acceptance_gauntlet.py`
   - Added local CSV replay mode:
     - `--data-source local_csv`
   - Added required context-depth checks.
   - Added required verification package file manifest.
   - Added root package manifest.
   - Added explicit data-route failure reporting.
   - Removed fake forced trade-plan payload behavior.
   - Replaced simulated BTC/SOL trade plans with conservative official payload generation.
   - Added strict critic JSON fallback for critic prompt runs.
   - Acceptance checkpoints now fail on:
     - watch chart with trade box,
     - trade chart mismatch,
     - shallow context.
   - Full archive generation now avoids recursively including `verification_package_full.zip` inside itself.

5. Tests
   - Added `tests/test_wp0036_acceptance_package_repairs.py`.
   - Expanded `tests/test_wp0034_ai_smc_trader_brain.py`.

## New Evidence Package

Fresh local replay run:

`/Users/tobimobolade/smc-codex-desk/analysis_runs/WP0036_GAUNTLET_20260701_082052`

Download copy:

`/Users/tobimobolade/Downloads/wp0036_verification_package_full_20260701_082052.zip`

The package includes, per completed symbol:

- `provider_manifest.json`
- `official_decision.json`
- `validation_report.json`
- `critic_review.json`
- `anchor_grounding_report.json`
- `liquidity_status_report.json`
- `rule_origin_report.json`
- `evidence_pack.json`
- `official_annotated_chart.png`
- `clean_15m_chart.png`
- `clean_1h_chart.png`
- `clean_4h_chart.png`
- `clean_1d_chart.png`
- `test_summary.txt`
- `verification_package_manifest.json`

## Run Results

BTCUSDT:

- Data source: local Binance futures CSV replay.
- Context depth: 15m 1500, 1h 1000, 4h 500, 1d 365.
- Official state: `WATCH_ONLY`.
- Chart template: `watch_chart`.
- Trade box: false.
- Acceptance result: PASS.

SOLUSDT:

- Data source: local Binance futures CSV replay.
- Context depth: 15m 1500, 1h 1000, 4h 500, 1d 365.
- Official state: `WATCH_ONLY`.
- Chart template: `watch_chart`.
- Trade box: false.
- Acceptance result: PASS.

AVAXUSDT:

- Local CSV replay could not run.
- Reason: canonical AVAXUSDT local CSV files do not exist under `data/ohlcv/binance_futures/AVAXUSDT`.
- This is now recorded as a data-route failure in the root manifest instead of being silently ignored.

Root package status: `PARTIAL` because BTCUSDT and SOLUSDT passed, while AVAXUSDT had no local data route.

## Validation

Focused repair tests:

`41 passed in 1.78s`

Full project suite:

`672 passed, 1 skipped in 106.45s`

Archive inspection:

- Required package files are present for BTCUSDT and SOLUSDT.
- The repaired ZIP no longer includes a recursive nested `verification_package_full.zip`.

## Remaining Work

1. Add or backfill canonical AVAXUSDT Binance futures CSVs if AVAX must be included in local-first replay.
2. Improve watch-chart semantic richness: current charts are honest and safe, but still too minimal compared with professional SMC teaching charts.
3. Make the root package status wording more expressive, for example `PARTIAL_DATA_ROUTE_FAILURE` instead of plain `PARTIAL`.
4. Continue the visual annotation repair toward swing-to-swing structure lines, selective BOS/CHoCH labels, bounded OB/FVG zones, and cleaner trader-style story charts.

## Bottom Line

The critical failure from yesterday is fixed: the system can no longer promote a trade-ready chart while saying there is no validated sweep/displacement. The new evidence package is honest, reproducible, and auditable. It is not yet visually perfect, but it is now structurally much safer.
