# smc-codex-desk

`smc-codex-desk` is a local Smart Money Concepts analysis workstation for Codex.

It is designed as an analyst stack, not a trading bot:

1. Intake
Accept chart screenshots, OHLCV CSV files, or both.

2. Analysis
Apply deterministic heuristics for swings, liquidity, BOS, CHoCH, FVGs, order blocks, dealing range, premium/discount, and trade planning.

3. Output
Produce JSON, Markdown, and annotated PNG artifacts that can be stored in a journal or dashboard.

## What This Does Well

- Builds a clean local repo Codex can extend
- Produces consistent structured outputs
- Creates annotated charts from OHLCV data
- Compares your bias against the model plan
- Downloads public Binance USD-M futures OHLCV data for replay testing
- Runs a no-lookahead SMC replay backtest with near-miss diagnostics
- Separates swing/external structure from internal entry structure so local CHoCH cannot flip HTF bias
- Gives you a rulebook and prompt pack to keep the workflow disciplined

## What This Does Not Guarantee

- It does not guarantee profitable trades
- It does not guarantee performance better than discretionary professionals
- It does not auto-execute orders
- Screenshot-only mode is a review canvas unless you also provide OHLCV data or manual notes

## Elite Quality Gates

The deterministic engine is intentionally conservative. A setup cannot be marked `Execute` unless the checklist is complete:

- Directional bias is defined
- Bias comes from swing/external structure; internal CHoCH is entry confirmation only
- A fresh POI exists by default (`require_fresh_poi=true`; partial POIs are research opt-in)
- POI aligns with premium/discount
- Liquidity is swept before the break
- BOS/CHoCH has candle-body displacement
- Price is at or near the POI
- Logical target gives at least `1:3` R:R

Anything missing becomes `Watch` or `Pass` with `0%` risk. This is by design. The system should prevent low-quality trades more often than it produces trade ideas.

If you want serious performance, the priority order is:

1. Encode your own BOS, CHoCH, OB, FVG, and liquidity rules
2. Validate on historical data
3. Review false positives and false negatives
4. Tighten the rules before adding live capture

## Quick Start

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Generate sample market data:

```bash
python3 tools/generate_sample_ohlcv.py --output sample_ohlcv.csv
```

Run analysis:

```bash
python3 tools/analyze_chart.py \
  --ohlcv sample_ohlcv.csv \
  --symbol XAUUSD \
  --timeframe 15m \
  --bias bearish \
  --notes "Watching for sell-side sweep into bearish FVG." \
  --output-dir outputs
```

Compare your own bias versus the model:

```bash
python3 tools/compare_my_bias_vs_model.py \
  --analysis outputs/analysis.json \
  --ohlcv sample_ohlcv.csv \
  --user-direction bearish \
  --user-entry 2320.5 \
  --user-stop 2324.2 \
  --user-target 2312.0 \
  --output-dir outputs
```

## Repo Layout

- `prompts/`: Codex-ready prompts for building, running, and extending the workstation
- `strategies/smc/`: the house rulebook template, rule config, and the **SMC Elite Strategy**
- `smc_desk/`: reusable Python package for parsing data, running analysis, and rendering outputs
- `tools/`: CLI entrypoints, including the WebBridge screenshot capture tool
- `outputs/`: generated JSON, Markdown, and PNG artifacts that can be stored in a journal or dashboard
- `journal/`: saved SMC Elite analyses, screenshots, and outcome tracking
- `.opencode/skills/smc-elite-analyst/`: opencode skill for persistent chart analysis
- `smc_elite_prompt.md`: quick prompt for instant analysis
- `mcp/`: placeholder for future browser or broker integrations

## Input Format

OHLCV CSV files should include:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume` is optional

Timestamps should be ISO 8601 or any pandas-readable datetime format.

## Output Files

The default output set is:

- `outputs/analysis.json`
- `outputs/annotated_chart.png`
- `outputs/trade_plan.md`
- `outputs/bias_comparison.md`
- `outputs/bias_comparison.png`

If you provide screenshot input, the tool also writes:

- `outputs/screenshot_review.png`

## SMC Elite System

A complete, high-confluence SMC workflow has been added to this repo:

- **Playbook:** `strategies/smc/SMC_ELITE_STRATEGY.md`
- **Structure doctrine:** `strategies/smc/STRUCTURE_DOCTRINE.md`
- **Consensus research:** `strategies/smc/CONSENSUS_SMC_RESEARCH.md`
- **Backtesting playbook:** `strategies/smc/BACKTESTING_PLAYBOOK.md`
- **Visual accuracy spec:** `strategies/smc/VISUAL_ACCURACY_SPEC.md`
- **Skill:** `.opencode/skills/smc-elite-analyst/SKILL.md`
- **Quick prompt:** `smc_elite_prompt.md`
- **Journal:** `journal/`
- **WebBridge capture tool:** `tools/smc_webbridge_analyst.py`

### Fusion Architecture (experimental observability layers)

A new four-layer observability stack sits beside the deterministic engine. It adds narrative, visual, and intent context without replacing the engine or `dual_lens.py`:

- **Sequence Memory** — converts bars into episodes (rally, drop, consolidation, trap, accumulation, distribution) and emits a narrative.
- **Visual Cortex** — detects vertical-spike traps and failed breakouts from rendered OHLCV charts.
- **Intent Detector** — scores market-intent hypotheses (bull trap, distribution, exhaustion, etc.).
- **Fusion Engine** — reconciles engine verdict/bias with the layers; downgrade-only, with explicit override records.

See `strategies/smc/FUSION_ARCHITECTURE.md` for the full contract.

Replay a CSV through the layers:

```bash
python3 tools/replay_episodes.py \
  --ohlcv data/sample_ohlcv.csv \
  --symbol EURUSD \
  --output /tmp/replay.json \
  --max-bars 500 \
  --warmup-bars 50
