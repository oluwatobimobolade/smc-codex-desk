# SMC AI Perception Interrogation Self-Audit

**Audit date:** 2026-07-13  
**Repository:** `/Users/tobimobolade/smc-codex-desk`  
**Framework:** `SMC AI Perception Interrogation Framework` supplied by the user  
**Audit stance:** adversarial, evidence-bound, no accuracy inference from unit-test count

## Executive Verdict

**Overall framework verdict: FAIL (research certification not yet earned).**

The system is a serious, unusually disciplined research platform. It has strong deterministic OHLCV handling, completed-candle cutoffs, a close-based break lifecycle, parent/child guards, causal POI lineage, abstention states, sparse rendering, and execution disabled by contract.

It is **not yet proven to perceive SMC structure like a skilled trader**. The decisive reasons are:

1. There are **zero eligible adjudicated perception cases**. Precision, recall, F1, calibration, and expert agreement are unavailable.
2. Several suites named `vision`, `adversarial`, `crop`, or `rendering stress` use mocks, inspect prompt text, or only import modules. They prove plumbing, not chart perception.
3. The current annotation composer shortens long structure marks by changing the coordinates stored in the drawing object. Source anchors exist elsewhere, but immutable evidence geometry and display geometry are not separated. This fails catastrophic gate 6.
4. Numeric confidence values are mostly rule-based scores, not empirically calibrated probabilities. This fails certification under catastrophic gate 9.
5. POI ranking has not been evaluated on a frozen pre-return cohort; sweep/breakout classification has not been measured through a real sequential confusion matrix.
6. Deterministic bitmap QA proves that an image is populated, not that BOS, CHoCH, POI, liquidity, or labels are semantically correct.

The weighted implementation/readiness score is **45.1/100**. This is **not perception accuracy**. Because catastrophic gates override aggregate scoring, 45.1 does not soften the FAIL verdict.

## What Was Examined

- Perception V2 and the experimental/V3 break lifecycle.
- Formal structure graph and formal causal episode graph.
- Swing hierarchy, protected-point, active-range, liquidity, inducement, and causal POI modules.
- AI evidence pack, prompts, annotation composer, annotation validator, renderer, and bitmap review.
- Causality, swing, rendering, crop, blind-vision, visual-adversarial, break-lifecycle, causal-graph, and native-story-pack tests.
- Gold-set evaluator and current case library.
- The framework's cited visual-grounding, look-ahead, counterfactual, and calibration research.

## Weighted Readiness Score

| Dimension | Weight | Readiness | Weighted | Strict finding |
|---|---:|---:|---:|---|
| Raw candle and level perception | 10 | 5/10 | 5.0 | Strong from OHLCV; real screenshot perception unmeasured. |
| Exact geometric grounding | 15 | 4/10 | 6.0 | Anchors exist, but source/display geometry is conflated. |
| Swing hierarchy | 15 | 4/10 | 6.0 | Multi-scale candidates exist; gold hierarchy and counterfactual stability do not. |
| Structural classification | 10 | 5/10 | 5.0 | V3 is materially better; many V1 controlling breaks are challenged in replay. |
| Protected-point and causal reasoning | 15 | 3/10 | 4.5 | Graph lineage exists; protected origin is still often derived from selected OB rather than independently proven. |
| Liquidity and sweep classification | 10 | 4/10 | 4.0 | Wick/body distinction exists; sequential sweep-vs-breakout validity is unmeasured. |
| Range, POI and inducement reasoning | 10 | 5/10 | 5.0 | Causal POI authority is promising; pre-return ranking and inducement anti-hindsight are unproven. |
| Temporal validity and no-look-ahead | 10 | 7/10 | 7.0 | Strongest area: cutoff filtering, confirmation times, and truncated/full-history equivalence. |
| Uncertainty and abstention | 3 | 6/10 | 1.8 | Fail-closed states are real; confidence is not calibrated. |
| Annotation communication | 2 | 4/10 | 0.8 | Sparse charts improved; exact semantic-to-pixel reconstruction is not proven. |
| **Total** | **100** |  | **45.1/100** | **Readiness only; no accuracy claim.** |

## Catastrophic Gates

