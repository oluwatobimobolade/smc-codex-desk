# WP-0023 V6 Colleague Integration — Story Renderer, Data Depth, Memory Supersession

Status: `PASS_ACCEPTED`

Authority mode: `observe_only_detector_research`

WP-0023 wires the V6 cognitive brain to trader-facing story charts so the visual
narrative can never contradict the cognitive state. It also hardens the data
foundation and memory model that the narrative rests on.

## What Changed

- **Story renderer (`smc_desk/render_v2.py`)**
  - New `render_v2_story_chart()` draws candles, recent external structure,
    active POI, premium/discount shading, and an observe-only banner.
  - Title is `SYMBOL TF | V6: <final_state>`.
  - Per-timeframe bias line uses `structure_hierarchy[timeframe].external_bias`,
    not the legacy trade-plan direction. This fixes the bug where a 15m chart
    showed `bias bullish` while V6 said the 15m external structure was bearish.
  - Debug mode (`mode="debug"`) renders all primitives; story mode renders only
    the recent narrative-relevant objects.

- **Gauntlet stage separation (`smc_desk/colleague/wp0020_gauntlet.py`)**
  - Added `04a_story_charts` stage rendered *after* the colleague brain produces
    `final_colleague_output.json`.
  - Legacy `04_annotated_charts` remains as the debug/comparison layer.
  - `story_charts_generated` added to the final report summary.
  - Story rendering is best-effort: malformed snapshots skip that timeframe
    without failing the gauntlet.

- **Data depth and direct-vs-resampled validation**
  - Analysis windows widened to research-depth targets:
    `15m=1500, 1h=1000, 4h=500, 1d=365`.
  - MTF package manifest now includes `data_depth` rows/status/shortfall per TF.
  - MTF package manifest now includes `direct_vs_resampled_validation`, which
    resamples the canonical 15m frame and compares last-candle OHLC against the
    provided HTF frames.

- **Memory supersession (`smc_desk/colleague/decision_memory_graph.py`)**
  - New `supersede_prior_decisions()` marks older same-symbol records as
    `superseded_by` when the narrative direction changes.
  - `orchestrator_v2.py` stores `final_state` in each memory record and triggers
    supersession after appending a new record.
  - Gauntlet memory manifest reports `superseded_count` and `current_count`.

- **Perception primitive repairs**
  - `dealing_range.py` builds ranges from the protected external high/low pair
    and clips child ranges to the parent range.
  - `poi_lifecycle.py` classifies bearish order blocks as `supply` (was
    `order_block`), and each POI now carries `event_history`, `quality_score`,
    and `quality_reasons`.

## Validation

- New WP-0023 regression tests: `tests/test_wp0023_v6_story_renderer.py`
  - `7 passed`
- Full pytest baseline: `530 passed, 1 skipped in 92.40s`
- Governance consistency: `PASS`
- No market edge, paper execution, live execution, or capital-risk authority was
  created or enabled.

## Runs

### BTCUSDT V6 story gauntlet

- Path: `analysis_runs/WP0023_BTCUSDT_V6_STORY_CHARTS_20260627`
- Source: `data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv`
- Status: `PARTIAL_PASS` (TradingView visual layer deliberately skipped)
- Final state: `NO_TRADE_HTF_CONFLICT`
- Final action: `NO_SIGNAL`
- Story charts generated: 4
- 15m chart header verified: `bias bearish`, matching 15m external bias.

### SOLUSDT full system with TradingView visual capture

- Path: `analysis_runs/WP0023_SOLUSDT_FULL_SYSTEM_VISUAL_20260627`
- Source: `data/ohlcv/binance_futures/SOLUSDT/SOLUSDT_15m_4year.csv`
- Status: `PASS`
- Final state: `WATCH_BEARISH_RETRACE_TO_SUPPLY`
- Final action: `NO_SIGNAL`
- Direction: bearish (15m bullish retracement; 1h/4h/1d bearish)
- Story charts generated: 4
- TradingView screenshots captured: 4 (15m, 1h, 4h, 1d) via Kimi WebBridge
- Visual reconciliation: `VISUAL_AUDIT_AVAILABLE`
- Evidence-linked thesis written to `09_smc_thesis/smc_trade_thesis_v2.md`.
- Note: OHLCV came from the cached Binance CSV ending 2026-06-19; TradingView screenshots are live 2026-06-27 and remain audit-only evidence, not market truth.

## Boundary

WP-0023 is research and observability infrastructure only. It does not claim
strategy edge, generate executable signals, or enable paper/live execution.
