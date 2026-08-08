# SMC Interrogation 30-Case Cohort

## Verdict

The empirical evaluation machinery is now complete enough to collect real evidence. The cohort itself is integrity-verified but remains `NOT_GOLD`. No perception score is available yet.

## Cohort

- 30 historical point-in-time cases: six volatility strata each for BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, and BNBUSDT.
- Selection was engine-blind and used only timestamp plus rolling 96-bar true-range fraction.
- Minimum spacing between cutoffs: 45 days.
- Future outcomes, detector outputs, and profitability were excluded from selection.
- System source freeze: 410 files, SHA256 `74906372ab6c6b8e77a0611567f11ced4017ad212dbcff140f208705e45e96fa`.
- Cohort content SHA256: `28207e847f60d1507f984eb7ca1900ac18ece4cf23b1286242dbf53a08ac584c`.

Each case contains:

- four clean completed-candle charts and exact candle maps;
- 15 true OHLC rerenders, including colour swap, dark theme, width, crop, resolution, grid, scale, anonymisation, watermark, false BOS, and misleading-caption attacks;
- four sequential replay stages;
- one exact one-candle counterfactual with a machine-verifiable changed-field proof;
- two independent reviewer templates;
- one source-normalized anonymous adjudication path;
- one system response template with quarantined calibration confidence;
- all 20 hardest framework questions and all ten scoring dimensions.

## Integrity Proof

`tools/verify_perception_interrogation_cohort.py` reports:

- status `PASS`;
- 30 cases;
- 1,230 checked files;
- 15,900 checked visible candles;
- 30 verified one-candle counterfactuals;
- zero issues.

## Framework Coverage

| Section | Engineering evidence | Empirical state |
|---|---|---|
| 1 Evidence contracts | Complete object contracts and dual geometry | Pending expert scoring |
| 2 Raw visual perception | Clean charts, candle maps, no-evidence assets | Real visual responses pending |
| 3 Swing selection | Candidate/confirmed lifecycle and exact cutoffs | Expert agreement pending |
| 4 Structure | Formal graph, external/internal guard, wick/close invariant | Blind adjudication pending |
| 5 Protected causal points | Causal episode and POI authority | Expert causal-edge scoring pending |
| 6 Liquidity/sweeps | Explicit penetration/reclaim/acceptance/sweep lifecycle | Sequential gold pending |
| 7 Dealing ranges | Protected swing range authority | Competing-range gold pending |
| 8 Displacement/FVG | Evidence contracts and causal status | Precision/recall pending |
| 9 POI ranking | Pre-reaction hash freeze | Expert ranking pending |
| 10 Inducement | Candidate/retrospective distinction in questions | Expert labels pending |
| 11 MTF reasoning | Independent timeframe charts and parent guard | Blind scoring pending |
| 12 Temporal validity | Four cutoffs per case plus runtime causality | Object lifecycle scoring pending |
| 13 Counterfactuals | One exact one-candle mutation per case | Expected change adjudication pending |
| 14 Uncertainty | Abstention fields and quarantined confidence | Calibration pending |
| 15 Adversarial visuals | 15 rerenders per case | Real response consistency pending |
| 16 No evidence | Blank, random, unreadable, and no-chart pack | Real abstention responses pending |
| 17 Annotation | Immutable geometry and normalized plans | Blind annotation score pending |
| 18 Trade readiness | Fail-closed state and no-trade gating | Expert state agreement pending |
| 19 Hard questions | All 20 embedded per case | Answers pending |
| 20 Scoring | Ten exact weights and weighted blind scorer | No completed cases |
| 21 Catastrophic gates | Ten case-fail gates enforced | No adjudicated outcomes |
| 22 Procedure | Stages 1-8 implemented; stage 9 separated | Independent people required |

## Blindness Repair

Reviewer and system submissions are normalized into the same anonymous schema. Raw calibration confidence, runtime metadata, reviewer identity, and role are excluded from adjudicator-visible submissions. Original source hashes and the private identity map are verified only after adjudication.

## Current Boundary

The system now has a real route to empirical certification. It does not yet have the independent human decisions required to traverse that route. Empty templates, AI consensus, deterministic engine output, and this report are not gold truth.

The historical cohort can measure the frozen system, but it is not an untouched future holdout. A later frozen future cohort is still required before making the strongest generalisation claim.

## Cryptographic Authority

All empirical evidence must now be Ed25519-signed against a trust registry whose exact hash is pinned into the cohort manifest. Trust provisioning requires distinct keys for two reviewers, adjudicator, system operator, visual auditor, and calibration authority. The current cohort remains `UNPROVISIONED`; therefore no evidence file can presently unlock certification.

This is deliberate. The system cannot appoint itself as its own independent reviewer.
