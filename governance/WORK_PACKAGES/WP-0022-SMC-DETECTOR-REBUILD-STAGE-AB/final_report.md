# WP-0022 SMC Detector Rebuild Stage A/B

Status: `PASS_ACCEPTED_STAGE_AB`

Authority mode: `observe_only_detector_research`

WP-0022 turns the professional SMC story from WP-0021/WP-0021A into detector
objects. The goal was not to create signals. The goal was to stop relying on
narrative guesses for internal structure, liquidity, order blocks, sweeps, and
inducement.

## What Changed

- `StructureDetector` now runs separate external and internal structure tracks.
- External structure controls bias; internal structure is entry-timing evidence.
- External CHoCH requires a body close through the protected swing, not a random
  internal high/low.
- Structure hierarchy now ignores internal V2 breaks for external bias.
- Cross-timeframe hierarchy is temporal: child timeframe breaks before the
  current parent leg do not keep control of the child story.
- Swings now record scale and ATR-normalized prominence evidence.
- Liquidity levels now exist as first-class objects:
  - single swing highs/lows
  - equal highs
  - equal lows
- Sweep/reclaim events now exist as first-class objects.
- Order blocks now exist as first-class objects: last opposing candle before a
  confirmed structure-breaking displacement.
- Raw FVGs can now be marked as `poi_grade` when they are close to a
  structure-breaking displacement origin.
- Inducement now exists as a first-class object linked to an internal swing,
  order block, break, and optional sweep.
- `PerceptionEngineV2` now emits:
  - `liquidity_levels`
  - `sweeps`
  - `order_blocks`
  - `inducements`
  - `poi_grade_fvgs`
- The perception bridge now exposes summary counts for those new primitives.
- POI lifecycle now prefers certified order blocks and POI-grade FVGs, while
  keeping the old displacement-created POI only as fallback.

## Important BTCUSDT Replay

Replay:

`analysis_runs/WP0022_BTCUSDT_DETECTOR_REBUILD_REPLAY_20260627`

Source:

`analysis_runs/WP0020_LIVE_BTCUSDT_20260627_095711/01_verified_ohlcv/BTCUSDT_15m_verified_closed.csv`

Result:

- Final action: `NO_SIGNAL`
- Final state: `WATCH_BEARISH_RETRACE_TO_SUPPLY`
- Contradiction: `ALIGN`
- 4H: bearish external, bullish internal retracement
- 1H: bearish external, bullish internal retracement
- 15M: bearish external, bullish internal retracement
- Visual layer: `PARTIAL_PASS` only because TradingView capture was deliberately skipped.

Primitive counts from the replay:

- 15M: 77 breaks, 94 liquidity levels, 184 sweeps, 39 order blocks, 39 inducements, 89 POI-grade FVGs.
- 1H: 48 breaks, 101 liquidity levels, 156 sweeps, 16 order blocks, 16 inducements, 49 POI-grade FVGs.
- 4H: 12 breaks, 98 liquidity levels, 214 sweeps, 3 order blocks, 3 inducements, 6 POI-grade FVGs.
- 1D: 1 break, 11 liquidity levels, 5 sweeps, 0 order blocks, 0 inducements, 1 POI-grade FVG.

## Validation

- New WP-0022 detector tests: `7 passed`.
- Affected perception/WP-0021/WP-0020 suite: `55 passed`.
- Compileall on perception and bridge files: PASS.
- Full pytest: `523 passed, 1 skipped in 86.34s`.
- BTCUSDT detector replay: `PARTIAL_PASS` due visual skipped; cognitive result corrected to `ALIGN` and `WATCH_BEARISH_RETRACE_TO_SUPPLY`.

## Boundary

No market edge was claimed. No paper execution, live execution, broker action,
or capital-risk authority was created. WP-0022 improves perception maturity and
research observability only.

## Still Not Done

WP-0023 remains necessary:

- enforce premium/discount gates in watch decisions
- feed liquidity draws into targets and invalidation
- build dealing ranges from the active protected external high/low pair
- thread ATR consistently into displacement, FVG, sweep, and prominence scoring
- tune primitive volume so story charts do not show raw debug noise
- keep TradingView visual reconciliation audit-only and DOM-verified
