# WP-SMC-14 — POI Contract and Native Markup Repair

**Authority mode:** `deterministic_poi_and_native_markup_repair_observe_only`  
**Status:** `PASS_LOCAL_OBSERVE_ONLY_EMPIRICAL_CERTIFICATION_UNCHANGED`

## Why this package exists

A deeper audit showed that the earlier POI visibility change passed its local
tests but did not yet form one trustworthy production chain. Rejected OBs
could be promoted downstream; the scorer and evidence builder read a stale
candidate schema; historical mitigation could reset to fresh; market state had
no real POI-arrival confirmation sequence; and the TradingView compiler did
not have a live capability handshake matching the local MCP.

## Repaired contract

- A canonical POI adapter preserves the timeframe-qualified `poi_id` as the
  downstream object identity while retaining the detector `source_object_id`.
- The causal OB gate is enforced again at the causal-authority boundary.
  Rejected geometric bases remain visible but cannot receive a PASS causal
  certificate or production-primary authority.
- The detector keeps plausible older opposing clusters in a visibility ledger,
  explicitly marks them non-causal, and traces delayed breaks from the actual
  body-close confirmation candle.
- POI lifecycle is replayed candle by candle after confirmation. First touch,
  partial mitigation, full mitigation and body-close invalidation therefore
  cannot disappear when price later leaves the zone.
- `causal_poi_authority_v1` is the single production primary selector. The
  uncalibrated quality score explains the primary and ranks alternatives; it
  cannot replace the authority-selected POI.
- Market state now waits for the real sequence after POI arrival: aligned LTF
  liquidity sweep, displacement, body-close structure break, then a
  confirmation-candle-close entry model. This remains observe-only.
- Default/CE entry geometry is one contract (zone midpoint) across exact and
  semantic lookup; proximal/distal models are direction-aware.
- Forex session reconstruction accepts expected weekend closures but rejects
  unexplained midweek gaps. Crypto remains continuous and fail-closed.
- Delayed confirmation records every structural level the confirmation candle
  actually closed through.
- Static and TradingView renderers share visual tokens. The local TradingView
  MCP now reports a versioned native drawing capability contract, accepts rays
  and bounded multipoint paths, supports targeted updates/removal, and keeps
  workflow cleanup away from destructive `draw_clear`.

## Identity correction

`WP-SMC-13` was already reserved for the analyst-selected development cohort.
The earlier POI-visibility record is retained as append-only history but is
superseded in identity by this WP-SMC-14 package. WP-SMC-13 remains the next
empirical human-truth gate; this repair does not substitute for it.

## Validation

- Final exact-source R2 repository: **1,350 passed, 1 skipped in 375.46s**.
- The earlier R1 source state passed **1,348 passed, 1 skipped** before the
  CADJPY diagnostic exposed and prompted the final POI-planner repair.
- Focused POI/detector, narrative/market-state, entry, TradingView compiler,
  forex-session and structure suites passed.
- Python compile, `git diff --check`, authority-boundary and governance checks
  passed.
- TradingView MCP offline contract/sanitisation: **72 passed**; ESLint reported
  zero errors and four pre-existing warnings outside the drawing repair.
- The live MCP end-to-end suite was not forced because it requires a CDP
  attachment; the signed-in TradingView app was not restarted or duplicated.

## CADJPY diagnostic

The complete Yahoo 1H source failed closed, correctly, because it contains a
two-hour midweek hole from 2026-04-20 06:00 to 09:00 UTC. The pipeline was then
run on the unchanged source's 1,889 rows after that last defect. The diagnostic
resolved 1D/4H/1H bearish context, a 110.800 equal-lows draw, and a fresh 1D
bearish OB at 115.871–116.460. The nine-object annotation plan and deterministic
geometry resolution passed; all three pixel reviews passed.

Artifacts:

- `analysis_runs/CADJPY_WP_SMC_14_POST_GAP_DIAGNOSTIC_20260809/evidence_pack.json`
- `analysis_runs/CADJPY_WP_SMC_14_POST_GAP_DIAGNOSTIC_20260809/charts/`

This is a diagnostic integration result, not forex/CADJPY certification and
not a trade recommendation.

## Limits

- The quality weights are reasoned defaults, not human-calibrated constants.
- Native compiler/MCP contract tests do not prove a currently attached
  TradingView instance supports every shape until `draw_capabilities` returns
  the matching live contract.
- The signed-in TradingView app was not restarted or duplicated for testing.
- Forex and CADJPY are not certified scope; integration there is diagnostic.
- No human markup, perception accuracy, predictive edge, signal, paper, live,
  or execution authority is created.
