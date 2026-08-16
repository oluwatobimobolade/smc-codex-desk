# WP-SMC-27 — Session Record: Evidence, Annotation, and What Refusal Was Hiding

**Authority mode:** `record_only_no_new_authority`
**Status:** `RECORDED`
**Covers:** commits `0ffe90b` through `22589e5`

A record rather than a change. Nothing here creates authority; it exists so the
next person — including the founder in a month — can see what was established,
what was disproved, and what was deliberately left alone.

## The arc

The session began with the system refusing every market and ended with it
producing coherent trader-shaped reads on five. The refusals were never the
problem. Three separate layers were computing answers that nothing downstream
consumed, and the sparse charts and universal `REVIEW_REQUIRED` were symptoms of
that, not of excessive caution.

## What was established

**The mechanism rung exists and returns negatives.** `MECHANISM_SUPPORTED` had
no implementation; it now has a sealed preregistration, a matched-control arm, a
dependence-aware bootstrap and the Harvey/Liu/Zhu t ≥ 3.0 bar. Its first three
verdicts were `DATA_FAILED`, `MECHANISM_NOT_SUPPORTED` and a contradicted
prediction — which is the point.

**One rule replicated out of sample.** Direction-aware location — supply in
premium, demand in discount — lifted the hold rate on the held-out half of five
of five instruments: BTC +8.1%, ETH +9.9%, SOL +11.5%, XRP +14.4%, BNB +3.6%.
Expectancy roughly doubles. It is the only factor with held-out evidence behind
it, and the POI weights were revised on it under a seal written first.

**Refusals became measurable.** The selective-outcome ledger now records a
decision per run carrying the read the system *would* have taken, so a refusal
can be scored later instead of being unfalsifiable.

**The narrative reads as SMC.** Context timeframe, retracement, confirming
timeframes, draw on liquidity, invalidation — with a selected primary POI and
its alternates.

## What was disproved, and stayed disproved

**The significance grade does not discriminate.** It decides which swings appear
on every native chart. Tested against penetration acceleration on two markets,
the prediction was contradicted at six of six horizons. The grade was left in
place — it still supplies consistent scarcity — but the justification "these are
the swings that matter" is unsupported and the code says so.

**Fair value gaps did not replicate.** Positive direction on both markets
(continuation, not fill, which runs against the retail belief), but opposite
horizon profiles on BTC and ETH and no horizon clearing the bar on both.

**Raw FVGs and all-scale swing penetrations are untestable.** At one gap per
7 bars and one penetration per 3.8, there is no uncontaminated control. A
pattern that frequent is a description of ordinary price behaviour.

## Six defects found in this session's own work

Recorded because each was caught by testing rather than review, and the pattern
matters more than any one of them.

1. **The block bootstrap resampled a non-series** — pooled arms, so blocks
   preserved nothing. The dependence correction was decorative.
2. **The matched design was discarded** — pairing thrown away for pooled means.
   Fixing 1 and 2 moved BTC from `NOT_SUPPORTED` to `BOUNDARY_SENSITIVE`; the
   first commit had *under*-reported the effect.
3. **Every hypothesis was scored with forward returns** regardless of its
   declared observable.
4. **The live runner was broken for days** — a function appended after the
   `__main__` guard, so every symbol died with `NameError` and the handler wrote
   `status: FAILED` while the script exited zero.
5. **`htf_aligned` was dead and `location_in_range` was never direction-flipped**,
   which is why the first feature test concluded nothing separates.
6. **One pivot was drawn three times** at three detection scales, labelled `L`,
   `LL`, `LL` — a swing declared a lower low than itself.

## Two things attempted and reverted

**Raising the annotation object cap.** Measuring first showed it would have drawn
eight arbitrary objects from forty-six equally-labelled ones — richer-looking and
less accurate.

**Admitting off-window structure marks.** Built, rendered, and reverted on sight:
it also admitted an IDM priced outside the visible range, which expanded the
y-axis by a third and compressed every candle into half the frame. The object
count improved from 0 to 2 and the chart got worse.

## What is left, in priority order

### Blocking a trade

1. **Risk module** — stop, target, R, expectancy. Every input is already in
   `market_state`. Live BTC priced at R = 0.07 against the narrative invalidation
   and R = 3.94 against the setup invalidation: the same trade, two stops.
2. **Separate the two invalidations** — narrative belongs in the thesis, setup
   belongs on the stop. Same package as 1.

Until these exist coverage stays at 0.0, and every research result terminates in
the same `REVIEW_REQUIRED` whether it is good or bad.

### Annotation

3. **4h episode selection** — the latest external episode is weeks stale while
   the visible trend broke structure repeatedly. Upstream of rendering; a
   render-side fix was tried and made things worse.
4. **Thesis Bias Summary** still prints the legacy `final bias=mixed` beneath the
   coherent hierarchical read. Cosmetic, but a contradiction on the page.

### Research

5. **Rolling case library** — the only design that can measure `swept_before`,
   `left_imbalance` and `distance_to_draw`, currently held in
   `ROLLING_ONLY_FEATURES`. The Osler-backed feature is among them.
6. **Regime labelling** — required by the sealed supplement. Location showed
   −27% in one regime and +11.5% in the next and nobody has characterised the
   difference.

### Longer-lived

7. **P6** — the six-role tool loop exists and is not on the live path. In
   local-deterministic mode no model challenges anything, so the AI reasoning
   layer is still unexercised on real runs.
8. **Human markup cohort** — 0 of 20 scored. Only the founder can do it.
9. **Four label families remain `NOT_EVALUATED`** — order block, CHoCH/MSS/BOS
   semantics, liquidity draw, structural level interaction. These carry the SMC
   meaning.
10. **Rungs 4 and 5** — `FORECAST_CALIBRATED` and `ECONOMICALLY_REPLICATED` have
    no implementation.

## Standing limitations

- Coverage is 0.0. The system has never produced a trade.
- The location finding sits inside a single market regime; five instruments
  agreeing within one regime are not five independent tests.
- POI ranking weights are revised but uncalibrated, and the causal authority —
  not the ranking — still owns which POI is primary. That is deliberate.
- No signal, paper, live, or predictive-edge authority exists anywhere.
