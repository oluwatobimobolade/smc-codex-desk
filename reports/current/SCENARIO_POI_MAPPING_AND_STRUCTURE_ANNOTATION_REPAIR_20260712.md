# Scenario POI Mapping and Structure Annotation Repair

The system no longer treats "no trade now" as "nothing useful to map." It now preserves both directional POI scenarios until the formal graph adjudicates them, then shows the best causally grounded watch POI together with the material structure that explains the market story.

## What Was Wrong

XRP's bullish 15m OB at `1.0959-1.1005` existed in detector evidence and owned the bullish BOS through `1.1008`. A provisional bearish hierarchy caused the lifecycle to delete the zone before the formal graph could apply its newer bullish 15m structure truth. The renderer then had no POI and showed only one BOS.

## What Works Now

- Opposing scenario POIs are retained, not promoted.
- Formal graph direction can correct only a provisional direction mismatch.
- Mixed context remains mixed and cannot authorize a trade.
- `THESIS_ONLY` charts can show one scenario POI plus two material structure marks.
- Internal structure is visibly labeled and cannot impersonate parent/external structure.
- OBs and FVGs retain their true object type.
- The thesis reports scenario POIs even when no official active POI exists.

## Live Result

The verified XRP chart now shows the `15M Bullish OB 1.0959-1.1005`, `1H Internal CHoCH 1.0996`, and `15M BOS 1.1008`. The verified SOL chart shows `1H Bearish FVG 77.88-78.09`, `1H BOS 77.62`, and `15M BOS 77.83`. Both stayed `THESIS_ONLY`, both passed annotation validation and visual review, and neither contains a trade box.

Full evidence and charts:

`analysis_runs/POI_SCENARIO_REPAIR_XRP_SOL_VERIFIED_20260712/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_203338`

Validation: `984 passed, 1 skipped`; compilation and diff checks passed.

## Honest Limit

A mapped POI is a route-map hypothesis, not a guaranteed reaction. This repair improves what the system sees, retains, explains, and draws. It does not establish predictive edge or enable execution.

