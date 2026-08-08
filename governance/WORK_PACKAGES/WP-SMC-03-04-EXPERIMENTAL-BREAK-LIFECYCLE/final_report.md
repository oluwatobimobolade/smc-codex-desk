# WP-SMC-03/04 Final Report

## Objective

Capture the first verified canonical structure defects and implement their
correct semantics in an isolated experimental path.

## Implemented

- Public `HybridPerceptionEngineV3Experimental` facade with explicit
  non-authority contract and no implicit AI provider.
- Deterministic break lifecycle under a decision-time cutoff.
- Wick-only probe classification.
- Body close as candidate rather than immediate final authority.
- External displacement and normalized-penetration gates.
- Two/six-bar follow-through or retest horizon.
- `INITIAL_DIRECTION_BREAK` for the first accepted break.
- Internal CHoCH and external MSS candidate/confirmed separation.
- Future-data invariance.

## Not Implemented Yet

- Automatic conversion of the full candidate atlas into certified break-level
  interactions.
- Causal protected-point/range V2 integration into the new lifecycle.
- Full sweep/breakout symmetry and level-salience decay.
- Blind human-gold accuracy, empirical threshold calibration, or promotion.

## Validation

Focused gate: 21 passed. Full repository: 981 passed, 1 skipped. Compile,
diff, authority-boundary, and governance checks passed.

Next gate: WP-SMC-05, connecting accepted experimental breaks to causal
protected-point and versioned active-range state without changing canonical V2.