```

### Downloading Binance futures data for backtesting

```bash
python3 tools/download_binance_futures_ohlcv.py \
  --symbol BTCUSDT \
  --interval 15m \
  --start 2026-06-01 \
  --end 2026-06-18 \
  --output data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_20260601_20260618.csv
```

Pull the default perp universe (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `BNBUSDT`) across `15m`, `1h`, `4h`, and `1d`:

```bash
bash tools/pull_binance_futures_universe.sh
```

Run the full 15m research/training loop for one pair:

```bash
bash tools/train_pair.sh BTCUSDT
```

Run it for the whole default futures universe:

```bash
bash tools/train_binance_futures_universe.sh
```

### Running a replay backtest

```bash
python3 tools/backtest_smc_elite.py \
  --ohlcv data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_20260601_20260618.csv \
  --symbol BTCUSDT \
  --timeframe 15m \
  --output-dir backtests/2026-06-18/BTCUSDT_15m_smoke \
  --warmup-bars 250 \
  --entry-wait-bars 24 \
  --max-hold-bars 96
```

### Capturing exchange-matched chart screenshots for analysis

```bash
python3 tools/smc_webbridge_analyst.py --instrument BTCUSDT
```

This opens TradingView (free), switches through **Daily → 4H → 1H → 15m**, and saves screenshots to `journal/YYYY-MM-DD/<INSTRUMENT>/`.
For Binance futures symbols, the tool defaults to TradingView perpetual charts like `BINANCE:BTCUSDT.P` so screenshots line up with Binance USD-M futures OHLCV. Legacy spot symbols `BTCUSD` and `ETHUSD` still default to Bitstamp; for other markets, pass the TradingView source explicitly, for example `--instrument OANDA:EURUSD` or `--instrument XAUUSD --exchange OANDA`.

### Building a reusable SMC case

Every serious example should become a case folder with:

- 15m OHLCV source path and SHA-256 hash
- data quality checks
- no-future-leakage MTF snapshot
- machine analysis and checklist
- TradingView screenshot references
- blank expert-label template

```bash
python3 tools/build_smc_case.py \
  --symbol BTCUSDT \
  --exchange BINANCE \
  --ohlcv data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv \
  --screenshots-meta journal/2026-06-18/BTCUSDT/screenshots.json \
  --output-dir case_library/BTCUSDT/current_live_case
```

Do not promote a rule from raw backtest output alone. Promote only after the case library has enough visually reviewed wins, losses, missed entries, and pass/no-trade examples.

Audit the case library after adding cases:

```bash
python3 tools/audit_case_library.py --root case_library --print-summary
```

This writes `case_library/index.md` and `case_library/index.json`, showing which cases are source-aligned, which remain unreviewed, and which are eligible for machine research versus expert training.

### Generating a TradingView overlay

To keep models from inventing visual levels, generate a Pine Script overlay from the deterministic case data:

```bash
python3 tools/generate_tradingview_overlay.py \
  --case case_library/BTCUSDT/current_live_case/case.json \
  --print-summary
```

This writes `tradingview_overlay.pine` beside the case. Paste it into TradingView Pine Editor and add it to the chart to draw the exact SMC Desk zones, POI, execution SL, structural invalidation, targets, and structure labels. Public TradingView pages do not expose the Charting Library Drawings API directly, so Pine overlay is the repeatable path; browser-click drawing is a brittle fallback.

### Running dual-lens live analysis

The dual-lens workflow keeps the deterministic engine in charge of every price while a chart-vision read acts as a second opinion:

```bash
python3 tools/analyze_live_dual_lens.py \
  --symbol BTCUSDT \
  --provider binance_futures \
  --days 20
```

Then reconcile a vision read against the engine output:

```bash
python3 tools/reconcile_dual_lens.py \
  --case case_library/BTCUSDT/<case>/engine_analysis.json \
  --vision case_library/BTCUSDT/<case>/vision_read.json
```

Rules: closed candles only, same-source data preferred, engine owns entry/stop/targets, vision can confirm or veto but cannot invent tradeable levels. Stops separate raw structural invalidation from execution SL; risk/reward uses the execution SL after the ATR volatility buffer.

### Running an SMC Elite analysis

With the skill registered in opencode, simply say:

> "Analyze XAUUSD with SMC Elite."

Or paste the contents of `smc_elite_prompt.md` and name the instrument.

## Next Steps

The highest-value upgrades are:

1. Replace remaining generic heuristics with your exact house rules
2. Add your journal and example charts as retrieval context
3. Run broader train/holdout backtests across BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, FX majors, and metals
4. Add a browser/Pine Script overlay layer for trusted chart visualization
