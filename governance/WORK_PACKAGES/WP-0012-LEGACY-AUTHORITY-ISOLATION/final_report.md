# WP-0012 Legacy Authority Isolation - Final Report

Date: 2026-06-26

## Objective

Remove the legacy SMC engine from current Market Colleague decision authority while
preserving it as optional comparison evidence.

## What Changed

- `scenarios/decision.json` is now derived from `PerceptionEngineV2` plus MTF
  context, not from `legacy_comparison/engine_analysis.json`.
- `scenarios/scenario_tree.json` no longer consumes the legacy trade plan for
  action state, targets, invalidation, or next action.
- `perception/mtf_state_graph.json` always contains a current decision node with
  `legacy_trade_plan_used=false`.
- `include_legacy_comparison=false` now skips the legacy engine completely and
  still builds a complete colleague package.
- `tools/run_market_colleague_case.py` now exposes `--no-legacy-comparison`.
- Thesis/report text now correctly reports legacy comparison as `disabled` when
  it is not run.

## Real Smoke Evidence

Run:

```bash
.venv/bin/python tools/run_market_colleague_case.py \
  --symbol BTCUSDT \
  --decision-time 2026-06-19T23:45:00Z \
  --output-dir analysis_runs/BTCUSDT_20260619_2345_wp0012_no_legacy_smoke \
  --no-legacy-comparison \
  --holdout-policy configs/holdout_policy.local_first.json
```

Result:

- Package: `analysis_runs/BTCUSDT_20260619_2345_wp0012_no_legacy_smoke/`
- Decision candle open: `2026-06-19T23:30:00`
- Decision available at: `2026-06-19T23:45:00`
- Action: `NO_SETUP`
- Legacy role: `disabled`
- Capital risk: `0`
- `legacy_trade_plan_used`: `false`

## Authority Result

Legacy engine is now:

- optional;
- sealed under `legacy_comparison/` when enabled;
- not run when `--no-legacy-comparison` is used;
- not passed into the current decision/scenario builders.

## Non-Goals

- No strategy edge was claimed.
- No paper/live execution was enabled.
- No legacy comparison code was deleted.
- No PEV2 object was promoted to gold truth.

## Next Gate

WP-0013 should build a resolved-case cohort across BTCUSDT, ETHUSDT, SOLUSDT,
XRPUSDT, and BNBUSDT so the colleague can learn from outcomes without claiming
edge prematurely.
