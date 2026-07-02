# Open Risks

## R-001: Perception Ontology Contains Strategy And Risk Parameters

`specs/PERCEPTION_ONTOLOGY_V2.yaml` currently contains fields such as
`risk_reward_floor`, `stop_buffer_atr_mult`, `require_fresh_poi`, and
`allowed_poi_kinds` handling in code. The constitution requires perception and
strategy concerns to be separated. Current engine imports still depend on the
combined config, so this must be migrated carefully.

Update: WP-0015 created split target contracts at
`specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml` and
`specs/STRATEGY_EXECUTION_CONFIG_V1.yaml`, plus an audit guard. WP-0016 then
migrated runtime `RuleConfig` defaults to those split contracts with legacy
compatibility adapters. This risk is closed for runtime config authority, but
it does not certify perception completeness, strategy edge, or live execution.

## R-002: Scenario Semantics Are Still Minimal

WP-0002 moved the market-colleague workflow into a PerceptionEngineV2-led
orchestrator, and legacy output is now written under `legacy_comparison/`.
WP-0012 removed legacy trade-plan authority from `decision.json` and
`scenario_tree.json`. However, the scenario tree is still a minimal current
context layer, not yet a rich object-to-object MTF scenario reasoner.

## R-003: Kimi WebBridge Capture Is Not Fully Verified

Existing capture can navigate and screenshot TradingView, but does not yet
prove all chart-state requirements: exact symbol text, timeframe text, candle
type, linear scale, timezone, visible bar window, and DOM evidence.

Update: WP-0003 added a strict local alignment contract. Screenshot-only
manifests now fail alignment instead of being treated as verified. The remaining
risk is the live browser controller: it must populate verified `chart_state`
from TradingView evidence or OHLCV overlap before alignment can pass in live
shadow mode.

## R-004: Strategy Evidence Is Not Fully Audited

Old SMC strategy docs, research rules, ML scorers, and backtest reports are not
yet fully classified into active, research, legacy, rejected, or archive.

## R-005: No Certified Predictive Edge

No strategy candidate currently has promotion-grade evidence after costs,
walk-forward testing, matched baselines, untouched holdout, and live shadow.

Update: WP-0013 resolved 50 local colleague packages, but all 50 were
`NO_SETUP` observations. This proves outcome plumbing, not edge.

## R-006: Historical Availability Is Modelled, Not Observed

WP-0011 repaired scheduled close-time availability for historical and
TradingView-replayed candles. Historical CSVs still do not contain real live
ingestion timestamps, provider delays, or clock-skew metadata. Live shadow
should record those fields before any claim of production-grade timing
certainty.

## R-007: Live OHLCV Acquisition Can Fail While Charts Are Visible

WP-0016 attempted BTCUSDT live shadow through Kimi WebBridge and TradingView.
Kimi was healthy and screenshots were captured, but TradingView OHLCV timed
out, Binance REST failed DNS resolution, and browser-side Binance fetch failed.
The system correctly returned `NO_VALID_LIVE_TRADE`. Next work must harden live
OHLCV route health checks, retry windows, provider diagnostics, and visual-only
gating.

## R-008: WP-0020 Visual Audit Is Available But Not DOM-Verified Candle Truth

WP-0020 proves the CSV-backed colleague path from verified OHLCV through
charting, annotation, perception, cognitive refusal, TradingView/Kimi screenshot
capture, thesis, memory, and final report. The visual manifest still marks
timeframe chart state as `requested_state_not_dom_verified` and last-closed
candle timing is null, so TradingView remains visual audit evidence only. The
next visual test should extract DOM-verified symbol/timeframe/candle timing and
still keep mismatches as `REVIEW_REQUIRED`, not market-truth overrides.

## R-009: WP-0021 Professional Interpretation Is Core Slice, Not Full SMC Maturity

WP-0021 repairs the BTCUSDT internal-retracement-as-HTF-conflict failure class
by adding external/internal hierarchy, displacement quality, POI lifecycle,
timeframe roles, watch states, and SMC thesis V2. It does not finish the full
A-J roadmap. Still open: paginated live backfill, hard HTF depth enforcement,
direct HTF-vs-resampled audits, certified order-block/breaker/mitigation-block
detectors, story-vs-debug renderer, DOM-verified visual reconciliation, and a
human-adjudicated gold SMC label set.

Update: WP-0021A confirmed the parent-subordination repair and cleaned the
authority boundary. WP-0022 then implemented the Stage A/B detector primitives:
parallel internal/external break tracks, protected-swing external CHoCH,
ATR-normalized swing prominence, liquidity levels, equal highs/lows,
sweep/reclaim events, order blocks, POI-grade FVG origin filtering, and
inducement objects. Remaining maturity risk moves to WP-0023: these primitives
must be wired into premium/discount gating, liquidity targets, valid dealing
ranges, ATR scoring, calibrated story rendering, and outcome testing before the
system can claim decision quality or strategy edge.

## R-010: WP-0022 Produces Richer Objects But Needs Story/Decision Calibration

WP-0022 intentionally emits many raw research objects. The BTCUSDT replay proved
the market story is corrected (`WATCH_BEARISH_RETRACE_TO_SUPPLY`), but the raw
object counts are high. The next work must separate debug density from story
charts, enforce premium/discount and liquidity-draw logic, and test whether the
new primitives improve outcomes after costs. Until that happens, the detector is
more mature, but still observe-only research evidence.
