# SMC Visual Accuracy Spec

This document answers the critical question: how do we stop the analyst from inventing levels and make it usable across pairs?

## Honest Status

The system is not yet a perfect multi-pair SMC trader. It is a strong foundation:

- deterministic OHLCV analysis,
- no-future-leakage MTF context,
- exchange-matched TradingView capture,
- case-library auditing,
- and now Pine overlay export.

It should not be described as screenshot-trained or edge-proven yet. The current edge is discipline and repeatability, not proven profitability.

## Core Rule

Screenshots are evidence, not the source of truth.

The system should never ask a model to freely invent levels from pixels. The safe pipeline is:

1. Use exchange-matched OHLCV.
2. Detect levels deterministically.
3. Export exact levels to TradingView as Pine overlay objects.
4. Capture the overlayed chart with Kimi WebBridge.
5. Ask the model to explain the overlay and chart together.
6. Audit the result against human/expert labels.

This makes weak and strong models read the same structured truth instead of guessing.

## What Must Be Detected

### Market Structure
- Swing highs and swing lows.
- BOS only when body close breaks structure with displacement.
- CHoCH only when direction flips after a valid structural break.
- Breaker/mitigation blocks only after a failed support/resistance role flip is confirmed.

### Liquidity
- Equal highs/lows clustered within tolerance.
- Prior session/day/week/month highs and lows.
- Obvious swing extremes.
- Sweep status: unswept, swept, reclaimed, failed reclaim.

### Imbalance
- FVGs with displacement filter.
- Mitigation percentage.
- Fresh, partial, mitigated status.

### Supply/Demand/OB
- Last opposite candle before displacement.
- Body quality and displacement score.
- Freshness/mitigation.
- Premium/discount location.
- Proximity to structure origin.

### Trade Plan
- HTF bias.
- Dealing range.
- POI.
- Confirmation condition.
- Structural invalidation and execution SL.
- Liquidity target.
- R:R.
- Explicit missing checks.

## Multi-Pair Requirement

Every market needs a source contract:

- TradingView symbol, for example `BINANCE:BTCUSDT.P`, `BITSTAMP:BTCUSD`, or `OANDA:EURUSD`.
- OHLCV source and venue.
- Timezone and candle-open semantics.
- Tick size / pip size.
- Spread/slippage assumption.
- Session model.
- News/fundamental calendar source.

The crypto default is now Binance USD-M futures data (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `BNBUSDT`) matched to TradingView perp charts such as `BINANCE:BTCUSDT.P`. Bitstamp spot remains a legacy comparison source. Forex must use real Forex data, not crypto proxy data.

## Annotation Options

### Option A: Pine Overlay - current best path

Generate a Pine Script from `case.json` and paste it into TradingView. This draws deterministic zones, lines, and labels on the actual chart. It is repeatable, price-exact, and model-independent.

Tool:

```bash
python3 tools/generate_tradingview_overlay.py --case path/to/case.json
```

### Option B: TradingView Charting Library Drawings API

This is powerful if we host our own embedded TradingView Charting Library app. It can create multipoint drawings programmatically. It is not generally exposed on public TradingView Supercharts pages.

### Option C: Kimi WebBridge coordinate drawing

This can click and type, but using it to mouse-draw rectangles/lines is fragile because chart layout, zoom, panes, sidebars, and browser scaling change coordinates. It should be used to install/capture Pine overlays, not as the main drawing engine.

## Anti-Hallucination Controls

1. **No screenshot-only trade decisions.**
2. **Source alignment required:** chart exchange must match OHLCV exchange where possible.
3. **Case audit required:** unreviewed cases cannot become training labels.
4. **Overlay required for visual claims:** key levels must appear in `tradingview_overlay.pine`.
5. **Missing checks must be explicit:** the model must say why it is not an entry.
6. **Human label gate:** only `gold_standard` or `approved` cases can train/evaluate model behavior.
7. **Regression set:** every future rules change must pass a fixed set of reviewed wins, losses, missed entries, and no-trade chop cases.

## Research Notes

Existing public/open-source SMC implementations use deterministic OHLCV functions for FVGs, swing highs/lows, BOS/CHoCH, order blocks, liquidity, previous highs/lows, and sessions. That supports our direction: do not depend on free-form vision to find core levels.

TradingView Pine supports programmatic lines, boxes, labels, and polylines. Pine scripts cannot control manual Supercharts drawing tools, so overlay scripts are the reliable public-TradingView route.

TradingView Charting Library has a Drawings API for hosted chart widgets, including `createShape` and `createMultipointShape`, but that is a different environment from the public TradingView page.

## Next Build Phases

1. Add source contracts for BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, EURUSD, GBPUSD, XAUUSD, and US indices.
2. Add previous day/week/month high-low levels.
3. Add breaker/mitigation-block detection as first-class zones.
4. Add session liquidity and kill-zone filters.
5. Generate Pine overlays for every verified case.
6. Use Kimi WebBridge to capture overlayed TradingView charts.
7. Build a reviewed gold-standard case set before claiming model visual skill.