| Gate | Status | Evidence and verdict |
|---|---|---|
| 1. Future candles justify an earlier conclusion | **PROVISIONAL PASS** | The canonical causality test compares truncated and full history at 100 random cutoffs. V3 also filters closed candles at `decision_time`. This has not yet been repeated across the complete AI/POI/annotation pipeline. |
| 2. Invented invisible level/candle | **PARTIAL** | Deterministic annotation objects require evidence IDs, but real visual-provider grounding is untested. |
| 3. Internal structure labeled external | **PROVISIONAL PASS** | Formal graph and annotation validators enforce scope, but no adjudicated confusion matrix exists. |
| 4. LTF CHoCH reverses HTF external structure | **PROVISIONAL PASS** | Parent/child invariants are fail-closed and the V3 graph is downgrade-only. |
| 5. Wick penetration called close-based BOS | **PROVISIONAL PASS** | V3 emits `WICK_PROBE`/`EXPIRED_WICK_PROBE` and requires body close plus acceptance. |
| 6. Annotation changes object coordinates | **FAIL** | `annotation_candidate_composer.py` clips `start_index` or `start_time` inside the drawing object. Evidence and display geometry are not first-class separate fields. |
| 7. POI rank uses future reaction | **UNPROVEN / GATE CLOSED** | No frozen pre-return POI-ranking cohort exists. Certification cannot pass until ranking is recreated at historical cutoffs and scored before returns. |
| 8. Every penetration treated as sweep | **PARTIAL** | Reclaim evidence exists, but accepted-breakout versus sweep is not evaluated sequentially on real gold cases. |
| 9. Confidence fabricated without evidence | **FAIL** | Multiple modules emit fixed/heuristic values such as 0.55, 0.75, 0.78, 0.92, and 1.0 without calibration against adjudicated correctness. |
| 10. Refusal to abstain | **PASS** | `REVIEW_REQUIRED`, `WATCH_ONLY`, `THESIS_ONLY`, unresolved states, and disabled execution contracts are implemented. |

**Catastrophic result:** FAIL. Gates 6 and 9 fail directly. Gates 7 and 8 remain unproven and therefore block certification.

## Evidence That Is Real

### 1. Temporal discipline is meaningful

`tests/stress_tests/test_B1_causality.py` runs 100 decision-time comparisons between truncated history and full history. This is an actual future-leakage check, not a prompt assertion.

`smc_desk/perception/experimental_break_engine.py`:

- filters candles to `close_time <= decision_time`;
- distinguishes wick interaction from body close;
- expires stale wick probes;
- requires penetration, displacement, and follow-through/valid retest;
- keeps signal, paper, and live execution disabled.

This is the system's strongest defensible capability.

### 2. Fail-closed authority is real

`formal_causal_episode_graph_v2` is observe-only and downgrade-only. It can challenge V1, cannot promote trade state, and cannot authorize entry, stop, target, paper execution, or live execution.

That is good epistemic engineering. It reduces harm, but it does not establish that the surviving interpretation is correct.

### 3. The causal graph is a genuine improvement

The graph connects accepted structure events to broken swings, displacement evidence, POIs, sweep/inducement hypotheses, and candidate protected origins. This is substantially better than isolated BOS/OB/FVG labels.

The remaining weakness is that some edges are generated by bounded heuristics rather than adjudicated causal truth. For example, sweeps are linked when they share direction and fall within a seven-day pre-event window; that is useful candidate generation, not proof of causality.

## Evidence That Is Weaker Than Its Name Suggests

### Swing stress tests

- The protected-point test only checks that `structure_state` is not `None`.
- The CHoCH/BOS test only checks that any emitted break type is one of `bos` or `choch`.
- The range test explicitly accepts that a tight oscillation creates many swings and asserts only that at least one swing exists.

These tests do not validate protected-point correctness, CHoCH disambiguation, or noise robustness.

### Rendering stress tests

`tests/stress_tests/test_F_rendering.py` explicitly calls itself a smoke suite. It checks imports, module count, and whether source text contains the word `review`. It does not prove semantic-to-pixel fidelity, one-tick accuracy, label collision safety, or chart sterility.

### Crop and visual adversarial tests

- `test_G2_crop_truth.py` uses a hand-written mock that abstains when the filename contains `cropped`; its unreadable-axis test is empty.
- `test_blind_vision.py` supplies mock JSON, bypasses image-file validation, and then verifies the mock response.
- `test_vision_adversarial.py` checks that the prompt contains words such as `hallucinate`, `price`, or `guess`; it does not challenge a vision model with an adversarial chart.

These are valid interface tests. They must not be presented as evidence of visual robustness.

### Bitmap self-review

`bitmap_annotation_review.py` honestly states its limit. It measures resolution, pixel density, darkness, saturation, and blankness, and sets `semantic_correctness_proven_by_pixels` to `false`.

This is useful renderer health checking, not AI visual self-review of SMC correctness.

## Gold-Truth Result

Fresh evaluation of `case_library` produced:

```text
status: insufficient_ground_truth
eligible adjudicated cases: 0 / required 20
skipped cases: 172
precision: unavailable
recall: unavailable
F1: unavailable
```

The designated AI SMC gold-set audit also reports zero adjudicated cases. Therefore:

- no BOS/CHoCH/order-block/FVG/sweep/inducement accuracy claim is valid;
- no visual consistency claim is valid;
- no confidence calibration claim is valid;
- no expert-level or trader-level perception claim is valid.

## Exact Coordinate Failure

The evidence anchor stores source geometry. However, `_structure_object()` currently clips long marks:

```python
if start_index is not None and end_index is not None and end_index - start_index > 18:
    start_index = end_index - 18
    start_time = None
    end_time = None
```

It similarly changes projected HTF `start_time` for display. The visual intent is sensible, but the schema cannot reconstruct both the original evidence segment and the displayed segment from the drawing object alone.

The correct repair is:

```text
evidence_geometry:
  source_start_time/index
  source_end_time/index
  source_price/zone
  immutable: true

display_geometry:
  display_start_time/index
  display_end_time/index
  clipping_rule
  derived_from_evidence_geometry_hash
```

