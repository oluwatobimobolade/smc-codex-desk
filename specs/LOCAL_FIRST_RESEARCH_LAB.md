# Local-First SMC Research Lab

This workflow turns the current SMC Codex Desk into a local, reproducible
perception and state-machine lab. It does not require an external LLM, vision,
trading, or broker API.

## Authority Rules

- Local Binance USD-M 15m CSVs are the canonical market source.
- Higher timeframes are derived from the canonical 15m files unless a native
  HTF file is being used only for audit.
- Engine output is operational evidence under the current rulebook, not gold
  truth.
- `engine_weak_labels.json` is never importable as gold.
- Gold perception labels require two independent reviewers and an adjudicator.
- Live/paper/autonomous execution remains disabled by default.

## Commands

Verify local market data and write a hash/provenance manifest:

```bash
.venv/bin/python tools/sync_market_data.py --assert-clean
```

Build one operator-facing market-colleague case from local Binance futures
data. This creates clean 15m/1H/4H/1D charts, an annotated 15m engine chart,
sealed engine/MTF JSON, a thesis, and an independent review prompt:

```bash
.venv/bin/python tools/run_market_colleague_case.py \
  --symbol BTCUSDT \
  --decision-time 2026-06-19T23:45:00Z
```

Attach TradingView/WebBridge screenshot evidence when available. The screenshots
are source-alignment evidence, not authority over OHLCV-derived levels:

```bash
.venv/bin/python tools/smc_webbridge_analyst.py \
  --mode capture \
  --instrument BTCUSDT \
  --output-dir journal/$(date -u +%Y-%m-%d)/BTCUSDT/tradingview_check

.venv/bin/python tools/run_market_colleague_case.py \
  --symbol BTCUSDT \
  --tradingview-manifest journal/$(date -u +%Y-%m-%d)/BTCUSDT/tradingview_check/screenshots.json
```

Build the 100-case local blind review lab from existing CSVs:

```bash
.venv/bin/python tools/build_local_case_lab.py \
  --cases-per-symbol 20 \
  --output-root case_library/local_first_lab/$(date -u +%Y%m%d)
```

Replay the setup state machine across the local universe:

```bash
.venv/bin/python tools/replay_setup_universe.py \
  --max-bars 500 \
  --output-dir backtests/state_machine/local_first_$(date -u +%Y%m%d)
```

Build no-API desktop AI review packets from generated cases:

```bash
.venv/bin/python tools/build_desktop_ai_review_packet.py \
  --root case_library/local_first_lab/$(date -u +%Y%m%d) \
  --output-dir backtests/perception/desktop_ai_packets/$(date -u +%Y%m%d)
```

Measure the two-reviewer human baseline after reviewer files are filled:

```bash
.venv/bin/python tools/measure_review_agreement.py \
  --root case_library/local_first_lab/$(date -u +%Y%m%d) \
  --output-dir backtests/perception/reviewer_agreement/$(date -u +%Y%m%d)
```

Export adjudicated training rows after final labels are complete:

```bash
.venv/bin/python tools/export_adjudication_dataset.py \
  --root case_library/local_first_lab/$(date -u +%Y%m%d) \
  --output datasets/perception/adjudicated_cases_$(date -u +%Y%m%d).jsonl
```

## Holdout Guard

The default policy is `configs/holdout_policy.local_first.json`. Tools block
case generation, state replay, backtesting, training, and tuning when their
decision windows overlap a locked holdout period.

Use `--allow-holdout` only for a deliberate final evaluation run, and record
that run separately from exploratory work.

## Case Outputs

Each generated case contains:

- clean raw charts for blind review;
- the exact visible 15m analysis window;
- sealed machine analysis;
- `engine_weak_labels.json` with weak-label provenance;
- reviewer templates;
- `adjudicated.json` for final human resolution;
- adjudicator written justification;
- `case_manifest.json` with hashes and no-future-leakage metadata.

The blind review brief intentionally does not link to machine analysis or weak
labels.

Market-colleague cases are different from gold-candidate review cases. They are
daily desk artifacts for analysis and disagreement capture. Their engine labels
remain operational analysis, not gold truth, and any Execute verdict still
requires human review before risk.
