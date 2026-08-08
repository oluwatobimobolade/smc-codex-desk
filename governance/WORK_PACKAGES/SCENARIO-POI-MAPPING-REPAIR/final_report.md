# Scenario POI Mapping and Sparse Structure Repair

Date: 2026-07-12  
Status: COMPLETE - LOCAL OBSERVE-ONLY VALIDATION PASSED

## Problem

The canonical detector could identify a valid directional OB/FVG, but the legacy POI lifecycle discarded it when its direction disagreed with a provisional hierarchy bias. The later formal structure graph therefore had no object to adjudicate. In mixed context, `THESIS_ONLY` also collapsed into "no active POI" and the professional renderer showed only one recent 15m break.

The XRPUSDT failure was concrete: the detector contained a causally traced bullish 15m order block at `1.0959-1.1005`, linked to `BOS_bullish_1783868400.0`, but the lifecycle removed it while using a stale bearish 15m hierarchy label.

## Repair

- POI lifecycle now maps both directional scenarios and records `hierarchy_bias` plus `bias_alignment`; it no longer erases an opposing scenario before formal adjudication.
- Causal POI authority now reads the complete lifecycle set as well as legacy `active_pois`.
- The formal graph may reconcile only `INVALID_DIRECTION_MISMATCH` when the POI direction matches the graph's certified external direction. Other lifecycle/range/causality failures remain rejected.
- Mixed `THESIS_ONLY` and `WATCH_ONLY` charts may show one causally selected scenario POI without promoting it to an official active POI or trade.
- Sparse annotation now selects at most the material 1H and 15m structure marks. If the controlling external 1H swing begins outside the visible execution chart, the latest visible internal break is used and explicitly labeled `Internal`.
- The thesis now reports a `Scenario Poi Map` instead of falsely saying no POI exists.
- Context-chart visibility is capped at three objects: one scenario POI and two material structure marks. Entry, SL, TP, risk, RR, and trade boxes remain forbidden outside `TRADE_PLAN_READY`.

## Verified Live Evidence

Run root:

`analysis_runs/POI_SCENARIO_REPAIR_XRP_SOL_VERIFIED_20260712/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_203338`

XRPUSDT official chart:

- `15M Bullish OB` at `1.0959-1.1005`
- `1H Internal CHoCH` at `1.0996`
- `15M BOS` at `1.1008`
- Official state: `THESIS_ONLY`
- Annotation validation: `VALIDATED`, zero issues
- Visual critic: `PASSED`
- No trade box

SOLUSDT official chart:

- `1H Bearish FVG` at `77.88-78.09`; explicitly FVG, not mislabeled as OB
- `1H BOS` at `77.62`
- `15M BOS` at `77.83`
- Official state: `THESIS_ONLY`
- Annotation validation: `VALIDATED`, zero issues
- Visual critic: `PASSED`
- No trade box

Artifact SHA-256:

- XRP chart: `5e274c28c2dcc29cea075b0ccf1060ce2761753b19222c627c82dcd25d06db14`
- SOL chart: `d88c6a817e6fcb2fda7cdd6ebc1bc90d585f22f264bf1e81e3c1bd5d32b39fd0`
- XRP evidence pack: `890bd430f507aa5839adfa260aa4916037765ec24046e5d063e7e83746bb9ffd`
- SOL evidence pack: `690972eef3c2a65a29d11fecaa2a1fe68fcfdd75f5a1820f2913ce3565417eb7`

## Validation

- Root-cause and affected regression set: `85 passed`
- Full repository: `984 passed, 1 skipped in 123.40s`
- `compileall`: PASS
- `git diff --check`: PASS
- Live Binance USD-M closed-candle run: PASS

## Authority Boundary

This repair proves deterministic retention, reconciliation, labeling, rendering, and refusal behavior. It does not prove expert perception accuracy, future POI reaction, strategy edge, or execution readiness. `signal_allowed=false`; paper and live execution remain disabled.

