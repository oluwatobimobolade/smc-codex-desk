# WP-SMC-26 — Scoped Reconciliation Completion

**Authority mode:** `observe_only_scoped_reconciliation_completion`
**Status:** `PASS_LOCAL_OBSERVE_ONLY_SOURCE_BOUND`
**Gate:** `GATE-WP-SMC-26-SCOPED-RECONCILIATION-001`

## Why

WP-SMC-21 scoped the reconciliation gate: a disputed break **at or above** the
context timeframe means the story is unknown; one **below** it means the entry
is unavailable while the read stands. That fix reached the validator and the
renderer. It reached neither the trader state machine nor the thesis writer,
both of which kept the old all-or-nothing rule.

The consequence was total and silent, on runs the validator had already passed.

## What was broken

**`market_state.py`** bailed to `NO_CONTEXT` with `bias: "unknown"` on any
status other than `PASS`. So `select_primary_poi` — and with it the entire POI
ranking built in WP-SMC-21 — never executed on a single live run. The founder
asked whether the narrative picks the best POI. It was not picking one at all.

**`smc_thesis_ai_v1.py`** did the same, and the result contradicted itself on
the page. The published BTCUSDT thesis listed the surviving V3 structure as
"1d bearish; 4h bearish; 1h bearish; 15m bearish" and then concluded
"final bias=mixed. Decision-authority bias remains unresolved." Four agreeing
timeframes reported as a mixed read.

## What changed

Both now scope on `{PASS, ENTRY_TIMING_WITHHELD}` rather than `PASS` alone, and
`market_state` records the withheld entry in its reasons rather than discarding
the context.

Entry authority is unchanged and explicitly re-guarded: when the lower-timeframe
confirmation is present *and* its timeframe failed V3 replay, the machine now
stops at `LTF_CONFIRMATION_PENDING` instead of promoting to `TRADE_PLAN_READY`.
Without that guard, scoping the gate would have handed back exactly the entry
authority the gate exists to withhold.

## Result on live data

**Before** — BTCUSDT and ETHUSDT: `NO_CONTEXT`, `bias: unknown`, no POI.

**After** — BTCUSDT: `LTF_CONFIRMATION_PENDING`, bias bearish, primary POI
selected as the 4h bearish order block at 62800.0–63613.6, waiting on a 15m
displacement break after the recorded sweep. ETHUSDT: `ACCEPTED_DISPLACEMENT`,
bias bearish, no POI yet — honestly reported as waiting for a causally-owned POI
aligned with context.

The narrative reads as a proper multi-timeframe SMC story:

```
State: RETRACEMENT_WITHIN_PARENT
Context: 1d bearish · Retracing: 15m · Confirming: 4h, 1h
Draw on liquidity: bearish toward 62248.5 (equal_lows)
Invalidation: price body-closes beyond the 1d protected high at 82828.7
```

## A dead-code audit, and what it found

The two defects above are the same disease as WP-SMC-24's: machinery built and
never called. A scan of every public function across `perception`, `brain`,
`rendering`, `decision` and `evaluation` flagged 83 with no consumer outside
their own module. Spot-checking the narrative-critical ones — `resolve_liquidity_draw`,
`score_importance`, `classify_kind`, `summarize_liquidity_sequence`,
`build_structure_hierarchy` — showed all are used internally by modules that are
themselves called, so the scan over-reports and the narrative path is wired.

The disease is real but localised. Three genuine cases have now been found and
fixed: the significance grade (WP-SMC-24), `swing_label` (WP-SMC-24), and the
POI ranking (here).

## Known remaining, not fixed

Section 1 of the thesis still prints the legacy V1 vote line, `final bias=mixed`,
directly beneath the coherent hierarchical read. It is cosmetic and it is a
self-contradiction on the page. Recorded rather than patched in the same change
that fixed the substantive gate.

## Validation

- Full source-bound suite: **1,564 passed, 1 skipped**.
- Governance consistency: PASS. Authority-boundary scan: PASS.
- 3 new tests pinning the scoped behaviour, including that a narrative-level
  disagreement still stops the machine.
