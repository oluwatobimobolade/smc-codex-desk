# Causal POI Authority Repair

## Objective

Replace nearest/deepest/last-opposing-candle POI selection with a deterministic,
fail-closed causal authority layer. The system must identify the best evidenced
origin for the current structural narrative, preserve lower-timeframe
refinements as subordinate objects, and abstain when causality is unresolved.

## Truth Boundary

No order block, FVG, or supply/demand zone can be known in advance to react
100% of the time. This work targets deterministic rule classification and
auditable refusal. It does not guarantee future reaction, predictive accuracy,
profitability, or execution safety.

## Research Conclusion

The educational doctrine reviewed converges on context, displacement,
structure break, retracement, and liquidity. It does not support a universal
"nearest" or "deepest" rule. Market-microstructure research supports a causal
relationship between order-flow imbalance and short-horizon price changes, but
does not prove that visually inferred SMC order blocks are deterministic.

The implemented hierarchy is therefore:

1. Certified formal MTF structure and active range.
2. Explicit break-to-departure-origin lineage.
3. Protected-reversal origin, latest continuation origin, or prior unbroken origin.
4. External structure ownership before internal reaction structure.
5. No superseding opposite external break.
6. Valid lifecycle and active-range containment/location.
7. Departure quality and causal FVG support.
8. Depth only as the final tie-break.

## Implementation

- `OrderBlockDetector` now preserves a contiguous opposing origin cluster and
  the complete departure-candle trace to the accepted break.
- FVG-to-break association now requires chronological source-candle overlap;
  the old eight-hour proximity shortcut no longer establishes causality.
- `causal_poi_authority_v1` classifies objects as primary causal POI, secondary
  reaction POI, execution refinement, shallow inducement hypothesis,
  invalid/rejected, or unresolved.
- Internal-break POIs cannot own the primary external thesis.
- A standalone FVG is blocked while any plausible OB lineage remains unresolved.
- The AI prompt reads causal POI authority after the formal graph and before
  selecting an active POI.
- The validator rejects POIs outside the authority selection, FVG promotion over
  an eligible causal OB, wrong bounds, and missing controlling-parent IDs.
- HTF POIs render onto 15m charts by timestamp rather than reusing incompatible
  HTF row indices.
- Every canonical run writes `causal_poi_authority.json` beside the formal graph.

## Adversarial Tests

- Protected reversal origin outranks a shallower continuation OB for causal,
  not depth, reasons.
- Temporal FVG proximity is rejected as causal membership.
- Nearest opposing candle geometry is unresolved without a departure trace.
- Outside-range candidates are not promoted.
- Internal-break origins remain secondary.
- Standalone FVG promotion is blocked while OB lineage is unresolved.
- The annotation selector uses authority rather than nearest-zone ranking.

## Live Observe-Only Evidence

Final run:
`analysis_runs/CAUSAL_POI_AUTHORITY_SMOKE_FINAL2_20260712/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_134616/XRPUSDT`

- Source: Binance USD-M perpetual closed OHLCV.
- XRPUSDT 1H had three internal OB reaction candidates and one external-link FVG.
- The authority refused to promote the FVG and returned
  `FVG_PRIMARY_BLOCKED_BY_UNRESOLVED_OB_LINEAGE`.
- Official output remained `THESIS_ONLY` with no POI rectangle, trade box,
  entry, stop, target, paper execution, or live execution.
- Visual inspection confirmed a sparse chart with one local BOS mark.

BTCUSDT and XRPUSDT dual smoke:
`analysis_runs/CAUSAL_POI_AUTHORITY_SMOKE_FINAL_20260712/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_134444`

Both workflows completed against live closed candles and stayed observe-only.

## Validation

- Focused causal/annotation/detector suite: 49 passed.
- Final full suite: 954 passed, 1 skipped in 116.35 seconds.
- `git diff --check`: PASS.
- `compileall smc_desk tools tests`: PASS.

## Remaining Work

- Freeze a balanced blind cohort containing primary-origin, continuation-origin,
  FVG-only, multi-candle cluster, invalidated, and ambiguous cases.
- Adjudicate the causal origin and controlling timeframe independently of the
  engine output.
- Measure classification agreement before making perception-accuracy claims.
- Only after perception validation, test outcome calibration by POI class with
  costs and walk-forward holdouts.

No strategy edge or execution authority was created.

## 2026-07-12 GBPUSD Lineage Follow-Up

The user correctly challenged the shallow 4H continuation block. The follow-up
repair consolidates duplicate OB lineages, prefers the accepted external-break
lineage, permits a true parent origin beyond a newer nested range, and exposes
parent-scope 1H/15m refinements without promoting them.

Fresh replay selected 4H `1.332445-1.336988` as the external BOS origin and
certified the geometric child-OB overlap `1.334187-1.334704` as refinement
only. Reaction remains explicitly unguaranteed. Final full validation after the
broader programme work was 981 passed, 1 skipped.
