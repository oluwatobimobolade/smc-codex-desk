# WP-SMC-24 — Structure Skeleton

**Authority mode:** `observe_only_significance_selected_structural_context`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_SOURCE_BOUND`
**Gate:** `GATE-WP-SMC-24-STRUCTURE-SKELETON-001`

## The recommendation this replaces

The obvious diagnosis of the sparse charts was that the composer's two-object
cap was too tight, and the obvious fix was to raise it. Measuring first showed
that would have made annotation **worse**, and the measurement is worth keeping:

| Timeframe | Raw objects | Graded "major" | % major | "Tradeable" |
|---|---|---|---|---|
| 1d | 296 | 32 | 10.8% | 82 |
| 4h | 463 | 46 | 9.9% | 106 |
| 1h | 921 | 191 | 20.7% | 384 |
| 15m | 1314 | 367 | **27.9%** | **675** |

Two things follow. The grade is not consistently scarce — the same word meant
"top tenth" on 4h and "top quarter" on 15m, and on 15m *half of everything* was
tradeable-grade, which is not a filter. And `structural_significance` reached no
renderer at all: its only consumers were `market_state` and the markup-cohort
builder. Neither the annotation composer, the native story pack, the thesis
writer, nor the narrative hierarchy ever read it.

So the cap was a symptom. Raising it would have drawn eight arbitrary objects
out of forty-six equally-labelled ones — visually richer, less accurate, and a
return to exactly the over-annotation this project started by fixing.

## What was built

**Selection is a count, not a threshold.** A chart holds about eight structural
marks whatever the market is doing; a threshold admits whatever the market
happens to produce. `select_for_display` picks the chart-sized set, which gives
identical density on every timeframe without pretending the absolute grades mean
the same thing everywhere. `prominence_percentile` records where each object sat
in its own timeframe, so the relative information exists without corrupting the
grade, which stays absolute and auditable.

**`rendering/swing_skeleton.py`** joins two pieces that were both built and
never called: significance ranking, and the HH/HL/LH/LL vocabulary in
`smc_visual_grammar.swing_label`. Neither had a consumer outside its own tests.

**Sides must alternate.** Ranking on prominence alone is the obvious
implementation and it fails on real data: the six strongest 4h swings on live
BTCUSDT were all lows, so every label read `LL` and the sequence described
nothing. Structure *is* the alternation of highs and lows, so the skeleton takes
the strongest swing on each side in turn. Prominence still chooses which high
and which low; it does not get to decide a chart has no highs on it.

**The skeleton is budgeted separately.** The seven-object native limit was
calibrated for story marks — zones, segments, labelled liquidity lines — which
are visually heavy. A swing tick is a different class. Sharing one budget meant
either clipping the skeleton to nothing (it ranks last on importance, so it
loses every tie) or inflating the story limit and letting heavy marks multiply.

## Two defects the live run exposed

**Selection ran before the window filter.** The pack ranked the top swings over
the whole context, the renderer then dropped anything off-canvas, and nothing
survived — the strongest swings across 400 bars are routinely older than the
90 bars a chart shows. The pack now supplies grades as facts; the renderer
selects among what it can actually draw.

**An empty label is not a blank mark.** The first swing on each side has no
predecessor, so `swing_label` correctly returns `""` rather than inventing an
`HH`. But the renderer falls back to the object kind, and the chart came back
stamped `SWING_HIGH` and `SWING_LOW` in text louder than the real structure
labels beside it. A bare `H` or `L` is the honest middle: it names the mark
without claiming a relationship to a swing that is not on the chart.

## Result on live data

BTCUSDT and ETHUSDT, live Binance, both `VALIDATED` with zero hard issues.

- **BTCUSDT 4h** went from 4 marks to 8, reading `H → L → LH → LL` — a lower
  high and a lower low, which is the bearish structure the 1d context claims.
- **ETHUSDT 1d** reads `H → BOS → L → LL → LH → INTERNAL CHOCH` across four
  months: the break down, the lower low, the lower high, then the recovery.

Both charts now let a reader check the BOS against the structure it broke,
which was impossible when the BOS tag floated in bare candles.

## Boundaries

- Descriptive. Selection can only narrow what is drawn; it never invents a swing
  the detector did not confirm, and creates no trade authority.
- Ungraded swings are dropped rather than assumed significant.
- The skeleton is fail-soft: a missing or malformed significance report yields
  an unlabelled chart, never a failed render.
- **The grade itself is still uncalibrated.** Nothing has tested whether a
  major-graded swing behaves differently from a minor one. This package makes
  the grade *consulted* and *consistently scarce*; it does not make it *true*.
  The mechanism harness from WP-SMC-23 is the instrument for that, and it is the
  honest next step.

## Validation

- Full source-bound suite: **1,546 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 14 new tests, centred on the alternation rule and on never emitting a marker
  without a label.
