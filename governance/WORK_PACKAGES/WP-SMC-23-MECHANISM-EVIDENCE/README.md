# WP-SMC-23 — Mechanism Evidence

**Authority mode:** `observe_only_preregistered_mechanism_association`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_SOURCE_BOUND`
**Gate:** `GATE-WP-SMC-23-MECHANISM-EVIDENCE-001`

## Why this work package exists

Three of the five authority rungs had no implementation. `MECHANISM_SUPPORTED`,
`FORECAST_CALIBRATED` and `ECONOMICALLY_REPLICATED` were names in a YAML file,
never referenced anywhere in `smc_desk/`, `tools/` or `tests/`. This builds the
first of them.

The published record does not validate Smart Money Concepts as a packaged
system. It does document several of the behaviours the doctrine gestures at —
most directly Osler's finding, from the complete Royal Bank of Scotland order
book, that stop orders cluster just beyond round numbers and that price
accelerates through those clusters. So the hypotheses here are about
mechanisms, not doctrine. None says "an order block works".

## What was built

**`specs/MECHANISM_PREREGISTRATION_V1.yaml`**, hash-sealed, written and sealed
*before* any result was computed. Three hypotheses, each with its observable,
horizons, control design and thresholds fixed in advance. `certify_mechanism`
refuses any hypothesis id not in the sealed file, which is what stops a result
from being chosen after the fact.

**`evaluation/matched_baseline.py`** — controls matched on size, location and
recency. Price revisits most levels eventually, which makes an uncontrolled
"the zone worked" unfalsifiable; the control arm is what turns it into a claim
that can fail. Exclusion is forward-only, because a bar *before* an event cannot
carry its effect. Events that cannot be matched are reported, never paired
loosely — dropping one costs power, a bad match costs correctness, and only one
of those is recoverable.

**`evaluation/mechanism_evidence.py`** — three guards against the standard ways
this kind of study goes wrong:

- **Stationary block bootstrap.** Outcome windows overlap, so observations are
  not independent and a plain t-test overstates significance. Blocks no shorter
  than the horizon preserve the dependence.
- **Harvey/Liu/Zhu threshold.** t ≥ 3.0, not the conventional 2.0, on the
  grounds that the conventional bar is far too permissive given how much has
  been tested. Plus a Benjamini-Hochberg step-up across horizons.
- **Covariate balance check.** An unbalanced comparison measures the imbalance,
  not the mechanism, so a standardised mean difference past ~0.1 fails the
  certificate closed.

## Results on real data

### Raw fair value gaps — DATA_FAILED, and the reason is the finding

BTCUSDT 15m, 20,000 candles, 2,171 confirmed gaps. **Median spacing between
gaps: 7 bars.** Against a 40-bar horizon that leaves essentially no
uncontaminated control period: 2,066 of 2,171 events could not be matched, and
balance failed.

This is not a limitation to work around. A pattern that occurs every seven bars
is not a signal, it is a description of ordinary price behaviour, and the
question "does a gap predict continuation" has no counterfactual because the
market is almost never outside one. The matched baseline made that visible
immediately; without it the same data would have produced a confident number.

### Qualified fair value gaps — MECHANISM_NOT_SUPPORTED

The constitution keeps qualification separate from raw geometry, so the
qualified subset is a different object, not a second attempt at the same one.
Both runs are reported here, which is the condition under which running both is
legitimate.

215 events, median spacing 66 bars, balance **passed**.

| Horizon | Treated | Control | Difference | t | p | Passes |
|---|---|---|---|---|---|---|
| 10 | +14.94 bps | −4.69 bps | **+19.63** | 2.55 | 0.006 | No |
| 20 | +12.77 bps | −1.43 bps | +14.21 | 1.19 | 0.124 | No |
| 40 | +10.09 bps | −4.66 bps | +14.75 | 0.94 | 0.177 | No |

**This is the clearest possible demonstration of why the threshold matters.** At
the conventional t ≈ 2.0 bar, the 10-bar horizon passes — t = 2.55, p = 0.006 —
and the honest-sounding conclusion would have been "qualified fair value gaps
predict continuation". At the preregistered t ≥ 3.0 it does not survive, and the
effect decays across horizons instead of persisting.

Two things are worth keeping from a negative result. The direction is
consistently positive at every horizon, which is *continuation*, not fill —
directionally against the retail "gaps fill" belief and consistent with the
published work disputing it. And the magnitudes are small: roughly 15–20 basis
points before costs.

## Boundaries

- A certificate here proves a preregistered association with a named observable.
  It cannot establish participant identity, deterministic causation, forecast
  quality, or economic value, and creates no signal, paper or live authority.
- Single market, single timeframe, single detector configuration. Nothing here
  generalises until it is replicated.
- The bucket counts in the control matching were raised from 4/4 to 5/10 because
  a four-way split left location imbalanced at 0.19 SD. That is a design choice
  about the control arm made against a balance diagnostic, not a threshold tuned
  until a result turned significant — which the preregistration forbids.

## Also in this package

`poi_quality` ranking weights are now frozen by a tripwire test. They are
reasoned defaults that nothing has scored, and tuning them against outcomes is
a parameter search: fifty combinations at the 5% level give roughly a 92% chance
one looks significant by chance. Changing them is allowed, but it must come with
a multiple-testing correction, and the test is where that gets noticed.

## Validation

- Full source-bound suite: **1,524 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 20 new tests. The two that matter: a random walk at a powered configuration
  must not certify (checked across four seeds), and a planted effect must be
  detected — a harness that can only say no is as useless as one that can only
  say yes.
