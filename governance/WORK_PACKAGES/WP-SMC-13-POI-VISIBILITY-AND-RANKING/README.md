# WP-SMC-13 — POI Visibility and Ranking

**Authority mode:** `poi_visibility_and_ranking_observe_only`
**Status:** PASS_LOCAL_OBSERVE_ONLY_EMPIRICAL_CERTIFICATION_UNCHANGED

## Why this work package exists

The founder pointed at a CADJPY 4H chart and named a supply zone at
112.828-113.721 that the system had not marked. The zone was valid: it was the
last opposing candle before a departure that displaced roughly 1.9x ATR and
broke structure at 112.707, and it was unmitigated. The detector had found it
and then deleted it, because its body was 0.106 of its range and the
`ob_min_body_factor` gate demanded 0.75.

That is the wrong shape of failure. A turning-point candle is habitually
small-bodied, so a body filter deletes exactly the zones worth watching, and it
deletes them at detection time, where the information cannot be recovered. The
founder's instruction was explicit: *"I need a system that sees everything ...
then maybe the AI chooses which will work and why."*

This work package separates those two jobs.

## What changed

### 1. Detection stopped deleting candidates

`order_blocks.py` now records body ratio and gate status as facts on the
evidence (`below_body_floor`, `admission_status`, `caused_structure_break`)
instead of using them to `continue`. Candidates that fail the causal admission
gate are emitted with `poi_grade=False` rather than discarded, and `poi_grade`
is no longer coupled to body size — it reflects causation, which is what
actually validates an order block.

Identical zones produced by overlapping clusters are deduplicated on
`(direction, price_low, price_high, first_cluster_id, last_cluster_id)`,
preferring the `poi_grade=True` and external-scope survivor.

CADJPY 4H went from 2 emitted order blocks to 11. The founder's zone is among
them, with `poi_grade=True`.

### 2. Ranking decides, and says why

`perception/poi_quality.py` is new. It ranks candidates in SMC order:
causation, then scope (external over internal), then displacement quality, then
premium/discount location, then freshness — with **proximity demoted to a
tie-break**. Every score carries the reasons that placed it.

Body ratio is deliberately absent from the ranking. It is a recorded fact, not
evidence about whether a zone matters.

### 3. Two pre-filters that made ranking pointless were removed

`select_primary_poi` sorted aligned candidates by distance to the draw and
nothing else, while its own docstring claimed it weighed equilibrium. It did
not. It now delegates ordering to `rank_pois` and accepts the resolved dealing
range so premium/discount is measured against the range price is actually
trading in.

`smc_evidence_pack_builder` collected only `primary_causal_poi` from each
scenario and discarded `secondary_reaction_pois`, so the ranking would have
been ranking a field of one and could never overturn an upstream choice. Every
POI each scenario carries is now offered.

## Authority

Descriptive throughout. Ranking promotes nothing, creates no signal, and never
invents a zone the detector did not emit. `signal_allowed` remains `False`.

## Limitations

- The ranking weights are reasoned defaults, **not calibrated constants**. No
  human markup has scored them. They encode SMC ordering; they do not claim
  measured accuracy.
- Emitting 11 candidates where 2 were emitted before is a visibility change,
  not an accuracy claim. Whether the ranking picks what a trader would pick is
  unmeasured until the markup cohort exists.
- No perception accuracy, predictive edge, signal, paper, live, or execution
  authority was created.
