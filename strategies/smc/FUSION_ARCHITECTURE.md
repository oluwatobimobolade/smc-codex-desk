# Fusion Architecture — Trustworthy SMC Augmentation

This document describes the experimental observability stack that sits **beside** the existing deterministic SMC engine. It does **not** replace the engine, `dual_lens.py`, or the safety model. Its purpose is to add context that helps the system see more clearly and abstain more accurately.

> **Guiding principle:** The fusion layer adds better seeing and better abstention. It does not add alpha. Any piece that makes you more likely to deploy capital on the base signal is a bug.

## Status

This is a **shadow-mode** research layer. It logs its verdicts and reasoning; it does not change the live trade plan. It may graduate to "voting" only after meeting the acceptance gates at the end of this document.

## Design Principles

1. **Engine owns every price.** Entry, stop, target, invalidation, and POI levels all come from the deterministic engine.
2. **Dual-direction hypotheses.** The engine emits both a bullish and a bearish `TradePlan`. Fusion scores the two competing hypotheses rather than overriding a single baseline.
3. **Fusion is observability-only by default.** It records conflicts, overrides, and narratives; it does not originate trades.
4. **Downgrade-only.** The Fusion Engine may lower a verdict (`Execute → Watch → Pass`) and may flag a contested state, but it may **not** promote `Pass`/`Watch` to `Execute`.
5. **No invented prices.** Every price referenced by Fusion must trace to an engine-owned level.
6. **Hard gates are vetoes, not scores.** R:R floor, POI mitigation, news blackout, and counter-Daily-without-exception each force `Pass` and cannot be overridden by confidence.
7. **Falsifiable hypotheses.** Every intent rule and feature detector states its trigger conditions and is unit-tested against synthetic data.

## The Four Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Fusion Engine                                              │
│  - scores bullish/bearish engine plans                      │
│  - downgrade-only; can flag contested                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────┐
│ Engine │  │ Sequence   │  │ Intent     │  │ OHLCV       │
│        │  │ Memory     │  │ Detector   │  │ Features    │
│ owns   │  │ episodes   │  │ calibrated │  │ exact,      │
│ prices │  │ & narrative│  │ modulators │  │ cv2-free    │
│        │  │            │  │            │  │             │
│ emits  │  │            │  │            │  │             │
│ both   │  │            │  │            │  │             │
│ dirs   │  │            │  │            │  │             │
└────────┘  └────────────┘  └────────────┘  └─────────────┘
```

### 1. Engine — now dual-direction (`smc_desk/engine.py`)

The engine still computes all prices, but `analyze_dataframe()` now populates:

- `AnalysisResult.trade_plan` — the primary direction (backward-compatible).
- `AnalysisResult.bullish_plan` — the long thesis with engine-owned levels.
- `AnalysisResult.bearish_plan` — the short thesis with engine-owned levels.

`build_dual_trade_plan()` calls the same direction-agnostic helper twice. There is no duplicated preprocessing; swing, FVG, OB, sweep, and structure detection already run once for both directions.

**Hard gate:** A plan with `risk_reward < floor` now forces `Pass`, regardless of other confluence. This fixes the "R:R 1.5 · Watch" bug.

### 2. Sequence Memory (`smc_desk/sequence_memory.py`)

Converts a stream of closed bars into descriptive market episodes:

- `RALLY`, `DROP`, `CONSOLIDATION`, `TRAP`, `ACCUMULATION`, `DISTRIBUTION`

Each completed episode stores start/end bar, high/low, key events, and a confidence score. The layer emits a human-readable narrative.

**Safety note:** Sequence Memory never creates price levels. It only labels what has already happened. It is tested for no future leakage: episodes that end before bar T are unchanged when future bars arrive.

### 3. OHLCV Features (`smc_desk/features.py`)

OHLCV-derivable pattern detection in pure numpy/pandas:

- **Vertical spike trap** — sudden range expansion + reversal.
- **Failed breakout** — price pierces a recent extreme and closes back inside.
- **Wick/body ratios** — rejection strength.
- **Regime proxies** — adx_proxy, volatility_pct, net_change, regime_label.

Every function accepts a `decision_time` cutoff and refuses to read future bars. This replaces the cv2-based pixel-recovery pipeline for all features that are losslessly computable from the raw data.

### 4. Intent Detector (`smc_desk/intent_detector.py`)

Scores competing hypotheses about market intent. Rules implement the `IntentRule` protocol. Current rules include:

- Sweep reversal trap
- Spike trap (uses OHLCV features)
- Rally-then-trap distribution
- Drop-then-trap accumulation
- Exhaustion
- News-event distortion
- Active trap / chop
- Multiple failed breakouts

**Critical change:** Intent is a **modulator**, not a director. By default it runs in **log-only mode**: it records conflicts and would-have-been score adjustments, but it cannot change the fused verdict. After calibration against a gold set, `allow_intent_modulation=True` can apply learned multipliers.

### 5. Fusion Engine (`smc_desk/fusion_engine.py`)

Reconciles the engine's dual plans with Sequence Memory, Intent Detector, features, and regime context.

Behavior:

- Records engine, intent, and sequence contributions.
- Scores both bullish and bearish plans.
- Applies regime penalties (`chop`, `trend_counter`).
- Records intent modulation as log-only by default.
- Flags `contested` when neither direction wins by a clear margin.
- Downgrades `Execute → Watch` when an active trap episode exists.
- Produces `FusionOverride` records for every change.
- Maps every emitted price to its engine source in `price_sources`.

**Safety note:** Fusion may only downgrade or contextualize. It cannot invent prices or upgrade a verdict.

## Macro Sanity Check: The Dual Lens

The **Dual Lens** (`smc_desk/dual_lens.py`) is an orthogonal "Macro Sanity Check" that runs *after* the Fusion Engine. It compares the final Math Engine trade plan against a `VisionRead` (a qualitative assessment from a Vision AI or human looking at the chart).

Behavior:
- **Reconciliation:** It computes an Agreement Score based on bias, key zones, and structural clarity.
- **Safety Veto:** If the mathematical model wants to `Execute` but the vision model rates the chart as chaotic or disagrees on the direction, the Dual Lens enforces a veto, reducing confidence or forcing a `Pass`.
- **No Heavy Dependencies:** We decoupled the heavy `cv2` image-generation dependencies. The Dual Lens now strictly accepts a standardized `vision_read.json`, which can be supplied by Kimi WebBridge or an offline classifier.

## Market Context

`MarketContext` carries external state that can affect interpretation:

- `minutes_to_next_major_news`
- `is_options_expiry_day`
- `session`
- `regime_label` — from `features.regime_features()`

## Tools

### Replay episodes

`tools/replay_episodes.py` runs the layers over a historical CSV and writes a JSON log:

```bash
.venv/bin/python tools/replay_episodes.py \
  --ohlcv data/sample_ohlcv.csv \
  --symbol EURUSD \
  --output /tmp/replay.json \
  --max-bars 500 \
  --warmup-bars 50
