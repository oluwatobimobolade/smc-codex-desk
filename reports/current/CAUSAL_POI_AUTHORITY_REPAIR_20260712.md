# Causal POI Authority Repair

The system now separates geometric POI candidates from a controlling causal
POI. It no longer treats nearest, deepest, newest, last-opposing-candle, or
nearby-FVG heuristics as final authority.

## What Changed

- Order blocks preserve origin clusters and departure-to-break lineage.
- FVG links require source-candle overlap, not timestamp proximity.
- External primary POIs, internal reaction candidates, execution refinements,
  secondary zones, and inducement hypotheses have separate roles.
- Protected reversal origins may outrank shallow continuation origins when the
  causal lineage is stronger and still intact.
- Depth is only a final tie-break.
- FVGs stay supporting while causal OB lineage exists or remains unresolved.
- AI prompts, active-POI selection, validation, annotation, and run artifacts
  all consume the same authority object.

## Honest Result

This does not create a POI that will react 100% of the time. It creates a system
that can be certain about whether its own selection rules were satisfied and
that refuses to guess when the causal evidence is incomplete.

The final XRP live smoke proved the refusal path: the 1H FVG was not promoted
because the deeper OB candidates were only internal-lineage objects. The chart
remained thesis-only and did not invent a POI or trade plan.

## Evidence

- Full report:
  `governance/WORK_PACKAGES/CAUSAL-POI-AUTHORITY-REPAIR/final_report.md`
- Test report:
  `governance/WORK_PACKAGES/CAUSAL-POI-AUTHORITY-REPAIR/TEST_REPORT.json`
- Final XRP smoke:
  `analysis_runs/CAUSAL_POI_AUTHORITY_SMOKE_FINAL2_20260712/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_134616/XRPUSDT`
- Validation: 954 passed, 1 skipped; compileall and diff check passed.

The next evidence step is a frozen blind causal-POI cohort, not further tuning
on these live examples.

## GBPUSD Follow-Up

The deeper 4H OB `1.332445-1.336988` now wins because it owns the accepted
external BOS, not merely because it is deeper. The subordinate 1H and 15m OBs
produce an exact refinement overlap at `1.334187-1.334704`. Duplicate
external/internal lineages no longer allow the later internal copy to erase
the controlling external cause.
