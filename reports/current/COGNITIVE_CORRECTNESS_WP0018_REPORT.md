# Cognitive Correctness WP-0018 Report

Date: 2026-06-26

## Executive Verdict

The colleague now has a working cognitive correctness layer. It can refuse to
think when market truth is bad, downgrade when regime confidence is weak,
collapse multi-timeframe conflict into one conservative state, score
uncertainty, and write a structured decision memory graph.

## What Changed

- Added a hard market-truth validator.
- Added deterministic regime classification.
- Added MTF contradiction resolution with timeframe hierarchy.
- Added uncertainty scoring and centralized refusal policy.
- Added decision-memory graph records.
- Added observe-only `orchestrator_v2`.
- Added a local CLI: `tools/run_colleague_brain_v2.py`.

## Real BTCUSDT Smoke

Output folder:

`analysis_runs/BTCUSDT_brain_v2_wp0018_smoke/`

Result:

- Truth: `PASS`
- Perception: `completed`
- Regime: `ranging / compression / distribution`
- Regime confidence: `0.7843`
- Contradiction: `INVALIDATE_ALL`
- Final action: `NO_SIGNAL`
- Memory record count: `1`

This is a successful refusal: the system had valid data but blocked the signal
because HTF evidence was contradictory.

## Validation

- `tests/test_cognitive_correctness_layer.py`: `9 passed`
- Focused regression suite: `40 passed`
- Full pytest: `478 passed, 1 skipped`
- Compileall: passed

## Boundary

No strategy edge, paper execution, live execution, or capital-risk authority is
created. WP-0018 is a judgment layer, not a trading strategy.

## Next

The next careful step is to feed V2 brain artifacts into normal
`analysis_runs` packages and rerun live OHLCV route smoke with truth validation
as the first mandatory gate.
