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

### Qualified fair value gaps

The constitution keeps qualification separate from raw geometry, so the
qualified subset is a different object, not a second attempt at the same one.
Both runs are reported here, which is the condition under which running both is
legitimate.

Two markets, 20,000 candles each, balance **passed** on both.

**BTCUSDT 15m — BOUNDARY_SENSITIVE.** 207 pairs, median spacing 66 bars.

| Horizon | Treated | Control | Paired difference | t | p | Passes |
|---|---|---|---|---|---|---|
| 10 | +14.94 bps | −7.32 bps | **+22.27** | **3.19** | 0.001 | **Yes** |
| 20 | +12.77 bps | −4.86 bps | +17.63 | 2.18 | 0.015 | No |
| 40 | +10.09 bps | −7.28 bps | +17.38 | 1.93 | 0.027 | No |

**ETHUSDT 15m — MECHANISM_NOT_SUPPORTED.** 237 pairs, median spacing 58 bars.

| Horizon | Treated | Control | Paired difference | t | p | Passes |
|---|---|---|---|---|---|---|
| 10 | +13.09 bps | +1.02 bps | +12.08 | 1.16 | 0.127 | No |
| 20 | +21.40 bps | −1.10 bps | +22.50 | 1.95 | 0.027 | No |
| 40 | +31.58 bps | +4.44 bps | +27.14 | 1.79 | 0.037 | No |

**The cross-market comparison is the strongest result here, and it is negative.**
A real mechanism should replicate. BTC's effect is largest at the shortest
horizon and decays with distance; ETH's is smallest at the shortest and grows.
Opposite profiles on two highly correlated instruments over the same period.
Direction is positive throughout — continuation rather than fill, which runs
against the retail belief and with the work disputing it — but the shape does
not survive changing the market, and no horizon clears the bar on both.

BTC's 10-bar horizon is the one cell that passes, at t = 3.19. On its own that
would be a finding. It is not one, because the preregistered rule requires every
declared horizon to agree, and because ETH does not reproduce it. Reporting the
passing cell while omitting the rest is explicitly listed as prohibited in the
preregistration, and this is the case it was written for.

## Three defects found in this package's own code, after the first commit

Recorded because the numbers above changed when they were fixed, and a result
that moved deserves to say so.

**The block bootstrap was resampling a non-series.** It pooled `[treatment,
control]` into one array and drew blocks from that. Blocks only preserve serial
dependence when adjacent entries are adjacent *in time*; in a pooled array they
are returns from scattered indices, and any block straddling the arm boundary is
meaningless. The correction reduced the effective sample per test but produced a
better-powered design.

**The matched design was being discarded.** Each event was matched to its own
controls and then compared against the pooled control mean — which throws away
the pairing that matching exists to create. The test now runs on the per-event
difference series, which is both paired and genuinely time-ordered, so the block
bootstrap has something real to block over.

Together these changed the BTCUSDT verdict from `MECHANISM_NOT_SUPPORTED` to
`BOUNDARY_SENSITIVE`: the 10-bar horizon moved from t = 2.55 to t = 3.19 and now
clears the bar. **The first commit under-reported the effect.** The corrected
statistics are more favourable, not less, which is worth stating plainly — the
error was not in the conservative direction.

**Every hypothesis was scored with forward returns regardless of what it
declared.** `FVG_FILL_RATE_V1` registers `band_touch_within_horizon` and would
have been answered with a directional-return number carrying the fill-rate id.
Observables now dispatch by name and an unimplemented one returns
`NOT_EVALUATED` rather than a substitute.

## Not run, and why

`SWING_LIQUIDITY_ACCELERATION_V1` is the hypothesis closest to Osler's
documented result, and it is refused. It concerns the moment price *trades
through* a confirmed swing extreme — a penetration, which occurs later than the
swing's own confirmation and may never occur at all. The available event source
is confirmed swings, which is a different event. Running it on swings would
measure one thing and stamp it with another hypothesis's id, which is the exact
substitution the observable dispatch was added to prevent. The runner refuses it
until a penetration-event extractor exists.

## Boundaries

- A certificate here proves a preregistered association with a named observable.
  It cannot establish participant identity, deterministic causation, forecast
  quality, or economic value, and creates no signal, paper or live authority.
- Two markets, one timeframe, one detector configuration. The replication that
  was attempted failed, which is itself the result.
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

- Full source-bound suite: **1,528 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 24 new tests. The two that matter: a random walk at a powered configuration
  must not certify (checked across four seeds), and a planted effect must be
  detected — a harness that can only say no is as useless as one that can only
  say yes.
