# WP-0027 SMC Decision Quality and Diagram Repair

Date: 2026-06-28

## Objective

Repair the failure class where the system could generate diagrams and theses that were technically present but not trader-readable enough: invalid/far POIs could confuse the chart, 15m bias could appear to contradict the HTF model, and CHoCH/displacement could be over-read without POI/liquidity context.

## Implemented

- Active POI selection is protected-range first through `ranked_active_poi_v2_protected_range_first`.
- `smc_desk/decision/poi_selection.py` now exposes a decision-facing POI-selection import path.
- Story charts hide detector noise in story mode and keep raw events in debug charts only.
- Invalid/parent-scope POI warnings are priority notes, so they cannot be pushed out of the visible chart note box.
- Story chart titles now separate model direction from local timeframe bias, for example `model bearish | 15m bias bullish`.
- Execution readiness, inducement/continuation state, liquidity sequence, confidence split, and outcome contract fields are included in gauntlet outputs.
- Added acceptance tests for:
  - 15m CHoCH not being enough without HTF/POI context.
  - Early bearish confirmation requiring an LTF supply retest.
  - SOL-style topside raid plus extended bearish drop being non-chaseable.
  - Inducement/continuation outcome contracts.
  - Story charts showing watch state and parent POI warnings.
  - Story charts separating model direction from local timeframe bias.

## Smoke Runs

- BTCUSDT CSV gauntlet:
  - `analysis_runs/WP0027_DECISION_QUALITY_DIAGRAM_REPAIR_20260628/BTCUSDT`
  - Status: `PARTIAL_PASS`
  - Reason: TradingView visual capture intentionally skipped, so visual layer is `REVIEW_REQUIRED`.
  - Story charts generated: 4.
  - Final action: `NO_SIGNAL`.
  - Pipeline confidence: `0.9269`; analysis confidence: `0.2676`.

- SOLUSDT CSV gauntlet:
  - `analysis_runs/WP0027_DECISION_QUALITY_DIAGRAM_REPAIR_20260628/SOLUSDT`
  - Status: `PARTIAL_PASS`
  - Reason: TradingView visual capture intentionally skipped, so visual layer is `REVIEW_REQUIRED`.
  - Story charts generated: 4.
  - Final action: `NO_SIGNAL`.
  - Pipeline confidence: `0.928`; analysis confidence: `0.5928`.

## Validation

- Focused repair tests: `9 passed`.
- Focused story renderer tests: `11 passed`.
- Compile check: `.venv/bin/python -m compileall smc_desk tools tests` passed.
- Governance consistency: `GOVERNANCE CONSISTENCY: PASS`.
- Full suite: `550 passed, 1 skipped`.

## Authority

- No live execution.
- No paper execution.
- No broker logic.
- No RASC promotion.
- No edge claim.
- Capital risk remains `0`.

## Remaining Work

- Re-run BTC/SOL with real TradingView visual capture when the user wants a live visual audit package.
- Build OCR/DOM-backed title/symbol/timeframe verification if TradingView context must become stronger than image heuristics.
- Continue outcome resolution on the pending inducement/continuation contracts before making any edge claim.
