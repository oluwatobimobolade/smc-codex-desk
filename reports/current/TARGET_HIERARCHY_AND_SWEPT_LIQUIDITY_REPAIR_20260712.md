# Target Hierarchy and Swept-Liquidity Repair

## Diagnosis

The XRPUSDT entry review exposed a target-classification error. The system
could validate the nearest local liquidity pool as if it were full model
completion. It did not deterministically distinguish:

- internal liquidity used for partial management;
- external liquidity at the controlling dealing-range extreme; and
- liquidity already recorded as swept.

The sweep validator also read a top-level `price` field but ignored the real
detector fields nested under `evidence.swept_level_id` and
`evidence.swept_price`.

## Repair

- Prompt order now requires internal-versus-external target classification.
- Internal liquidity may be disclosed as partial management but cannot replace
  the controlling active-range external extreme as model completion.
- Every completion target must map to its declared liquidity id.
- Detector sweep evidence now invalidates already-taken target ids and prices.
- Missing completion targets block execution readiness without falsely
  declaring the underlying SMC structure invalid.

## XRPUSDT Correction

- `1.0886-1.0892`: local/internal sell-side liquidity and partial-management
  reaction risk.
- `1.0827`: secondary management/reaction level.
- `1.0678`: controlling 4H external range low and bearish model-completion
  target, if the bearish continuation setup becomes valid.
- Preferred deeper entry POI: 1H supply `1.1057-1.1125`, refined at
  `1.1082-1.1102`; this remains confirmation-only and not currently triggered.

## Validation

- New regression tests cover internal-liquidity mispromotion and swept target
  rejection.
- Focused target suite: 60 passed.
- Final full suite: 946 passed, 1 skipped in 127.52 seconds.
- `compileall` and `git diff --check`: PASS.

No signal or execution authority was enabled.
