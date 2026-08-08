# WP-0022 SMC Detector Rebuild Stage A/B

Status: `PASS_ACCEPTED_STAGE_AB`

Implemented the detector-level rebuild for the missing SMC primitives:

- real internal/external structure tracks
- protected-swing CHoCH for external bias
- ATR-normalized swing prominence
- temporal parent-subordination
- liquidity levels and equal highs/lows
- sweep/reclaim objects
- order-block objects
- POI-grade FVG tagging
- inducement objects

BTCUSDT replay now reads:

- 4H bearish external / bullish internal retracement
- 1H bearish external / bullish internal retracement
- 15M bearish external / bullish internal retracement
- final state `WATCH_BEARISH_RETRACE_TO_SUPPLY`
- final action `NO_SIGNAL`
- contradiction `ALIGN`

Validation:

- WP-0022 tests: `7 passed`
- affected suite: `55 passed`
- full suite: `523 passed, 1 skipped`
- BTCUSDT replay: `PARTIAL_PASS` only because TradingView capture was skipped

No strategy edge, paper execution, live execution, or capital-risk authority was
created. WP-0023 remains the next step for decision wiring, premium/discount
enforcement, liquidity targets, ATR threading, and story-renderer cleanup.
