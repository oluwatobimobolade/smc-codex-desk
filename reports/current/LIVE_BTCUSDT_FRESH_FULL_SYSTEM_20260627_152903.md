# Fresh BTCUSDT Full-System Live Analysis

Run: `analysis_runs/WP0022_LIVE_BTCUSDT_FRESH_20260627_152903`

Generated: 2026-06-27 15:29 UTC

## Market Truth

- Symbol: `BTCUSDT` Binance USD-M perpetual.
- Provider: `binance_rest_direct`.
- Route health: `READY`.
- Verified closed 15m candles: `1499`.
- Last verified closed candle: open `2026-06-27T15:00:00+00:00`, close `2026-06-27T15:14:59.999000+00:00`.
- Last closed 15m OHLCV: open `60589.0`, high `60905.3`, low `60541.1`, close `60851.6`, volume `4033.171`.
- Current forming candle was excluded.
- TradingView was not used as market truth.

## Full-System Result

- Gauntlet status: `PASS`.
- Clean charts generated: `4`.
- Annotated charts generated: `4`.
- TradingView screenshots captured: `4`.
- Visual reconciliation: `VISUAL_AUDIT_AVAILABLE`.
- Perception event count: `302`.
- Regime: `ranging / expansion / distribution`, confidence `0.7496`.
- Contradiction result: `ALIGN`.
- Dominant direction: `bearish`.
- Observation confidence: `0.9019`.
- Final state: `WATCH_BEARISH_RETRACE_TO_SUPPLY`.
- Final action: `NO_SIGNAL`.
- Capital risk: `0`.

## Structure Thesis

Daily context is shallow and neutral because the live bounded window only has 15 derived daily candles.

4H is the directional timeframe and remains externally bearish. The latest important 4H external break is `BOS_bearish_1782302400.0`, with the active 4H external range approximately `63209.6` high to `58030.0` low. Price is below the 4H equilibrium around `60619.8`, so the 4H location is still discount even while price is retracing.

1H is the setup timeframe and also remains externally bearish. The 1H internal state is bullish retracement, not a bullish HTF reversal. The 1H protected high is `60557.8`, protected low is `58388.0`, and latest internal bullish break quality is weak, so the system correctly refuses to let the 1H internal retracement override 4H/1H bearish context.

15M is confirmation-only. The latest closed 15m candle was a strong bullish push into/through nearby supply, so there is no bearish execution confirmation yet.

## POI Reality Check

The formal watch-state selected a far 1H fresh bearish order block at `66206.6 - 66388.8`.

That selection is too crude for live trade planning. The nearest relevant active bearish POIs around current price are:

- 15m bearish FVG `60227.6 - 61163.9`, partial, price inside.
- 1H bearish FVG `60466.9 - 61048.5`, partial, price inside.
- 4H bearish FVG `60649.1 - 62272.1`, partial, price inside/near lower section.
- 15m bearish OB `61140.3 - 61339.9`, fresh, above current price.
- 4H fresh supply `62263.975 - 62939.3`, above current price.

This means the practical thesis should not be "wait all the way to 66.2k." It should be: BTCUSDT is retracing inside nearby bearish imbalance/supply, but short execution requires a fresh 15m bearish rejection/displacement from this area.

## Trade Decision

No executable trade right now.

Reason:

- HTF story is bearish, but current 15m behavior is bullish retracement into supply.
- The latest 15m candle closed strong bullish at `60851.6`.
- No completed 15m bearish confirmation has printed after the retrace.
- The engine is observe-only and execution authority remains disabled.

## Watch Plan

Bearish continuation idea:

- Watch current/nearby bearish imbalance zone around `60466.9 - 61163.9`.
- Stronger supply begins around `61140.3 - 61339.9`.
- Confirmation needed: 15m bearish displacement/rejection from the zone, ideally taking an internal low after a sweep/rejection.
- Invalidating pressure: clean acceptance above the nearby 15m OB/supply around `61339.9`, then higher-timeframe supply reassessment.
- Downside liquidity remains the 1H/4H sell-side range, especially below `60162.0`, then the broader low area around `58388.0 - 58030.0`.

## System Quality Note

This run shows the core hierarchy repair is working: internal bullish retracement did not flip bearish HTF structure. The remaining defect is POI ranking. The watch-state selector still prefers far fresh order blocks over nearer partial imbalances that are more relevant to live analysis. This should be handled in WP-0023 with premium/discount-aware POI ranking, nearest active supply selection, and story/debug renderer separation.
