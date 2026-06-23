# SMC Perception Accuracy Protocol

## Purpose

This protocol measures whether the engine and a vision model recognize the
same SMC objects that expert reviewers recognize. It does not promise that SMC
itself is objectively perfect or profitable.

## Two Different Tests

1. **Synthetic contract tests**
   - Use `smc_desk/synthetic.py` and `tools/perception_benchmark.py`.
   - Catch regressions in detector mechanics, threshold behavior, and scale handling.
   - Never report their recall as real-market accuracy.

2. **Gold-set perception evaluation**
   - Use source-aligned real cases with `review_status=gold_standard` or `approved`.
   - Require `expert_label.perception_annotations.label_status=adjudicated`.
   - Run `tools/evaluate_perception_gold.py --root case_library`.
   - This is the only report allowed to describe precision, recall, F1, or calibrated perception quality.

## Annotation Contract

Each annotation is one chart object:

- Primitive: `bos`, `choch`, `liquidity_sweep`, `fvg`, `order_block`,
  `equal_highs`, `equal_lows`, `inducement`, `supply`, or `demand`.
- Timeframe and direction.
- Events: candle timestamp and price.
- Zones: `price_low` and `price_high`.
- BOS/CHoCH: structure scope (`internal`, `swing`, or `external`).
- State where applicable: `fresh`, `partial`, `mitigated`, `swept`, or `unswept`.
- Two reviewers and an adjudicator before the labels become gold.

## Matching Rules

- Events must match primitive, direction, timeframe, timestamp tolerance, and
  percentage price tolerance.
- Zones must match primitive, direction, timeframe, and price-band IoU.
- Each machine object can match only one expert object. Extra detections are
  false positives; missed expert objects are false negatives.

## Accuracy Claims

Do not claim 99% from a point estimate alone. A primitive needs:

- at least 100 independently adjudicated instances across multiple pairs and regimes;
- high precision and recall, not recall alone;
- a low false-positive rate on explicit negative/chop cases;
- a lower confidence bound that meets the target, not just a rounded average;
- repeated holdout performance after detector changes.

## Vision Rule

Vision sees a raw chart first. Engine overlays are for explanation and audit,
not for blind vision scoring. Engine-generated labels are pseudo-labels; they
may measure model-to-engine agreement but cannot validate the engine itself.

When vision is uncertain, it must abstain or report ambiguity. It may never
invent an entry, stop, target, BOS, CHoCH, or zone price that is not present in
the structured engine output.
