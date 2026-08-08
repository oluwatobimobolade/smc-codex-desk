# SMC AI Perception Interrogation Protocol

**Status:** governing research-certification protocol  
**Version:** 1.0.0  
**Effective:** 2026-07-13

## Purpose

This protocol evaluates whether the SMC Codex Desk can ground, classify, and reconstruct market structure at an exact point-in-time cutoff. It does not equate fluent SMC language, software-test count, or profitable outcomes with perception correctness.

## Research-Scope Correction

RefChartQA is a general chart-question-answering and visual-grounding benchmark, not a candlestick-specific or SMC-perception benchmark. It supports requiring answers to be linked to their supporting chart elements. *Thinking with Visual Grounding* more broadly supports tying intermediate visual reasoning claims to explicit image regions, although it is also not trading-specific. *Look-Ahead-Bench* supports the need for point-in-time evaluation and the detection of look-ahead bias in financial LLM workflows, but it does not by itself validate this system's candle-cutoff or end-to-end causal-integrity implementation.

The unsupported statement that RefChartQA found stronger performance in persistent candlestick trends and weaker performance in ordinary or ambiguous market conditions is excluded from this protocol.

Primary references:

- https://arxiv.org/abs/2503.23131
- https://arxiv.org/abs/2606.16122
- https://arxiv.org/abs/2601.13770
- https://arxiv.org/abs/2303.02601
- https://arxiv.org/abs/2311.08298

## Separate Capability Tracks

1. **OHLCV-native perception:** exact deterministic candle arithmetic, timestamps, levels, lifecycle, and causal graph.
2. **Screenshot/VLM perception:** symbol/timeframe/axis reading, exact image-region grounding, theme/crop/scale robustness, and abstention.
3. **Annotation communication:** immutable market geometry transformed into bounded display geometry without semantic drift.
4. **Predictive/economic evaluation:** future outcomes only after perception labels and POI rankings are frozen.

No track may borrow another track's score.

## Mandatory Object Contract

Every exported object must provide:

- object ID, classification, status, and timeframe;
- source and confirmation anchors;
- exact prices and candle IDs;
- first-knowable candle and decision cutoff;
- observed evidence separated from structural interpretation;
- causal predecessors and consequences;
- competing interpretations and invalidation;
- doctrine assumptions and doctrine hash;
- evidence strength explicitly marked as non-probabilistic;
- calibrated confidence only when a valid certificate exists;
- abstention and missing fields.

## Geometry Contract

Every annotation object has two geometries:

1. `evidence_geometry`: immutable, hash-sealed source anchors and prices.
2. `display_geometry`: reproducibly derived presentation span with an explicit clipping rule.

Display geometry may shorten horizontal span. It may not change price, semantic object, structure scope, source IDs, or confirmation anchor.

## Sweep Lifecycle

The system distinguishes:

```text
penetration
-> penetration/acceptance candidate
-> reclaim candidate
-> accepted breakout
or local rejection without consequence
or confirmed structural sweep
```

Only reclaim followed by an opposing confirmed structural consequence is a certified structural sweep. A wick through liquidity is never sufficient by itself.

## 100/100 Certification

`CERTIFIED_100` requires all of the following simultaneously:

- all ten catastrophic gates pass;
- weighted dimension implementation totals 100;
- at least 30 independently adjudicated point-in-time cases;
- at least 50 adjudicated calibration records;
- expected calibration error at or below 0.10;
- real chart perturbation consistency at or above 0.95;
- no-chart, blank-chart, random-chart, and unreadable-chart abstention pass;
- frozen pre-reaction POI ranking;
- sequential sweep-versus-breakout replay pass;
- no signal, paper, or live authority is inferred from perception certification.

Missing empirical evidence caps the status at `NOT_CERTIFIED`. It is forbidden to round readiness, code coverage, test count, or synthetic performance to 100.

