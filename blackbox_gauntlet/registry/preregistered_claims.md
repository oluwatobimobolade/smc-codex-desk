# SMC Codex Desk: Preregistered Claims
**Version:** blackbox-gauntlet-v1

This document freezes the explicit claims of what `PerceptionEngineV2` can identify deterministically. We commit to these definitions and expected accuracies *before* seeing the hidden test results.

## 1. Local Swing
* **Definition:** A 3-candle fractal pattern. Local Swing High: central candle high > left and right highs. Local Swing Low: central candle low < left and right lows.
* **Minimum Visible Context:** 3 candles.
* **Confirmation Rule:** Strict close of the 3rd candle.
* **Permitted Uncertainty:** None on the fractal itself.
* **Expected Accuracy:** 100% (Purely Mathematical)

## 2. Internal Swing
* **Definition:** The highest/lowest Local Swings within a defined Dealing Range (between the most recent confirmed External Swings).
* **Minimum Visible Context:** A confirmed external dealing range + minimum 3 candles for the local fractal.
* **Confirmation Rule:** Becomes confirmed once a subsequent swing forms in the opposite direction.
* **Permitted Uncertainty:** None mathematically. Subjective definitions of "importance" are ignored in V2.
* **Expected Accuracy:** 100% (Purely Mathematical under V2 Ontology)

## 3. External Swing
* **Definition:** A swing point that has successfully broken (via body close) the prior protected structure.
* **Minimum Visible Context:** A prior structural break and the retracement that forms the new swing point.
* **Confirmation Rule:** Confirmed when price reverses and breaks structure in the opposite direction.
* **Permitted Uncertainty:** Scope ambiguity (whether a move is a complex internal pullback or a true external swing).
* **Expected Accuracy:** Precision ≥ 92%, Recall ≥ 88%

## 4. Protected High / Protected Low
* **Definition:** The origin of a move that caused an External structural break (BOS).
* **Minimum Visible Context:** The origin point and the subsequent BOS.
* **Confirmation Rule:** Confirmed simultaneously with the BOS that it caused.
* **Permitted Uncertainty:** None mathematically once the BOS is confirmed.
* **Expected Accuracy:** Accuracy ≥ 90%

## 5. Wick Probe
* **Definition:** Price breaches a protected structure level, but the candle body closes back within the boundary.
* **Minimum Visible Context:** 1 candle crossing the level.
* **Confirmation Rule:** Candle close.
* **Permitted Uncertainty:** None (Tick-level mathematical check).
* **Expected Accuracy:** 100%

## 6. Break of Structure (BOS)
* **Definition:** A candle body close beyond a confirmed external protected swing in the direction of the trend.
* **Minimum Visible Context:** Protected point + 1 breaching candle.
* **Confirmation Rule:** Strict body close.
* **Permitted Uncertainty:** None (Tick-level mathematical check).
* **Expected Accuracy:** Precision ≥ 93%, Recall ≥ 88%

## 7. Change of Character (CHoCH)
* **Definition:** A candle body close beyond a confirmed external protected swing *against* the prevailing trend.
* **Minimum Visible Context:** Protected point + 1 breaching candle.
* **Confirmation Rule:** Strict body close.
* **Permitted Uncertainty:** Differentiation between a minor internal CHoCH and a major external CHoCH.
* **Expected Accuracy:** Precision ≥ 88%, Recall ≥ 80%

## 8. Bullish Fair Value Gap (FVG)
* **Definition:** A 3-candle sequence where Candle 1 High < Candle 3 Low.
* **Minimum Visible Context:** 3 candles.
* **Confirmation Rule:** Strict close of the 3rd candle.
* **Permitted Uncertainty:** None (Tick-level mathematical check).
* **Expected Accuracy:** 100%

## 9. Bearish Fair Value Gap (FVG)
* **Definition:** A 3-candle sequence where Candle 1 Low > Candle 3 High.
* **Minimum Visible Context:** 3 candles.
* **Confirmation Rule:** Strict close of the 3rd candle.
* **Permitted Uncertainty:** None (Tick-level mathematical check).
* **Expected Accuracy:** 100%

## 10. FVG Lifecycle State
* **Definition:** Tracks whether an FVG is `FORMED`, `PARTIALLY_MITIGATED`, `FULLY_MITIGATED`, or `INVALIDATED`.
* **Minimum Visible Context:** The FVG + all subsequent candles until present/invalidation.
* **Confirmation Rule:** Evaluated dynamically at each candle close.
* **Permitted Uncertainty:** None mathematically.
* **Expected Accuracy:** 100%

## Evaluation Constraints
* **Supported Instrument:** BTCUSDT Perpetual
* **Supported Timeframe:** 15-minute
* **Supported Chart Styles:** Standard candlestick
* **Matching Tolerance:** Exact timestamp and price level (0 ticks error for mathematical objects).
