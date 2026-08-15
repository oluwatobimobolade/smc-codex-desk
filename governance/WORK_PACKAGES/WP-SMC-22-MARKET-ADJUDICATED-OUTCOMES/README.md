# WP-SMC-22 — Market-Adjudicated Outcomes

**Authority mode:** `observe_only_market_adjudicated_outcome_resolution`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_SOURCE_BOUND`
**Gate:** `GATE-WP-SMC-22-MARKET-ADJUDICATED-OUTCOMES-001`

## Why this work package exists

WP-SMC-21 made the system log what it decided and the read it would have taken.
Nothing scored those reads. `coverage: 0.0` sat in the report as an
uninterpretable number and `missed_favorable_outcome_rate` stayed `null`, so a
system correctly staying out and a system broken and silent produced identical
ledgers.

The constitution already says who settles this. Line 45:
`human_alignment: optional_external_audit_not_autonomous_truth_owner`. The
markup cohort's own report agrees: *"One reviewer is not adjudicated truth; it
is one expert opinion."* The adjudicator is the market, through the
MECHANISM / FORECAST / ECONOMIC rungs — all three of which had **zero
implementation**. Nothing in `smc_desk/`, `tools/` or `tests/` referenced
`MECHANISM_SUPPORTED`, `FORECAST_CALIBRATED` or `ECONOMICALLY_REPLICATED`.

This package builds the measurement those rungs stand on.

## What it does

`evaluation/outcome_resolution.py` scores one logged DECISION against the
candles that followed it, under a frozen, named rule:

`triple_barrier_1atr_20bar_close_return_v1`

- **`shadow_prediction_correct`** — did the close-to-close move at the horizon
  verify the recorded direction, outside a 0.25 ATR neutral band.
- **`favorable_opportunity`** — did price run a full ATR in the recorded
  direction *before* running one against it. This is what makes
  `missed_favorable_outcome_rate` mean "how often does caution cost something".
- **`outcome_return_bps`** — signed in the recorded direction.

The two verdicts are deliberately distinct. The demonstration run below contains
a case with `correct=False, favorable=True` (price ran, then reversed past the
close) and three with `correct=True, favorable=False` (the direction verified
without ever offering a clean ATR run). Collapsing them would lose that.

### Refusing rather than guessing

- Forward candles opening **before** the decision raise `LookaheadError`. This
  is the error class the project exists to prevent, and it has been introduced
  in this repository before by treating a candle's open as its close. The
  boundary is `open >= decision_time` — equality is legitimate, because
  `decision_time` is the close of the last seen candle and the next one opens
  exactly on it — and anything earlier is refused, not scored.
- Fewer candles than the horizon returns `UNRESOLVED`, and the tool **does not
  write** it. An UNRESOLVED event would claim the case was examined and settled;
  leaving it unwritten lets a later pass score it when the market has produced
  the horizon.
- A bar spanning both barriers resolves to `none`. Intrabar order is unknowable
  from OHLCV, and ambiguity is never resolved in the system's favour.
- Missing or non-positive ATR is `DATA_FAILED`, never a zero-width barrier.

## Demonstration

Ten real BTCUSDT 15m decision points across 2022-2026 from stored Binance
futures data, scored by `tools/resolve_selective_outcomes.py`:

```
resolved: 10   awaiting_market: 0   data_failed: 0
coverage:                        0.0
false_omission_rate:             0.3
missed_favorable_outcome_rate:   1.0
area_under_risk_coverage_curve:  0.653
```

**This is a test of the resolver, not an SMC claim.** The "read" was a naive
prior-20-bar momentum sign, chosen precisely because it carries no SMC content.
What it demonstrates is that the machinery produces the constitution's required
metrics from real candles.

Note also that `missed_favorable_outcome_rate` is definitionally 1.0 whenever
coverage is 0: a system that accepts nothing misses every opportunity. It only
becomes informative once the system accepts some cases. The number that carries
information today is `false_omission_rate`.

The five live decisions from the 2026-08-14 five-market run cannot be scored
yet — stored forward data ends 2026-06-27. They correctly report
`awaiting market` and remain unwritten.

## Boundaries

- Resolution is descriptive. It feeds no detector, tunes no threshold, promotes
  no object, and creates no signal, paper, or live authority.
- Under the constitution this is evidence toward MECHANISM / FORECAST, not
  toward `DEFINITION_CONFORMANT`, and it is not a predictive edge claim.
- The outcome definition is frozen and stamped on every event. Changing any
  constant requires a new definition id, so old results stay comparable.
- One outcome per case: the ledger refuses duplicate event ownership.

## Still missing above this rung

`MECHANISM_SUPPORTED` needs preregistration and a **matched baseline**. Price
revisits most levels eventually, so "price returned to my order block" is
trivially true and proves nothing until measured against control zones matched
on size, location and recency. That baseline is the next piece, and without it
association numbers are confirmation rather than evidence.

## Validation

- Full source-bound suite: **1,504 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 21 new tests, concentrated on the lookahead boundary and the refusal paths.
