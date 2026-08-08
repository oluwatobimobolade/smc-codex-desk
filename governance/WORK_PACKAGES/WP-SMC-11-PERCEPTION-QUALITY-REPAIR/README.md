# WP-SMC-11 — Perception Quality Repair

Status: `IMPLEMENTED_LOCAL_OBSERVE_ONLY`
Authority: observe-only. This work package creates no signal, prediction,
paper, live, or execution authority.

## Why this work package exists

Every gate in this repository was green on 2026-07-17 and the system still
could not read a chart. The canonical live run
`analysis_runs/LIVE_TV_APP_BTCUSDT_20260717` passed governance, authority
boundaries, invariants and hash attestation, and produced:

- 15 confirmed "external" structure breaks and 5 CHoCH in 3.7 days of BTCUSDT
  15m data;
- 6,591 evidence objects in the pack handed to the AI;
- `final bias = mixed` from a Daily-bearish / 4H-bullish / 1H-bearish layout;
- exactly **one** drawn object on the chart — a 15m Internal CHoCH — despite a
  resolved 4H dealing range, price in premium, and two POI candidates.

Nothing failed, because nothing measured perception *quality*. The refusal
machinery was working perfectly and correctly refusing noise. The system was
honest and silent.

## Root causes addressed

### 1. No concept of significance

`specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml` defines major structure as an
11-bar fractal (`swing_scales.external: 5`), a break as 4 bps of penetration
(~$25 on BTC at 63,000), and requires no displacement
(`displacement_required: false`). Everything matching the geometric definition
became an object, so noise arrived wearing structural labels.

### 2. Bias resolved by unanimity vote

`formal_structure_graph._build_parent_child_context` resolved multi-timeframe
bias with:

```python
aligned_bias = aligned[0] if len(set(aligned)) == 1 else "mixed"
```

Any disagreement across 1d/12h/4h/1h collapsed to `mixed`, forcing
`THESIS_ONLY`. But a retracement *is* the child disagreeing with its parent.
Full alignment happens only mid-impulse. The rule therefore abstained during
exactly the conditions a trader waits for.

### 3. Annotation could not express a market story

`AnnotationPlanV2` supported `structure_segment`, `poi_zone`,
`liquidity_line`, `path_projection` and `trade_box`. There was no way to draw
a dealing range, equilibrium, premium/discount, a sweep, or an equal-highs
pool — so those could never appear even when the system knew them.

## What was implemented

### `smc_desk/perception/significance.py` (new)

Deterministic grading of swings and breaks into `major` / `intermediate` /
`minor` / `noise`, relative to ATR and to the active range. Additive,
observe-only, downgrade-shaped: it never invents or upgrades an object, and
every grade carries the numbers that produced it.

An unconfirmed wick probe can never grade above `noise`. A body close below
`MINIMUM_BREAK_DISPLACEMENT_ATR` (0.20 ATR) is not structure regardless of how
many basis points the detector allows. The range axis is suppressed inside
consolidations narrower than `MIN_RANGE_ATR_MULTIPLE` (3.0 ATR), where "a
large share of the range" describes noise.

Measured on `data/live_btc.csv` (351 bars, 3.7 days):

| | raw detector | after grading |
|---|---:|---:|
| external swings | 43 | — |
| confirmed external breaks | 15 | — |
| tradeable structure objects | 58 | **6** |
| major events | — | **3** (1 CHoCH, 2 BOS) |

### `smc_desk/perception/narrative_hierarchy.py` (new)

Replaces the vote with a hierarchy. The highest resolved context timeframe
owns bias; a disagreeing child is classified as a retracement *inside* that
bias; a child only threatens its parent by body-closing beyond a **verified**
protective level. States: `ALIGNED_CONTINUATION`,
`RETRACEMENT_WITHIN_PARENT`, `PULLBACK_ENDING`,
`PARENT_INVALIDATION_PENDING`, `RANGE_BOUND`, `INSUFFICIENT_CONTEXT`. No
combination of biases can return `mixed`.

