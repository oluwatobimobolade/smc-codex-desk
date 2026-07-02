# WP-0031 Intraday Doctrine Audit

Timestamp: 2026-06-29T10:04:41Z

## Scope

Audited the current dirty worktree after the newest updates around:

- intraday SMC doctrine profile;
- setup classification, target selection, hybrid stops, entry style, RR validation, and rejection logic;
- narrative authority v2 wiring;
- clean SMC chart rendering and thesis v7;
- recent perception/evaluation/runtime-config/regime/live-data changes.

This audit did not revert any existing user or parallel-AI work.

## What Looked Correct

- The new WP-0031 tests are coherent and directly encode the intended doctrine:
  - 15m is the default execution timeframe.
  - 5m is optional.
  - 1m is forbidden.
  - minimum RR is 3.0.
  - leverage, fixed risk, and position sizing remain disabled.
  - 15m entries do not blindly force the first target.
  - target selection is setup-dependent.
  - stops are structural first, volatility-buffered second.
  - trade boxes are blocked unless the narrative authority says the trade plan is ready.
- The engine/rules direction is mostly right:
  - runtime config split is present;
  - perception and strategy configs are separated;
  - min POI width math in `engine.py` was corrected from mixed percent/bps math to bps math.
- The live OHLCV retry/backoff change is useful and aligned with the reliability direction.
- Evaluation work moved in the correct direction:
  - less placeholder/random scoring;
  - more real matching, consensus, precision/recall/F1;
  - no fake high accuracy claim from empty or insufficient evidence.
- Vision prompt changes are useful:
  - the prompt now warns not to invent exact decimal prices;
  - the prompt includes injection resistance language.
- Optional provider registration is acceptable only as non-authoritative infrastructure. It must not become part of the official local-first/no-API truth path unless explicitly approved later.

## Issue Found And Fixed

### Candle gap detection regression

`smc_desk/colleague/run_context.py` had been changed so timestamp gaps were no longer marked:

```python
if open_time != expected_open:
    pass
```

That caused `tests/test_truth_boundary.py::CandleQualityTests::test_gap_detected_when_timestamps_skip` to fail.

This was a real safety/correctness bug because Binance futures crypto data should not silently accept missing 15m candles as clean data.

Fixed behavior:

```python
if open_time != expected_open:
    has_gap = True
```

Future traditional-market session gaps should be handled by an explicit venue/session calendar, not by globally disabling gap detection.

## Cleanliness Fixes

Removed trailing whitespace / EOF blank-line issues from:

- `smc_desk/evaluation/human_challenge.py`
- `smc_desk/regime.py`
- `smc_desk/vision/provider_registry.py`
- `tools/build_research_dataset.py`
- `tools/train_ml_model.py`

## Validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_truth_boundary.py -q
.venv/bin/python -m pytest tests/test_wp0031_doctrine_profile.py tests/test_wp0031_setup_and_targets.py tests/test_wp0031_stop_and_rejection.py tests/test_wp0031_trade_rejections.py tests/test_wp0031_narrative_and_charts.py -q
git diff --check
.venv/bin/python -m pytest -q
```

Results:

- Truth boundary: 10 passed.
- WP-0031 doctrine suite: 29 passed.
- Diff check: clean.
- Full suite: 591 passed, 1 skipped.

## Remaining Cautions

- The repo still has a very large dirty worktree with many untracked new modules, tests, configs, datasets, and governance files. The suite is green, but this is not the same thing as reviewed/accepted product quality for every new file.
- `specs/ONTOLOGY_V2.yaml` is deleted while `specs/PERCEPTION_ONTOLOGY_V2.yaml` exists. That may be intentional, but the rename/deprecation should stay documented in governance.
- Any optional external vision provider must remain non-authoritative during the current no-API/local-first phase.
- Passing tests prove consistency and regressions for current contracts; they do not prove trading edge, profitability, or live execution readiness.

## Verdict

The newest updates are directionally strong and now test-clean after the gap-detection repair.

The system is healthier than before this audit: the intraday doctrine is codified, official trade gating is covered, chart/thesis tests exist, and the previous truth-boundary regression is fixed.

The correct next work is not more live signals. The next work is to finish hardening acceptance around the large new untracked surfaces, then run deterministic replay/event-store validation before any stronger trading claims.