The validator must reject any display geometry that changes price, crosses outside permitted evidence bounds, or lacks a reproducible derivation.

## Confidence Failure

The repository contains many useful evidence-quality scores. They are not probabilities of correctness. Until gold labels exist, values such as `0.78` or `1.0` should be renamed to `heuristic_score`, `evidence_strength`, or an ordinal status.

The system may only call a value `confidence` after recording:

- a defined prediction target;
- an adjudicated evaluation cohort;
- reliability bins;
- expected calibration error or Brier score;
- sample count per bin;
- abstention coverage and selective risk.

Until then, numerical confidence is false precision.

## Framework Quality Audit

The supplied framework is strong and should become the governing perception evaluation protocol. It correctly prioritizes evidence coordinates, first-knowable time, causal reconstruction, counterfactuals, perturbations, abstention, and catastrophic gates.

**Research-scope correction:** RefChartQA is a general chart-question-answering and visual-grounding benchmark, not a candlestick-specific or SMC-perception benchmark. It supports requiring answers to be linked to their supporting chart elements. *Thinking with Visual Grounding* more broadly supports tying intermediate visual reasoning claims to explicit image regions, although it is also not trading-specific. *Look-Ahead-Bench* supports the need for point-in-time evaluation and the detection of look-ahead bias in financial LLM workflows, but it does not by itself validate the system's candle-cutoff or end-to-end causal-integrity implementation.

The original claim that RefChartQA found models stronger in persistent candlestick trends and weaker in ordinary or ambiguous market conditions is unsupported by that paper and has been removed from the governing protocol.

OHLCV-native perception and screenshot/VLM perception also require separate scorecards. Exact candle arithmetic from canonical data is not the same capability as reading compressed pixels, axes, themes, and crops.

Research direction is nevertheless sound: explicit visual grounding improved chart QA reliability in RefChartQA, visually grounded reasoning is designed to attach claims to image regions, point-in-time financial evaluation addresses look-ahead bias, counterfactual perturbations reveal brittle VQA behavior, and calibration must be measured rather than asserted.

## Required Repair Order

### P0: Integrity blockers

1. Introduce immutable `evidence_geometry` and derived `display_geometry` in annotation plan V3.
2. Remove or rename uncalibrated numeric `confidence` fields from certified outputs.
3. Implement the framework's complete per-object evidence contract, including first-knowable candle, competing interpretation, invalidation, doctrine hash, and abstention.
4. Make annotation reconstruction a round-trip test: detector/graph -> plan -> pixels -> recovered semantic object.

### P1: Actual perception evaluation

5. Freeze at least 30 varied chart cases at point-in-time cutoffs, then obtain two independent expert labels plus blind adjudication.
6. Preserve disagreement rather than forcing one pseudo-gold answer where doctrine is ambiguous.
7. Measure object precision/recall, anchor and price errors, status accuracy, hierarchy violations, and causal-edge accuracy.
8. Freeze POI rankings before revealing returns; never score a level selected after seeing its reaction.

### P2: Real adversarial vision

9. Replace mock-only crop/theme tests with actual image variants: crop, recolor, resize, zoom, linear/log, candle-width changes, anonymized symbol, hidden axes, and injected false drawings.
10. Add no-chart, blank-chart, random-chart, and insufficient-resolution baselines. The correct output must be abstention.
11. Run sequential candle reveal for swing, sweep, break, POI, and protected-point lifecycles.
12. Add controlled single-candle counterfactuals and verify only causally dependent conclusions change.

### P3: Certification

13. Calibrate confidence only after enough adjudicated cases exist.
14. Report abstention coverage and selective accuracy, not raw accuracy alone.
15. Keep perception certification separate from predictive edge and profitability testing.

## Validation Performed During This Audit

- Focused causality/vision/rendering/V3 suite: **37 passed**.
- Gold evaluator: **0 eligible / 172 skipped**, `insufficient_ground_truth`.
- Designated AI SMC gold set: **0 adjudicated cases**, `INSUFFICIENT_GROUND_TRUTH`.
- `git diff --check`: **passed**.
- `.venv/bin/python -m compileall -q smc_desk tools tests`: **passed**.
- Full repository suite: **990 passed, 1 skipped in 144.51 seconds**.

The full green suite proves repository consistency against its present tests. It does not override the gold-truth absence or the catastrophic-gate failures documented above.

## Final Answer to the Framework's Ultimate Question

Can the system currently reconstruct the market at an exact candle cutoff, ground every conclusion, separate observation from inference, maintain hierarchy, expose uncertainty, and survive counterfactual and presentation perturbation?

**Partially in deterministic OHLCV space; not yet proven in visual or expert-adjudicated space.**

The correct current label is:

```text
ADVANCED RESEARCH-GRADE, FAIL-CLOSED SMC PERCEPTION LAB
NOT EXPERT-CERTIFIED
NOT CALIBRATED
NOT EXECUTION-AUTHORIZED
```

That is not a dismissal of the work. It is the first verdict strict enough to make the next round of work scientifically meaningful.
