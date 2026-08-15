# WP-SMC-21 — Scoped Reconciliation and Measured Refusal

**Authority mode:** `observe_only_scoped_reconciliation_and_selective_measurement`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_SOURCE_BOUND`
**Gate:** `GATE-WP-SMC-21-SCOPED-RECONCILIATION-001`

## Why this work package exists

WP-SMC-20 built a genuinely rigorous honesty apparatus, and then the five-market
exercise refused every single market. Reading the run artifacts rather than the
summary showed the refusals were not all the same refusal.

On BTCUSDT the 1d controlling break survived V3 replay as
`EXTERNAL_MSS_CONFIRMED_BEARISH` (displacement 0.82) and the 4h survived as
`EXTERNAL_BOS_BEARISH` (displacement 1.0). Both engines agreed, both bearish.
What failed was 1h — a close 5.7 bps beyond structure with displacement 0.54 —
and 15m at 0.61. Those are genuinely marginal breaks that *should* fail.

But `_invariants` returned `REVIEW_REQUIRED` on any violation, `severity` was
hardcoded `"review"` for every check, and the validator raised one undifferentiated
hard issue. So a marginal 15m break vetoed a daily read that the system had just
verified against an independent implementation.

That is inverted against SMC's own doctrine, which the repository states
everywhere else: the context timeframe owns the narrative, and everything below
it is timing. A failed 15m break means the entry is not ready. It does not mean
the daily story is unknown.

## What changed

### 1. Reconciliation is scoped to the context timeframe

`_structure_role` ranks each check's timeframe against
`narrative_context.context_timeframe` from the V1 graph. Violations at or above
the context timeframe are `narrative`; below it they are `timing`. Status is now:

- `REVIEW_REQUIRED` — a narrative violation. The system does not know the story.
- `ENTRY_TIMING_WITHHELD` — timing violations only. The read stands; entry,
  stop and target authority does not.
- `PASS` — everything reconciled.

**Fail-closed by construction.** If the context timeframe is missing, unrankable,
or the narrative read is not coherent, every check is treated as narrative-owning.
An unclassifiable disagreement is never quietly downgraded to a timing note.

Entry authority is unchanged. `ENTRY_TIMING_WITHHELD` still blocks
`TRADE_PLAN_READY` through both the new
`entry_timing_unreconciled_blocks_trade_plan` hard issue and the
`COHERENT_CONTEXT_ENTRY_WITHHELD` story status. The disputed objects themselves
stay withheld — that logic is per-object and was already correct.

Re-derived against the five-market run: **BTCUSDT and CHFJPY** move from full
refusal to `ENTRY_TIMING_WITHHELD`. **GBPNZD, SOLUSDT and USDCHF** have their 1d
controlling break disputed and correctly stay `REVIEW_REQUIRED`. The change
rescues exactly the cases where the narrative genuinely survived, and nothing else.

### 2. Refusals became measurable

`selective_outcomes.py` was well built and nothing ever wrote to it. There was no
ledger on disk, so `missed_favorable_outcome_rate` — the metric that matters most
for a system whose default output is refusal — had no data, and "correctly
cautious" was indistinguishable from "broken and silent".

`build_shadow_decision_from_run` converts a completed run into a ledger decision,
and the live runner appends one per market, fail-soft. The essential detail is
that **refusals carry the read the system would have taken**. A refusal with no
shadow prediction is unfalsifiable: no later outcome can contradict it, so
refusing always looks free.

`uncertainty_score` is the measured fraction of controlling checks the stricter
replay rejected — not a confidence score. Absent reconciliation evidence scores
1.0, because missing evidence must never read as confidence.

Replayed over the five-market run: 5 refusals, each with a direction and a
measured uncertainty, `coverage: 0.0`, all five awaiting an outcome pass.
Coverage is now a number rather than an impression.

### 3. Clean-room independence is enforced transitively

The independence test parsed one hardcoded file's direct imports. The obvious way
to break independence — the oracle imports an innocent helper, the helper imports
production perception — would have passed. The test now walks the whole import
graph and additionally pins the reachable set, so a widening shared surface is
itself a failure. The property held before this change; only the test was weaker
than the property.

## Boundaries

- No detector threshold was tuned. No disputed object is rescued.
- `ENTRY_TIMING_WITHHELD` creates no entry, stop, target, paper or live authority.
- The ledger records decisions. It computes no accuracy: `selective_error` and
  `missed_favorable_outcome_rate` stay `null` until outcomes are resolved.
- Human adjudication remains the only route to "is the definition itself right".

## Known limitation, not repaired here

CHFJPY reaches `ENTRY_TIMING_WITHHELD` on the strength of its 1d check alone,
with 4h, 1h and 15m all disputed. That satisfies the rule as written, but a
context read resting on one surviving check is thinner evidence than BTCUSDT's
1d-and-4h agreement. Distinguishing the two would need a depth requirement on
the surviving narrative checks; it is recorded rather than tuned to the visible case.

## Validation

- Full source-bound suite: **1,482 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 13 new tests: scoped reconciliation including the fail-closed paths, the
  run-to-ledger adapter, and transitive clean-room independence.