Adds the question the old thesis never asked — **where is price drawn to?** —
resolving to the nearest unswept pool in the context direction, falling back
to the range extreme. Consumed liquidity is spent and cannot be a draw.

Adds `select_primary_poi`, which picks ONE POI aligned with context bias and
nearest the draw, recording the alternates, instead of hedging with a bullish
and a bearish candidate.

On the 2026-07-17 evidence, `mixed → refuse` becomes:

> 1d remains bearish; 4h is retracing inside that leg. Draw: unswept sell-side
> liquidity at 63,000. Primary POI: the 1h bearish OB at 64,512–64,974.
> Invalidation: body close beyond the 1d protected high at 67,000.

Wired into `build_mtf_structure_graph` as `narrative_context`, additive
alongside the untouched `parent_child_context`.

### Annotation vocabulary

`AnnotationDrawingObject` gains `range_zone`, `sweep_marker` and
`equal_levels`, plus kinds `range`, `sweep`, `equal_highs`, `equal_lows` and
the `equilibrium_price` field. The bridge resolves each from certified
evidence only and **derives equilibrium itself** — the planner supplies an ID,
never a coordinate. A range spans the visible window via `_window_span`
because it is context rather than a local event. The renderer draws the range
band with premium/discount shading, sweep markers and equal-level lines.

The fail-closed contract is unchanged: a range cannot be conjured from a
swing, unknown IDs still fail, and `ai_geometry_authority` remains `False`.

### Guard rails — `tests/test_perception_quality_guardrails.py`

The durable part. These run on committed real market data and fail the build
if any original regression returns:

- graded structure stays at human density (≤ 20 tradeable objects);
- grading still removes most raw detections;
- major events stay rare (≤ 8);
- character does not change every few hours (≤ 4 major CHoCH/week);
- no "major" break rests on a marginal poke;
- the 2026-07-17 layout is never refused as incoherent;
- every bias combination yields a named state;
- a coherent read always names a draw;
- the narrative never creates signal authority;
- the annotation vocabulary can still express a story.

Both quality rails were verified to **bite**: under the old behaviour the
density rail sees 58 objects against a ceiling of 20, and the unanimity vote
returns `mixed` on the pinned layout. A guard rail that cannot fail is
decorative; these were checked against the pre-repair behaviour.

## Related defects repaired in the same pass

- `swings.py` → detector version 2.1: tie-tolerant pivots (first touch wins),
  so tick-equal EQH/EQL pools stop annihilating both fractals; dual-pivot bars
  emit both objects. Five swing lows were being destroyed by exact ties in
  351 bars of live BTC data.
- `formal_structure_graph.py`: four invariants that could never fail now have
  reachable fatal branches, including recomputation of a claimed parent break.
- `narrative_hierarchy`: a protective level is only trusted when it is
  genuinely protective. The graph derives both protected sides from one broken
  swing price, which would otherwise manufacture parent invalidations from
  ordinary pullbacks.
- `programme_schema.graph_anchor_records`: guarded against the real graph
  emitting `liquidity_levels` as an integer count.

## Validation

- Full suite: **1135 passed, 1 skipped** (from 1077 before this work package).
- New focused tests: 62 across significance, narrative, vocabulary, guard
  rails and swing ties.
- Authority boundary check: PASS.
- No existing contract, schema field, or gate semantic was removed.

## Explicitly not claimed

- No predictive edge, and no evidence of one.
- No human-adjudicated perception accuracy. The thresholds in
  `significance.py` are reasoned defaults, not calibrated constants — they
  have never been scored against a professional markup.
- No promotion of any layer to trade authority. `signal_allowed` remains
  `False` throughout.

## Phase 2 — reasoning layer (added after the architecture audit)

The audit against the trader-brain vision found the reasoning half largely
unbuilt. Four further modules close the named gaps. All are additive and
observe-only; `signal_allowed` remains false throughout.

