# Fusion Architecture — Autonomous SMC Layers

This document describes the four-layer observability stack that sits **beside** the existing deterministic SMC engine. It does **not** replace the engine, `dual_lens.py`, or the safety model. It adds narrative, visual, and intent context that can be used to downgrade or challenge an engine recommendation, never to upgrade it.

## Design Principles

1. **Engine owns prices.** The deterministic engine continues to calculate entry, stop, target, invalidation, and POI levels.
2. **Fusion is observability-only by default.** It records conflicts, overrides, and narratives; it does not originate trades.
3. **Downgrade-only.** The Fusion Engine may lower a verdict (`Execute → Watch → Pass`) and may change bias, but it may **not** promote `Pass`/`Watch` to `Execute`.
4. **No invented prices.** None of the new layers generate entry, stop, or target prices.
5. **Falsifiable hypotheses.** Every intent rule and visual detector states its trigger conditions explicitly and is unit-tested against synthetic data.

## The Four Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Fusion Engine                                              │
│  - reconciles engine verdict with narrative/intent/visual   │
│  - downgrade-only overrides                                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────┐
│ Engine │  │ Sequence   │  │ Intent     │  │ Visual      │
│        │  │ Memory     │  │ Detector   │  │ Cortex      │
│ owns   │  │ episodes   │  │ what is    │  │ vertical    │
│ prices │  │ & narrative│  │ market     │  │ spikes,     │
│        │  │            │  │ trying to  │  │ failed      │
│        │  │            │  │ do?        │  │ breakouts   │
└────────┘  └────────────┘  └────────────┘  └─────────────┘
```

### 1. Sequence Memory (`smc_desk/sequence_memory.py`)

Converts a stream of closed bars into discrete market episodes:

- `RALLY` — sustained upward displacement
- `DROP` — sustained downward displacement
- `CONSOLIDATION` — range-bound action
- `TRAP` — a spike that reverses and invalidates the prior move
- `ACCUMULATION` / `DISTRIBUTION` — inferred from episode context (observability only)

Each completed episode stores start/end bar, high/low, key events, parent/child relationships, and a confidence score. The layer also emits a short human-readable narrative of the last few episodes.

**Safety note:** Sequence Memory never creates price levels. It only labels what has already happened.

### 2. Visual Cortex (`smc_desk/visual_cortex.py`)

Provides computer-vision-style analysis of rendered OHLCV charts. Because the input is synthetic/rendered, the detectors are deterministic and independent of broker chart scaling.

Current detectors:

- **Vertical spike trap** — a tall wick that reverses, suggesting liquidity grab.
- **Failed breakout** — price pushes past a recent extreme and closes back inside the range.

The layer exposes `render_chart_for_visual_cortex()` so callers can produce the exact image the detectors see, making every detection reproducible.

**Safety note:** Visual Cortex returns patterns and confidence scores. It does not calculate entry/stop/target prices.

### 3. Intent Detector (`smc_desk/intent_detector.py`)

Scores competing hypotheses about market intent. Rules are small, composable plugins implementing the `IntentRule` protocol. Current rules include:

- Sweep reversal trap
- Spike trap (uses Visual Cortex patterns)
- Rally-then-trap distribution
- Drop-then-trap accumulation
- Exhaustion
- News-event distortion
- Active trap / chop
- Multiple failed breakouts

The detector aggregates rule scores into a normalized distribution and returns a primary intent with reasoning.

**Safety note:** Intent is probabilistic context, not a trade signal.

### 4. Fusion Engine (`smc_desk/fusion_engine.py`)

Reconciles the deterministic engine recommendation with Sequence Memory, Intent Detector, and Visual Cortex.

Behavior:

- Records each layer as a `FusionContribution`.
- If a high-confidence intent conflicts with engine bias (e.g., `BULL_TRAP` vs. `bullish`), it may override the bias and downgrade the verdict.
- If the active sequence episode is a trap/chop, it downgrades `Execute` to `Watch`.
- Every change produces a `FusionOverride` with source, field, old/new values, and reason.
- Confidence is penalized when layers conflict.

**Safety note:** Fusion Engine accepts the engine's `AnalysisResult` (which owns all prices) and may only downgrade the verdict or bias. It cannot create new price levels or upgrade a verdict.

## Replay Tool

`tools/replay_episodes.py` replays a closed-candle OHLCV CSV through the four layers and writes a JSON log:

- episode transitions
- visual pattern detections
- intent samples
- fusion overrides and final recommendations

Example:

```bash
.venv/bin/python tools/replay_episodes.py \
  --ohlcv data/sample_ohlcv.csv \
  --symbol EURUSD \
  --output /tmp/replay.json \
  --max-bars 500 \
  --warmup-bars 50
```

This is useful for auditing how the layers evolve over a historical window without generating trades.

You can also attach the Fusion Engine to a normal chart analysis:

```bash
.venv/bin/python tools/analyze_chart.py \
  --ohlcv data/sample_ohlcv.csv \
  --symbol EURUSD \
  --timeframe 15m \
  --output-dir outputs \
  --fusion
```

This writes `analysis.json` with a `fusion_observability` section and a human-readable `fusion.md` report.

## Integration Contract

When wiring the Fusion Engine into the live pipeline:

1. Run the deterministic engine first and obtain its `AnalysisResult`.
2. Run Sequence Memory over the same closed bars.
3. (Optional) run Visual Cortex on the rendered chart window.
4. Run Intent Detector with the current memory, patterns, and any `MarketContext` (news, session, options expiry).
5. Call `FusionEngine.fuse(engine_result, sequence_memory, intent_result, visual_patterns)`.
6. Use the returned `FusionResult.recommended_verdict` / `recommended_bias` only if they are **downgrades** from the engine verdict/bias.
7. Log every `FusionOverride` for review.

## Future Work

- Calibrate Visual Cortex thresholds on real annotated screenshots.
- Add more intent rules (e.g., order-block failure, stop-run cascade).
- Wire Fusion Engine into `tools/backtest_smc_elite.py` as an optional observability flag.
- Add a perception benchmark that compares Fusion Engine overrides against adjudicated labels.

## References

- `smc_desk/sequence_memory.py`
- `smc_desk/visual_cortex.py`
- `smc_desk/intent_detector.py`
- `smc_desk/fusion_engine.py`
- `tools/replay_episodes.py`
- `tools/analyze_chart.py`
- `tests/test_sequence_memory.py`
- `tests/test_visual_cortex.py`
- `tests/test_intent_detector.py`
- `tests/test_fusion_engine.py`
- `tests/test_replay_episodes.py`
- `tests/test_analyze_chart.py`
