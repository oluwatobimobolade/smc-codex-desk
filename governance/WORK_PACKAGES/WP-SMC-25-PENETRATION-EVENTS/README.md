# WP-SMC-25 — Penetration Events and the Grade Test

**Authority mode:** `observe_only_preregistered_mechanism_association`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_SOURCE_BOUND`
**Gate:** `GATE-WP-SMC-25-PENETRATION-EVENTS-001`

## Why

Two threads needed the same missing piece. `SWING_LIQUIDITY_ACCELERATION_V1`
had been sealed since V1 and never run, because the runner had no way to name
the event — and it is the hypothesis with the strongest evidence behind it,
Osler's Royal Bank of Scotland order book showing stops cluster just beyond
prior extremes and price accelerating through them.

The second thread was closer to home. WP-SMC-24 made the significance grade the
selector for every swing drawn on every native chart, and that grade had never
been tested against anything. A selection rule that decides what a reader sees,
and has never been falsifiable, is exactly what this ladder exists to catch.

## What a penetration is, and is not

* A **break** requires a body close beyond the level. It is about structure.
* A **penetration** requires only that price traded through. It is about
  *orders* — resting stops beyond the level have been filled.

Osler's cascade is the second, so a wick counts. Four rules keep it honest:
only interactions at or after `confirmed_at` (a swing needs bars to its right,
so price can trade through a level before the system could identify it);
approached from the protected side; first touch only, because the resting orders
are gone after it; and age recorded but never gated, since order decay is
exactly the kind of threshold the constitution calls `doctrine_undefined`.

Stacked levels taken by one candle deduplicate to one event. Counting them
separately would inflate the sample with observations sharing a single outcome
window — the dependence a block bootstrap models, smuggled in as extra n.

## A confound found and removed before first use

`realised_range_expansion` included the event bar in its "after" window. A bar
that just traded through a prior extreme is, by construction, a wide bar — it
reached further than every bar before it. Measuring from it would have asked
"is the breaking candle big?", which is close to a tautology and would report a
large effect on any data at all. The window now starts one bar later, which asks
what the hypothesis actually poses: does the movement *continue*.

The function was written in WP-SMC-23 and never executed, because the swing
hypothesis was refused for want of this extractor. The confound was fixed before
its first real use.

## Results

### SWING_LIQUIDITY_ACCELERATION_V1 — UNDERPOWERED, and the reason is the finding

BTCUSDT 15m, 20,000 candles: 15,802 confirmed swings, **5,205 penetrations —
one every 3.8 bars, median 2 bars from confirmation to penetration.**

That is not a stop cascade, it is ordinary price movement. The detector emits
swings at three scales, and a one-bar pivot is taken almost immediately by
definition. As with raw fair value gaps, the pattern is too frequent for an
uncontaminated control to exist: 23 of 5,205 events could be matched at the
5-bar horizon, and balance failed.

The all-scales reading of the sealed hypothesis is therefore untestable on this
detector. That is reported rather than repaired by narrowing the scale after the
fact, which the preregistration prohibits.

### SWING_GRADE_DISCRIMINATION_V1 — the prediction is contradicted, and it replicates

Prediction: major-graded penetrations show greater acceleration than
minor-graded ones, each arm against its own matched controls.

| Market | Horizon | Major effect | Minor effect | Major − Minor | p |
|---|---|---|---|---|---|
| BTCUSDT | 5 | 0.101 | 0.140 | **−0.039** | 0.69 |
| BTCUSDT | 10 | 0.077 | 0.141 | **−0.064** | 0.79 |
| BTCUSDT | 20 | 0.078 | 0.107 | **−0.029** | 0.61 |
| ETHUSDT | 5 | 0.105 | 0.141 | **−0.035** | 0.72 |
| ETHUSDT | 10 | 0.081 | 0.133 | **−0.052** | 0.83 |
| ETHUSDT | 20 | 0.022 | 0.094 | **−0.072** | 0.89 |

**Six of six horizons across two markets point the wrong way.** The grade does
not select the swings whose penetration matters more; on this observable the
minor-graded ones behave more energetically, consistently.

The minor arm is also the one carrying a real effect. On BTCUSDT it clears the
preregistered t ≥ 3.0 bar at 5 and 10 bars (t = 5.01, 4.54); on ETHUSDT at all
three (t = 4.88, 4.76, 3.27). Penetration acceleration appears to be real. It
simply is not what the grade is tracking.

## The caveat that matters

**The major arm failed its covariate balance check on both markets, and the ETH
minor arm did too.** Both certificates are `DATA_FAILED` for that reason, so the
effect *magnitudes* above are not reliable estimates.

The cause looks structural rather than incidental: a penetration is by
definition an event at a range extreme, and there are few unpenetrated control
bars at comparable extremes to match against. This may be a real limit on
matched-control designs for this event class.

No parameter was adjusted to repair it. Widening the recency window or coarsening
the location buckets would probably have produced balanced arms, and doing so
*after seeing the result* is the tuning the preregistration forbids — the same
discipline that made the earlier bucket change acceptable makes this one not.

What survives the caveat is the **sign**: the predicted direction is contradicted
in six of six horizons across two markets. Balance failure inflates uncertainty
about magnitude; it does not readily produce a consistent wrong sign.

## What this means for WP-SMC-24

The structure skeleton stands, on narrower grounds than it was built on.

Drawing a selected structural sequence is still better than drawing a BOS tag in
bare candles, and the grade still supplies consistent scarcity — a chart-sized
set on every timeframe. But the justification "these are the swings that matter"
is **not supported by this evidence**, and the honest reading is that the
skeleton currently draws a *legible* sequence rather than a *significant* one.

No change is made to the renderer here. Changing the selector on the strength of
one contradicted hypothesis, whose arms failed balance, would be reacting to a
result rather than to evidence.

## Boundaries

- Descriptive. Naming an event grants no signal and makes no claim about what
  follows; that is what the mechanism rung tests.
- Two markets, one timeframe, one detector configuration.
- Both grade arms carry balance failures; magnitudes are unreliable.
- No detector threshold, matching parameter, or grade constant was tuned.

## Validation

- Full source-bound suite: **1,561 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 15 new tests, concentrated on the lookahead boundary, the wick-versus-close
  distinction, first-touch-only, and same-bar deduplication.
- Preregistration V2 sealed **before** any of these runs; V1 remains on disk
  unchanged as the provenance of the fair-value-gap results.