```

### Attach to chart analysis

```bash
.venv/bin/python tools/analyze_chart.py \
  --ohlcv data/sample_ohlcv.csv \
  --symbol EURUSD \
  --timeframe 15m \
  --output-dir outputs \
  --fusion
```

This writes `analysis.json` with a `fusion_observability` section and a human-readable `fusion.md` report.

### Attach Vision Read (Dual Lens)

If you have a qualitative assessment of the chart (e.g., from an LLM), provide it to the analyzer to run the Dual Lens:

```bash
.venv/bin/python tools/analyze_chart.py \
  --ohlcv data/sample_ohlcv.csv \
  --symbol EURUSD \
  --timeframe 15m \
  --fusion \
  --vision data/sample_vision_read.json
```

This will additionally generate a `reconciliation.json` and a `reconciliation.md` report.

## Integration Contract

When wiring the Fusion Engine into the live pipeline:

1. Run the deterministic engine first and obtain its `AnalysisResult` with both `bullish_plan` and `bearish_plan`.
2. Run Sequence Memory over the same closed bars.
3. Compute OHLCV features and regime context from bars ≤ decision time.
4. Run Intent Detector with memory, features, and `MarketContext`.
5. Call `FusionEngine.fuse(engine_result, sequence_memory, intent_result, visual_patterns=features, context=context)`.
6. Use the returned `FusionResult` only for logging and research. Do not let it change the live trade plan until the acceptance gates are met.
7. Log every `FusionOverride` for review.

## Acceptance Gates (GO/NO-GO)

Fusion may graduate from shadow mode to voting only when all three hold on a blind adversarial gold set:

1. **Direction accuracy ≥ 85%** (including "no_trade").
2. **Brier score ≤ 0.25** on confidence predictions.
3. **Zero hard-gate violations** in the regression suite.

Until all three hold, it is not A+ no matter how persuasive the prose reads.

## Future Work

- Calibrate intent rule weights against adjudicated gold cases.
- Add more intent rules (order-block failure, stop-run cascade).
- Wire Fusion Engine into `tools/backtest_smc_elite.py` as an optional observability flag.
- Build a perception benchmark that compares Fusion Engine overrides against adjudicated labels.
- Migrate Sequence Memory to consume state-machine transitions for a single temporal source of truth.

## References

- `smc_desk/engine.py`
- `smc_desk/features.py`
- `smc_desk/sequence_memory.py`
- `smc_desk/intent_detector.py`
- `smc_desk/fusion_engine.py`
- `smc_desk/regime.py`
- `tools/replay_episodes.py`
- `tools/analyze_chart.py`
- `tests/test_engine_dual_direction.py`
- `tests/test_engine_hard_gates.py`
- `tests/test_features.py`
- `tests/test_fusion_leakage.py`
- `tests/test_fusion_golden.py`
- `tests/test_fusion_price_provenance.py`
- `tests/test_fusion_engine.py`
- `tests/test_intent_detector.py`
- `tests/test_sequence_memory.py`
- `tests/test_replay_episodes.py`
- `tests/test_analyze_chart.py`
