# Strategy Truth Audit

Status: `HISTORICAL` WP-0001 audit scaffold. This is not the current controlling
strategy audit and cannot direct runtime behavior. Current source authority is
registered in `governance/SOURCE_DOCUMENT_REGISTER.yaml`; active operational
research contracts remain under `strategies/active/` and `specs/`.

## Mandatory Truth Statement

No current strategy is guaranteed profitable. The active objective is to build a
fully specified, falsifiable, evidence-driven master strategy candidate and test
it aggressively enough to accept or reject it honestly.

## Active Strategy Candidate

- Name: Regime-Aligned SMC Continuation V1
- Short name: RASC-SMC-V1
- Status: research candidate
- Authority: live shadow only
- Scope: Binance USD-M BTCUSDT perpetual, 15m canonical data, derived 1H/4H/1D
- Risk: 0% capital risk

## Initial Rule Findings

| Rule | Initial Status | Recommendation |
|---|---|---|
| Daily, 4H and 1H alignment | PROJECT_HYPOTHESIS | Replace mandatory identical alignment with objective 4H regime plus Daily veto in V1. |
| Protected structure | OPERATIONAL_DEFINITION | Keep under perception ontology; do not let internal breaks flip HTF bias. |
| Internal vs external structure | OPERATIONAL_DEFINITION | Keep separate; internal structure is execution confirmation only. |
| Liquidity sweeps | PROJECT_HYPOTHESIS | Keep in RASC-SMC-V1 confirmation sequence; test incremental value. |
| Displacement | PROJECT_HYPOTHESIS | Store attributes; do not require for V1 event existence until tested. |
| FVGs | PROJECT_HYPOTHESIS | Use qualified 1H FVG as V1 location; test against trend+FVG baseline. |
| Order blocks | UNKNOWN | Exclude from V1 until separately tested. |
| Premium and discount | PROJECT_HYPOTHESIS | Do not make mandatory in V1 without evidence. |
| Freshness and mitigation | OPERATIONAL_DEFINITION | Use lifecycle rules for 1H FVG validity; preserve provenance. |
| Inducement | UNKNOWN | Exclude from mandatory V1. |
| London and New York sessions | UNKNOWN | Not a hard V1 gate; can be feature/baseline stratifier. |
| News filters | UNKNOWN | Out of V1 until data source and test contract exist. |
| Five-minute confirmation | DEPRECATED_FOR_V1 | Do not add until 15m version is evaluated. |
| Fifteen-minute confirmation | PROJECT_HYPOTHESIS | Core V1 sequence. |
| Fixed 3R target | FAILED_OR_UNSUPPORTED | Replace with nearest active 1H/4H liquidity/structure target and min 1.5 net R. |
| Liquidity-based targets | PROJECT_HYPOTHESIS | Use in V1; test. |
| ATR stop buffers | EMPIRICALLY_SUPPORTED_PRINCIPLE | Use small sequence invalidation buffer; test cost/MAE impact. |
| A/A+ confluence scores | FAILED_OR_UNSUPPORTED | Do not size by score or grant automatic 2% risk. |
| One-percent and two-percent risk | DEPRECATED_FOR_V1 | Research/live shadow risk remains 0%; no automatic 2% A+. |
| Fixed holding periods | PROJECT_HYPOTHESIS | Use 48 completed 15m candle expiry as V1 resolution condition. |
| Retracement entries | DEPRECATED_FOR_V1 | Exclude; close entry avoids ambiguous fills. |
| Market-on-close entries | PROJECT_HYPOTHESIS | V1 entry is confirmation candle close only. |
| State-machine sequence requirements | PROJECT_HYPOTHESIS | Implement and test deterministic states. |
| Vision veto or downgrade behaviour | PROJECT_HYPOTHESIS | Vision remains observe-only; source mismatch can downgrade/abstain. |
| ML setup scoring | FAILED_OR_UNSUPPORTED | Treat current ML scoring as research scaffolding only. |

## Next Audit Work

Trace every rule above to implementation locations, configuration locations,
tests, backtest evidence, sample size, and cost assumptions. Promote no UNKNOWN
rule into mandatory strategy logic without registering a research hypothesis.
