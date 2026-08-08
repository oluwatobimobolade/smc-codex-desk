# WP-0041A Annotation Integrity Re-Audit

Date: 2026-07-10

## Verdict

The overnight WP-0041/WP-0041A implementation was a strong and coherent foundation, but it was not fully complete. The architecture existed and most tests were valid; the re-audit found authority, lifecycle, decision-time, and coordinate gaps. All identified gaps are now repaired and covered by focused tests.

## What Was Already Good

- `annotation_plan_v2` was wired through decision schema, validator, renderer, and artifacts.
- Geometry was checked against canonical evidence rather than evidence IDs alone.
- The renderer preferred sparse V2 drawing objects and the critic could identify clutter.
- Trade boxes were gated to validated trade-ready decisions.
- The formal structure graph remained the higher authority.

## Repairs Completed

- Added confirmation, activity, mitigation, wick-probe, and confidence fields to annotation evidence anchors.
- Blocked unconfirmed probes from BOS/CHoCH and blocked terminal/consumed POIs.
- Added deterministic active watch-POI selection from confirmed 15m OB/FVG evidence.
- Made visual-critic failure an official hard downgrade that strips all trade authority.
- Reran the critic after cleanup and retained pre-cleanup provenance.
- Made an empty V2 plan suppress legacy labels, levels, banners, and paths.
- Kept one-candle POIs locally visible with a capped display span.
- Repaired offline XAU replay to trim at decision time and derive completed HTFs from canonical 15m only.
- Synchronized the live thesis with selected POI and active-range conflict evidence.
- Unified official-chart and evidence-pack candle windows; timestamps now override raw drawing indices.
- Refused evidence outside the visible window instead of snapping it to a chart edge.
- Replayed post-confirmation candles to reject consumed or invalidated POIs independently of stale detector lifecycle fields.

## Validation Evidence

- WP-0041 + WP-0041A: 17 passed.
- Extended affected suite: 126 passed.
- Focused integrity, partial-HTF, and offline-XAU suite: 25 passed.
- Full repository: 760 passed, 1 skipped in 132.44 seconds.
- Compileall and `git diff --check`: passed.

Fresh smoke artifacts:

- GBPUSD: `analysis_runs/WP0041A_REAUDIT_20260710/LIVE_FINAL_VERIFIED/LIVE_FULL_SYSTEM_AI_SMC_V3_20260710_082247/GBPUSD/`
- Offline XAU: `analysis_runs/WP0041A_REAUDIT_20260710/OFFLINE_FULL_SYSTEM_XAUUSD_STALE_20260710_082328/`

## Honest Boundary

This work establishes deterministic annotation integrity, decision-time truth, sparse rendering, and conservative refusal. It does not prove that SMC has predictive edge, does not authorize paper or live execution, and does not make TradingView/Kimi market truth.
