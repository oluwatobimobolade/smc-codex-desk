# Chart markup — how to do this

This is the error signal the project has never had. Until you mark these
charts, every perception threshold in the system — swing significance, break
displacement floors, liquidity importance weights, the label separation floor,
the POI approach zone — is a **reasoned default with no measurement behind
it**. Your markup is what turns those from judgement into calibration.

20 cases. BTCUSDT 15m, balanced across four regimes: 5 trend, 5 range, 5
transition, 5 ambiguous. Roughly 15–20 minutes each.

## The one rule that matters

**Do not open `_sealed_system_answer.json` before you finish a case.**

It contains what the system concluded. If you read it first, what you produce
measures suggestion rather than perception, and the whole exercise is void.
The filename starts with an underscore so it sorts away from what you need.

## What you have per case

```
<case_id>/
  charts/
    BTCUSDT_4h_clean.png     context
    BTCUSDT_1h_clean.png     structure and POIs
    BTCUSDT_15m_clean.png    execution detail
  markup_template.json       what you fill in
  metadata.json              decision time and regime label
  _sealed_system_answer.json DO NOT OPEN YET
```

Charts are candles only. No levels, no labels, nothing drawn — you read the
market, not the machine.

## How to do a case

1. Copy `markup_template.json` to `markup.json` in the same folder.
2. Open the three charts and mark them as you would for a client, **at the
   decision time only**. You cannot see future candles; neither could the
   system.
3. Fill the fields in the order a trader actually works:
   - `htf_bias` and `context_timeframe` — what is the market doing, and which
     timeframe told you
   - `dealing_range` — the range that governs current location
   - `annotations` — only the structure that **matters**. Each entry needs
     primitive, direction, timeframe, timestamp, price. Add as many as you
     need; delete the blank one.
   - `liquidity` — what has been swept, what remains, and where you think
     price is being drawn
   - `primary_poi` — the one zone you would actually watch, and why that one
   - `what_are_you_waiting_for` and `what_would_invalidate_this`
   - `would_you_trade_this` — `yes`, `no`, or `watch`

## Please do these three things

**Leave fields empty when the market does not show them.** A blank dealing
range on a genuinely structureless chart is a correct answer and scores
correctly. Filling it in to be helpful corrupts the measurement.

**Use `is_ambiguous: true` freely.** Ambiguous marks are counted separately
and never penalise the system. Forcing a confident answer where you would
genuinely hesitate teaches the wrong thing.

**Be sparse.** Mark what you would actually draw for a client — not every
object that technically exists. Selectivity is exactly what is being measured;
the system's old failure was marking 6,591 objects and drawing one.

## When you are done

```bash
python tools/score_markup_cohort.py --cohort review_queues/markup_cohort_20260808
```

That writes `score_report.json` with bias agreement, dealing-range agreement,
structure precision and recall, draw agreement, POI overlap, and per-case
detail on exactly what the system missed and what it invented.

## What the result will and will not mean

It **will** tell us where perception is wrong and by how much, which of the
four regimes it handles worst, and whether it misses real structure or invents
false structure — a distinction that decides whether thresholds move up or
down.

It **will not** be truth. One reviewer is one expert opinion, not adjudicated
gold; a second independent reviewer is needed before anything is called
certified. And it says nothing about profitability. Perception accuracy and
trading edge are different questions, and this project has been careful not to
confuse them. Do not let this report be quoted as evidence of edge.

## A note on what you will probably find

Every one of the 20 cases currently stops at `ACCEPTED_DISPLACEMENT` — the
system sees context, names a draw and finds displacement, then fails to select
a causally-owned POI. Most POI candidates are being rejected as
`INVALID_DIRECTION_MISMATCH` or as straddling a protected level.

Your `primary_poi` answers are therefore the most valuable field in this
exercise. They will show whether the POI layer is correctly refusing weak
zones, or wrongly rejecting the zone a trader would obviously take.
