# Consensus SMC Research Notes

**Purpose:** identify the SMC rules that repeat across sources, local academy transcripts, and open SMC tools, then separate core system rules from subjective filters.

This is not proof that SMC is profitable. It is a doctrine filter: if a concept is repeated across sources, it can become part of the core language; if it is source-specific, it stays optional until backtests and reviewed cases prove value.

## Sources Reviewed

### Local Academy / Video Transcripts

The repo contains 11 SMC transcript files under `research_transcripts/`:

- HCN confluences
- HCN entry techniques
- HCN inducement
- HCN market structure
- HCN order block entry
- HCN simplest strategy
- HCN valid order blocks
- KiraForex easiest strategy
- KiraForex FVG / imbalances
- SMC complete beginner to advanced
- Trading Savant full course

### Web / Documentation Sources

- LuxAlgo Price Action Concepts: market structure, liquidity, imbalances, order blocks, premium/discount, and previous highs/lows.
- TradingView LuxAlgo Smart Money Concepts open-source indicator page.
- General technical-analysis references for support/resistance, risk/reward, and backtesting discipline.

## Transcript Frequency Scan

Approximate keyword coverage across the 11 local transcripts:

| Concept group | Files mentioning it | Total keyword hits | Classification |
|---|---:|---:|---|
| Confirmation / entry behavior | 11 / 11 | 1496 | Core |
| Liquidity / sweep / inducement | 11 / 11 | 627 | Core |
| Market structure / BOS / CHoCH | 10 / 11 | 1340 | Core |
| Risk / target / stop logic | 10 / 11 | 688 | Core |
| FVG / imbalance | 10 / 11 | 681 | Core |
| MTF / top-down context | 8 / 11 | 645 | Core |
| Order blocks | 8 / 11 | 258 | Core POI |
| Breaker / mitigation blocks | 3 / 11 | 51 | Research |
| News filter | 1 / 11 | 12 | Optional filter |
| Premium / discount wording | 1 / 11 | 9 | Useful filter |
| Killzone / session wording | 1 / 11 | 3 | Optional filter |

## Core Consensus Rules

### 1. Top-down context comes first

Most sources use a higher-timeframe narrative before lower-timeframe execution. For this system:

- Daily = macro context and major dealing range.
- 4H = external/swing structure.
- 1H = POI and nearer-term HTF decision zone.
- 15m = execution chart.
- 5m can be added later for confirmation, but is not required for the current deterministic engine.

Engine rule now: do not feed execution bias from 1H alone. 1H and 4H must agree; Daily must agree or be neutral.

### 2. Structure is the backbone

Common language:

- BOS = continuation after structure is established.
- CHoCH / market structure shift = possible reversal.
- Internal structure is lower-order execution context.
- Swing/external structure carries the higher-timeframe story.

Engine rule:

- Swing/external CHoCH must break the protected high/low by candle close with displacement.
- Internal CHoCH can confirm an entry, but cannot flip HTF bias alone.

### 3. Liquidity must be mapped before entry

Common language:

- Equal highs/lows, prior highs/lows, session highs/lows, and swing highs/lows are liquidity pools.
- Sweeps/grabs are wick-through-and-close-back events.
- Inducement is a local liquidity pool that price may clear before tapping a POI.

Engine rule:

- A sweep is evidence, not entry by itself.
- The sweep must occur before the confirming displacement-backed break.

### 4. POIs are zones, not signals

Common POIs:

- FVG / imbalance.
- Order block.
- Breaker / mitigation block.

Engine rule today:

- FVGs and OBs are first-class deterministic zones.
- Breaker / mitigation blocks remain research until first-class detection is built and tested.
- Fresh POIs are default; partial POIs are research opt-in.

### 5. Displacement matters

Common language:

- A meaningful break should happen with impulse, body expansion, or displacement.
- Weak or slow breaks are more likely to be noise.

Engine rule:

- BOS/CHoCH and FVGs require displacement filters.
- Wick-only structure breaks are not BOS/CHoCH.

### 6. Entry needs confirmation or an exceptional aggressive model

Common language:

- Aggressive entry: limit at a strong HTF POI after the context is already complete.
- Confirmation entry: wait for lower-timeframe sweep, displacement, and internal structure shift.

Engine rule today:

- A trade cannot be `Execute` unless POI, sweep, displacement break, sequence, stop buffer, and R:R all pass.
- `Watch Retrace` is diagnostic/watchlist unless explicitly enabled for research.

### 7. Stops and targets must be structural

Common language:

- SL belongs beyond the structure/POI/sweep level that invalidates the idea.
- TP should target liquidity, not arbitrary points.

Engine rule:

- Store raw structural invalidation separately from executable SL.
- Executable SL must include ATR/structural buffer.
- R:R is calculated from executable SL, not the prettier raw level.

## Subjective / Research-Only Rules

These may be useful, but they are not common enough across our source set to become hard core rules without testing:

- Exact killzone-only execution.
- News-calendar blocking.
- Mandatory 5m confirmation for every entry.
- Mandatory FVG attached to every order block.
- Breaker/mitigation blocks as primary POIs.
- Exact premium/discount wording as a hard gate beyond the current dealing-range check.
- Any claim that an SMC label proves institutional activity.

## What Changes In Our System

1. Keep the current daily / 4H / 1H / 15m cascade.
2. Make HTF bias consensus-based: 1H and 4H must agree; Daily must agree or be neutral.
3. Keep internal vs swing structure separation.
4. Keep liquidity sweep before displacement break as a hard gate.
5. Keep FVG and OB as core POIs, but do not force every OB to have an immediate FVG until tested.
6. Keep fresh POI default.
7. Treat killzones, 5m confirmation, news, breaker blocks, and strict OB+FVG rules as modules to test, not claims that the engine already enforces.

## External References

- [LuxAlgo Market Structure](https://docs.luxalgo.com/docs/algos/price-action-concepts/market-structures)
- [LuxAlgo Liquidity Concepts](https://docs.luxalgo.com/docs/algos/price-action-concepts/liquidity)
- [LuxAlgo Imbalance Concepts](https://docs.luxalgo.com/docs/algos/price-action-concepts/imbalances)
- [LuxAlgo Volumetric Order Blocks](https://docs.luxalgo.com/docs/algos/price-action-concepts/order-blocks)
- [LuxAlgo Premium & Discount Zones](https://docs.luxalgo.com/docs/algos/price-action-concepts/pdzones)
- [LuxAlgo Highs & Lows MTF](https://docs.luxalgo.com/docs/algos/price-action-concepts/previous-high-low)
- [TradingView Smart Money Concepts (SMC) LuxAlgo](https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/)

