# SMC Codex Desk

**An evidence-grounded Smart Money Concepts (SMC) market colleague.**

SMC Codex Desk reads multi-timeframe market structure like a disciplined trader,
annotates charts *only* from certified evidence, builds conditional scenarios,
remembers what changed since its last look, and refuses to say anything it
cannot prove. It is deliberately **not** a trading bot, a signal service, or a
predictive system.

```
Release:        colleague-core-rc0
Market truth:   completed 15m candles (UTC), Binance USD-M canonical
Execution:      live DISABLED / paper DISABLED (and always has been)
Perception:     research authority, deterministic and fail-closed
Prediction/ML:  research only - never decision authority
Certification:  NOT_CERTIFIED by design (human adjudication required)
Validation:     1,412 tests passed / 1 skipped + append-only registry
```

## Why this exists

The goal is a *colleague*, not an indicator: a system that validates market
data, reconstructs higher-timeframe charts from canonical lower-timeframe
candles, reasons about SMC structure, produces professional annotations,
remembers cases, and **abstains when the evidence is not enough**. The north
star is to be nearly always useful and highly accurate about *current* market
state and deterministic geometry, and honest about the future: predictive edge
must be earned through historical validation, untouched holdouts, live shadow
operation, and calibration - never claimed.

## Honest status (read this before anything else)

- **The system sees well and refuses honestly.** Every live run of recent
  symbols (BTC, ETH, HYPE, XAU, EURJPY, AUDNZD, CADJPY) ends in a fail-closed
  refusal rather than a weak claim. That is the intended behaviour.
- **It is not yet "sure", and that is measured, not a feeling.** Historical
  engine setups were net-negative (PF 0.71 / -0.18R over 1,088 trades on 4yr
  BTC+ETH calibration). The current edge hypothesis is *selectivity through
  narrative coherence* - the value lives in the refusal rate - and it can only
  be tested against human-marked cases, which do not exist yet.
- **Two structure models (V1 canonical vs V3 causal replay) disagree on most
  runs, and the system's only response is to refuse.** Reconciling them
  requires ratified doctrine and measured disagreement classifications (the
  next gate).
- **The AI reasoning lab is built but not yet wired into the production run
  path** (P6, gated on the next item).

## How it thinks

```
OHLCV -> PerceptionEngineV2 (15m/1h/4h/1d) -> Event Ledger
      -> MTF Graph + Parent-Child Guard
      -> Formal Structure Graph   [AUTHORITATIVE, 6 invariants]
      -> Causal Episode Graph v2 + Causal POI Authority
      -> Significance / Narrative Hierarchy / Market State (memory)
      -> Evidence Pack (hash-sealed) -> AI thesis (narrates only)
      -> Validator (downgrade-only) -> Annotation composer -> Visual critic
```

Authority model, in one paragraph: **deterministic geometry owns every price;
the AI owns only the words.** The formal structure graph is the single
authoritative source for bias, ranges, POI claims and annotations. The AI can
narrate, compare, and critique - it can never move a level, flip a bias, or
create trade authority. Everything a chart shows is traceable to a sealed
evidence ID; anything unproven is omitted, and omission is audited.

A setup may only be considered ready when the full doctrine holds: external
bias defined by swing structure (internal CHoCH is confirmation only), a fresh
POI aligned with premium/discount, liquidity swept before the break,
**body-close displacement** (wicks are never breaks), price at the POI, and at
least 1:3 R:R. Anything less becomes Watch/Pass at 0% risk.

## What it can do today

- Multi-timeframe SMC perception: swings, external/internal BOS and CHoCH,
  protected swings, order blocks, FVGs, liquidity pools, sweeps, inducement.
- Significance grading (ATR-normalised) so a real 11-bar fractal is not drawn
  as "major" and noise is not drawn at all.
- A hierarchical multi-timeframe narrative that treats a disagreeing child as
  a *retracement inside the parent*, not a contradiction - and names the
  standing liquidity draw ("where is price being pulled to?").
- A trader-sequence market state (MAP_CONTEXT -> ... -> TRADE_PLAN_READY) with
  **cross-run memory**: each run records what changed since the last look.
- Professional native MTF storyboards (dealing range, context supply/demand
  retained as context-only, IDM, MSS) beside a sparse, validator-checked
  annotation plan - plus a recorded *shadow* narrative selection so the two
  selectors can be measured against human markup.
- Governance that audits itself: append-only validation registry, source
  manifests with SHA-256, authority-boundary scanner, controlled status
  vocabulary, and a prohibition on generic "latest validation" claims.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # expect 1,412 passed, 1 skipped