### Structural repairs from the 2026-07-14 audit

* **F1 — cross-scope protected points.** `_run_causal_protected_point_selection`
  pooled every swing scale with structure scope discarded, and
  `_match_candidate_to_swing` matched on price ±5bps and direction alone. A
  local pivot could become an external break's protected point. The pool is
  now scope- and timeframe-locked, and matching resolves **by exact evidence
  id first**, with price only used for non-swing cluster origins. Side is
  pre-filtered, so a bullish break can never adopt a swing high even by id.
  Measured on 1,500 BTCUSDT candles: **34 cross-scope substitutions → 0**,
  with 41 legitimate overrides still applying.

* **F2 — mixed-candle displacement.** A break object is created on the probe
  candle, so its body ratio and price bounds describe that candle; only
  penetration was updated on confirmation. Evidence now records
  `probe_candle_id`, `body_close_candle_id`, `is_delayed_confirmation` and the
  confirming candle's own body ratio, range and body size, and
  `score_break_displacement` prefers them. On real data one break scored
  **-0.17 body ratio from the probe where the confirming candle was 0.82** —
  a strong impulse read as weak. 18 of 70 external breaks took that path.

### `smc_desk/perception/liquidity_model.py` (new)

Liquidity was detected but never ranked, so every pool arrived with equal
standing and the draw defaulted to "nearest unswept". The model classifies
kind (prior week/day high-low, equal highs/lows, session levels, inducement),
scope (external beyond the dealing range vs internal inside it) and state
(swept liquidity is spent and can never be a draw), then scores importance
deterministically. Kind and timeframe dominate; touch count refines but does
not decide, so a triple-tapped 15m level still loses to a prior daily high.

Verified on live data: the draw stepped **past** the range extreme at 66,419
to target external equal-highs at 67,255 — correct, because external
liquidity beyond the range is what a completed leg reaches for.

### `smc_desk/perception/market_state.py` (new)

The system had no memory and answered in one shot. It now carries a running
picture — bias, range, protected levels, draw, swept and unswept liquidity,
primary POI and its alternates — and moves through the trader sequence:

    MAP_CONTEXT -> LIQUIDITY_EVENT_IDENTIFIED -> ACCEPTED_DISPLACEMENT
      -> POI_MAPPED -> PRICE_APPROACHING_POI -> PRICE_AT_POI
      -> LTF_CONFIRMATION_PENDING -> TRADE_PLAN_READY | INVALIDATED

Every state names **what it is waiting for** and **what would invalidate the
idea**; a state that cannot answer both is not one a trader would sit in.
`diff_states` supplies the memory: which liquidity was taken since the last
look, whether bias flipped, whether the POI moved, whether the setup advanced
or regressed. Arrival is required before confirmation is even considered.

On live BTCUSDT the pipeline reports `ACCEPTED_DISPLACEMENT`, waiting for a
causally-owned POI — with context, draw and displacement each recorded as the
reason it got that far.

### `smc_desk/brain/narrative_annotation_planner.py` (new)

Selects what to draw in a trader's order: range first for location, then the
ranked structure that built the context. Emits **evidence ids only** — a test
asserts the planner cannot leak a price or timestamp. Two rules came directly
from rendering real data: an internal break sharing a price with its external
twin is dropped (it stacked two labels on one line and hid the more important
one), and marks closer than 0.35 ATR are dropped as visually identical.

## Required next work

1. Score the graded output against a human markup on 10–15 charts. Until that
   exists there is no error signal, and every threshold here is a defensible
   guess rather than a measurement.
2. Feed `narrative_context` into the thesis writer and the annotation planner
   so the improved read reaches the chart, not just the graph.
3. Revisit `swing_scales` and `structure_break_min_bps` themselves once the
   grading layer has been validated; grading currently compensates for loose
   detector thresholds rather than correcting them.
