# WP-SMC-12 — Evaluation Truth and Adapter Repair

Status: `VALIDATED_LOCAL_OBSERVE_ONLY`

This work package repairs the boundary between market evidence, human
evaluation, and the production-shaped detector records consumed by narrative
and market state. It creates no prediction, signal, paper, live, or execution
authority.

The 20-case markup folder built on 2026-08-08 is retained only as an audit
artifact. It is explicitly invalid because its decision slice admitted an
unclosed 15m candle, its regime labels were placeholders, the reviewer did not
receive the 1d chart used by the system, and its sealed answers omitted scorer
inputs. Tooling now refuses to mark or score that cohort.

## Evaluation-integrity contract

The corrected cohort path uses `markup_cohort_v2` and is deliberately
one-way:

1. A definition set can become scoreable only with
   `definition_set_status_v2`: analyst identity, timezone-aware review time,
   selection rationale, explicit `scoreable: true`, case count, the canonical
   case-ID hash, and the exact case-metadata hash must all reconcile.
2. The builder writes into a sibling staging directory and atomically renames
   it only after every case is complete. It refuses any existing output path;
   no rerun can replace a sealed answer beside an existing human markup.
3. Each chart, template, metadata file, system answer, source file, and causal
   timeframe slice is SHA-256 bound. The scorer verifies those bytes before
   reading human markup.
4. Detector or POI-lifecycle failure makes the case `FAILED` and the cohort
   `INVALID_GENERATION_FAILED`. A partial system run can never become `READY`.
5. Human markup uses `markup_annotation_v2` with explicit `COMPLETE` status and
   a completion timestamp. Genuine blank ranges, draws, and POIs remain valid;
   unfinished forms do not enter any denominator.
6. Structure uses one-to-one semantic matching and the ATR belonging to each
   annotation's timeframe. BOS, CHoCH, swing highs, and swing lows are scored;
   sweeps remain a recorded liquidity dimension until an expert approves a
   sweep-significance rule.
7. Every aggregate reports its own scored denominator. Decision agreement is
   explicit, and a defined zero-precision/zero-recall result has F1 `0.0`.

The shared contract lives in `smc_desk/evaluation/cohort_integrity.py`; the
builder and scorer import it rather than maintaining parallel schema or hash
logic.

The next gate is empirical: an analyst must select and justify a separate
12–15 case development cohort without seeing the system answers, then complete
one expert markup pass before any perception threshold is tuned.