```

Run one live observe-only analysis (fetches Binance USD-M / Yahoo data):

```bash
python tools/run_live_ai_smc_full_system.py --symbols BTCUSDT ETHUSDT
```

Per symbol the run writes `analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_<stamp>/<SYMBOL>/`:

| Stage | Artifact |
|---|---|
| `10_smc_evidence_pack*` | hash-sealed evidence pack (the source of all claims) |
| `13_official_ai_decision` | the observe-only decision |
| `14_clean_annotation_render` | validated annotation plan + native MTF storyboard PNGs |
| `15_ai_thesis` | the written thesis (with named invalidation + liquidity draw) |
| `16_formal_structure_graph` | structure graph, causal episodes, POI authority |
| `17_perception_interrogation` | certification verdict (NOT_CERTIFIED by design) |
| `18_colleague_memory_narrative` | what changed since last look + narrative shadow plan |

## The next gate: WP-SMC-13 - human truth

The system is one deliberate human action away from becoming *measurable*.
`governance/NEXT_ACTIONS.yaml` has exactly one priority-1 item:

> **Build and mark an analyst-selected development cohort.** Select 12-15
> cases from clean charts *without* seeing system answers, seal their
> provenance, and complete one expert markup pass **before** any threshold is
> tuned.

That cohort is the first-ever measurement of whether the system sees structure
like a competent human. It gates everything downstream: threshold calibration,
doctrine ratification (Constitution V2), wiring the AI reasoning roles into
the run path (P6), and reconciling the two structure models.

The tooling exists and refuses to do the human's job for them:

```bash
python tools/survey_candidate_cases.py \
  --source data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv \
  --start 2026-03-01 --end 2026-06-19 --every 3D \
  --output review_queues/candidate_survey_<date>
# pick 12-15 cases by eye, write my_picks.json, then:
python tools/seal_definition_set.py \
  --survey review_queues/candidate_survey_<date> \
  --selections my_picks.json --analyst-id founder \
  --output data/gold_sets/development_set_<date>
python tools/build_markup_cohort.py \
  --gold-set data/gold_sets/development_set_<date> \
  --output review_queues/markup_cohort_v2_<date> --reviewer-id founder
# mark every case (never open the _sealed_system_answer.json), then:
python tools/score_markup_cohort.py --cohort review_queues/markup_cohort_v2_<date>
```

## Repository map

```
governance/          READ THIS FIRST: authority precedence, current state,
                     next actions, decision log, work-package records,
                     append-only validation registry (evidence/)
smc_desk/            the Python package
  perception/        detectors, significance, narrative, market state, memory
  colleague/         smc_desk.colleague.orchestrator_v3 - the canonical runtime
  brain/             thesis, annotation planners, validators, structure_lab
  rendering/         native MTF storyboards, visual grammar, critics
  evaluation/        markup cohort integrity, scoring, gold sets
tools/               CLI entry points (live runner, survey/seal/score,
                     validation registry, TradingView bridges, case library)
specs/               Constitutions V1/V2, detector configs, ontologies
tests/               1,412 tests - run the full suite before any claim
strategies/ journal/ case_library/ backtests/
                     historical and comparison research (see below)
analysis_runs/       runtime outputs - gitignored by design (large evidence)
```

## Working process (contributors)

1. Read `governance/README_FIRST.md`, then `AUTHORITY_PRECEDENCE.yaml` and
   `CURRENT_STATE.yaml`.
2. Confirm the current gate in `evidence/VALIDATION_REGISTRY.json`.
3. Obey the contract: `signal_allowed` stays false; no threshold changes
   without cohort evidence; the sealed evidence pack stays a pure function of
   evidence; memory and shadow artifacts are post-run evidence only.
4. Validate: full `pytest`, `tools/check_governance_consistency.py`,
   `tools/check_authority_boundaries.py`, then append a source-bound record
   with `tools/run_validation_registry.py`. Records are append-only; failed
   records are retained.

## Historical and comparison utilities

The early SMC-Elite era tools remain for research: `tools/analyze_chart.py`,
`tools/analyze_live_dual_lens.py`, `tools/build_smc_case.py`,
`tools/generate_tradingview_overlay.py`, the WebBridge capture tool, and the
strategy documents under `strategies/smc/`. They are **comparison and
research only** - the canonical runtime is `orchestrator_v3` and the live
runner above.

## Honest boundaries (never claim otherwise)

- Passing tests means code behaved as specified. It does **not** prove market
  correctness, profitability, or edge.
- AI labels are weak/research labels until human adjudication; implementation
  coverage is not perception accuracy.
- Live crypto runs use exchange-native higher-timeframe candles; the
  candle-lineage certificate currently binds offline replays only. XAUUSD uses
  a GC=F COMEX proxy whose daily settlement gaps fail-closed on 15m/1h
  (disclosed in each run). Forex uses a Yahoo spot proxy.
- No claim of live or paper trading readiness, ever, from this repository.
