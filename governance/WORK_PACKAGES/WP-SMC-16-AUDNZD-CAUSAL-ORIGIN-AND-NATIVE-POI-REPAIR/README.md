# WP-SMC-16 — AUDNZD Causal-Origin and Native-POI Repair

Date: 2026-08-09  
Status: PASS — local observe-only diagnostic; forex certification unchanged  
Gate: `GATE-WP-SMC-16-AUDNZD-CAUSAL-ORIGIN-NATIVE-POI-001`

## Objective

Run AUDNZD through the complete D1/4H/1H/15M colleague system, verify the selected POI against its exact candles and accepted structural break, inspect every native chart, and repair only a defect reproduced by the real run.

## Confirmed defect

The 4H detector correctly found a bearish external MSS at `CHOCH_bearish_1785268800.0`, confirmed on 2026-07-29 04:00 UTC, and correctly traced its admitted departure-origin OB to the 2026-07-28 16:00/20:00 UTC origin cluster. The OB is `1.201539993–1.206750035` and owns the exact accepted break with a strong displacement score of `0.9433885`.

A newer August nested dealing range later placed its high at `1.201859951`. The earlier lifecycle classifier therefore marked the historical origin as `REVIEW_REQUIRED_STRADDLES_PROTECTED_LEVEL`. Causal authority honored that newer-range classification before evaluating exact break ownership, causing the true historical origin to disappear from the scenario story.

This was incorrect because a future nested range may deny *active-entry* use of an older zone, but it cannot erase the admitted causal origin of an already accepted external break.

## Repair

- An unspent order block survives the newer-range straddle classification only when it:
  - owns the exact currently accepted external break;
  - has an explicit departure trace;
  - passed the causal-origin admission gate;
  - is POI-grade;
  - matches the accepted break direction.
- The repaired object is explicitly `authority_scope: causal_scenario_only` and `active_entry_authority: false`.
- Original lifecycle status and scope are preserved for audit.
- Non-owning, older, geometric, rejected, invalidated, consumed, or terminal straddled zones remain rejected.
- Native POI labels now disclose partial mitigation, producing `Protected OB (partial)` on the AUDNZD 4H chart.

## Final AUDNZD result

Run: `analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260809_190112/AUDNZD`

- Source: Yahoo `AUDNZD=X` spot-chart proxy; closed bars through Friday 2026-08-07.
- Official state: `REVIEW_REQUIRED`.
- Official direction: `mixed`.
- Current 15M close: `1.198789954`.
- Active 4H range: `1.195009947–1.201859951`; price is in premium.
- Accepted 4H story: bearish external MSS, selected partial protected-reversal-origin OB `1.201539993–1.206750035`, followed by a bullish internal pullback.
- Provisional 1H and 15M controlling external breaks do not survive the stricter causal replay, so decision authority remains unresolved.
- No validated current sweep/displacement/active-entry sequence exists. No entry, stop, target, RR, trade box, paper order, or live order is emitted.

## Validation

- AUDNZD/POI/market-state/render regression ring: 118 passed in 1.44s.
- Compileall: PASS.
- Diff whitespace check: PASS.
- Authority boundary checker: PASS; 130 files scanned.
- Governance consistency: PASS; the 12-test WP-0044 governance ring passed.
- Native D1/4H/1H/15M deterministic storyboard and bitmap checks: PASS with semantic review pending.
- Exact source manifest: `SOURCE_MANIFEST.tsv`.

## Limitations

- AUDNZD and forex remain outside the certified BTCUSDT/Binance-USDM scope.
- Yahoo is a chart proxy, not executable broker truth.
- The run uses market-closed data and is not a live opening signal.
- Causal-origin classification does not guarantee a future reaction.
- Deterministic bitmap checks do not replace human semantic chart review.
- Native TradingView Desktop drawing remains blocked because the detected process uses the prohibited isolated audit profile rather than the owner's normal signed-in instance.
- No perception accuracy, predictive edge, signal, paper execution, live execution, or profitability claim is created.
