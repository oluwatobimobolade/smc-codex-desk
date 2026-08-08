# Local-First Research Lab Implementation Report

Generated: 2026-06-25

## Executive Summary

The local-first SMC roadmap has been implemented as a reproducible research
and perception laboratory. The system now has explicit data provenance,
holdout protection, blind case generation, weak-label separation, adjudication
clustering, and state-machine replay outputs.

The most important achievement is epistemic safety: engine output is no longer
easy to confuse with gold truth. Machine objects are preserved as weak
operational labels, while subjective SMC truth still requires independent
review and adjudication.

## What Was Built

### 1. Local Data Foundation

Added `tools/sync_market_data.py`.

It verifies the local Binance USD-M futures OHLCV universe, writes quality
summaries, records SHA-256 hashes, and documents the canonical data contract:

- 15m CSVs are the canonical market source.
- 1h, 4h, and 1d files are derived from the canonical 15m feed unless doing a
  native-HTF audit.
- External refresh is opt-in only via `--refresh`; default mode is local-only.

### 2. Holdout Protection

Added:

- `smc_desk/evaluation/holdout_guard.py`
- `configs/holdout_policy.local_first.json`

The default protected window starts at `2026-07-01T00:00:00Z`, because June
2026 live/research data has already been touched. The guard blocks case
generation, state replay, backtesting, training, tuning, and prediction
training when they overlap a locked holdout unless the caller explicitly uses
`--allow-holdout` for final evaluation.

### 3. Local Chart and Case Lab

Updated `tools/build_perception_gold_batch.py` and added
`tools/build_local_case_lab.py`.

Each generated case now contains:

- clean raw charts for blind review;
- exact visible 15m analysis window;
- sealed machine analysis;
- `engine_weak_labels.json`;
- `case_manifest.json`;
- reviewer templates;
- adjudicator template.

The blind review brief intentionally does not link to machine analysis or weak
labels. Engine labels are marked as `weak_operational_labels_only`, not gold
truth.

### 4. Adjudication Loop

Replaced the placeholder implementation in `smc_desk/evaluation/adjudication.py`.

The new adjudication logic clusters reviewer objects by primitive, direction,
time, and price/zone overlap. It separates:

- agreed objects: at least two independent reviewers identify the same object;
- disputed objects: objects seen by only one reviewer or not matched.

This makes reviewer consensus measurable instead of assumed.

### 5. State-Machine Research

Updated `tools/replay_setup_states.py` and added
`tools/replay_setup_universe.py`.

State replay now emits:

- `state_machine_replay.json`;
- `state_observations.csv`;
- `state_transitions.csv`;
- holdout-window provenance;
- event-store schema metadata.

The universe wrapper replays BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, and BNBUSDT
through the same observability-only state machine.

### 6. Backtest Guardrails

Updated:

- `tools/backtest_smc_elite.py`
- `tools/backtest_smc_elite_mtf.py`

Both backtest paths now check the holdout policy before running. If a backtest
touches a locked window, it fails unless explicitly marked as final evaluation
with `--allow-holdout`.

### 7. Operator Documentation

Added `specs/LOCAL_FIRST_RESEARCH_LAB.md`.

This documents the authority rules, key commands, holdout policy, and case
output contract.

## What We Achieved

- The system can now be run as a local research lab without external model,
  vision, trading, or broker APIs.
- Data quality and provenance are manifestable with hashes.
- The local case lab can generate clean blind-review cases from existing CSVs.
- Machine labels are preserved for later scoring but cannot be mistaken for
  human/adjudicated truth.
- Adjudication now produces real agreement/disagreement outputs.
- State-machine replay can produce an event store across the symbol universe.
- Backtests and replay tools now respect locked holdout boundaries.
- The project’s “no false confidence” rule is now enforced in code, not only
  in documentation.

## Validation Performed

### Automated Checks

```bash
.venv/bin/python -m compileall -q smc_desk tools tests
```

Result: passed.

```bash
.venv/bin/python -m pytest -q
```

Result: `339 passed in 40.40s`.

### Whitespace / Patch Hygiene

```bash
git diff --check -- <local-first implementation files>
```

Result: passed.

Global `git diff --check` still reports trailing whitespace in older dirty
files outside this implementation surface:

- `smc_desk/evaluation/human_challenge.py`
- `smc_desk/perception/engine_v2.py`
- `smc_desk/perception/lifecycle.py`
- `smc_desk/perception/swings.py`
- `smc_desk/vision/provider_registry.py`

Those were not silently edited because they are pre-existing dirty worktree
changes outside this pass.

### Operational Smoke Checks

Local data manifest:

```bash
.venv/bin/python tools/sync_market_data.py \
  --symbols BTCUSDT \
  --intervals 15m \
  --derive-htf off \
  --output /tmp/smc_data_manifest_recheck.json \
  --quality-md /tmp/smc_quality_recheck.md \
  --quality-json /tmp/smc_quality_recheck.json \
  --assert-clean
```

Result: `PASS`.

Local case lab:

```bash
.venv/bin/python tools/build_local_case_lab.py \
  --symbols BTCUSDT \
  --cases-per-symbol 1 \
  --chart-bars 80 \
  --output-root /tmp/smc_local_case_lab_recheck
```

Result: one blind local-first case generated with weak-label provenance.

Universe state replay:

```bash
.venv/bin/python tools/replay_setup_universe.py \
  --symbols BTCUSDT ETHUSDT \
  --max-bars 5 \
  --output-dir /tmp/smc_state_universe_recheck
```

Result: replay outputs written successfully.

## Current Limitations

- This does not prove market edge or profitability. It proves the local lab,
  guardrails, and replay instrumentation work.
- The 100-case lab was not generated into the repo during implementation to
  avoid dumping large artifacts automatically.
- The adjudication layer clusters reviewer objects; it does not replace the
  final human adjudicator.
- The state machine remains observability-only. It does not authorize live,
  paper, or automated execution.
- Global whitespace warnings remain in unrelated pre-existing dirty files.

## Recommended Next Step

Build the actual 100-case local lab when ready:

```bash
.venv/bin/python tools/build_local_case_lab.py \
  --cases-per-symbol 20 \
  --output-root case_library/local_first_lab/$(date -u +%Y%m%d)
```

Then begin reviewer/adjudicator labeling. Only after adjudicated cases exist
should perception accuracy or rule performance be claimed.
