# SMC Codex Desk — Market Structure Constitution V1 (human-readable)

**Status:** PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL  
**Machine-readable companion:** `specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml`  
**Doctrine hash:** see `specs/MARKET_STRUCTURE_CONSTITUTION_V1.sha256`  
**Source:** `Downloads/SMC_Codex_Expert_AI_Perception_Validation_Annotation_Programme.md` section 10  
**Purpose:** every perception module and every AI role reads from one doctrine. No code may treat this as authoritative until you adjudicate the contested decisions below.

---

## How this Constitution is meant to work

- It is **not** an answer to the perception question. It is the set of *questions and proposed defaults* the perception code needs resolved before it can function honestly.
- Every concept below states a definition, how a candidate is generated, how the AI selects among candidates, what confirms the interpretation, what invalidates it, what its lifecycle looks like, and who owns it in time.
- Every "contested decision" is marked **PROPOSED** with a proposed default plus the realistic alternatives. **You — the trader — pick.** No code may act on a clause until its contested decision is resolved.
- Every clause carries a `forbidden_shortcuts` field that names the mistakes the programme explicitly rejects.

The legal/canonical form is YAML (so the code can pin to a doctrine hash). This Markdown exists for human reading and for the adjudication log.

---

## Design principles (the doctrine the AI is built around)

1. **AI for semantics, not arithmetic.** AI decides which candidate matters, which causal narrative is strongest, which interpretation is alternative, why one POI outranks another, and when ambiguity remains. Deterministic code owns OHLC, timestamps, completed-candle status, candidate coordinates, event order, body/wick facts, future-data cutoff, and geometry.
2. **No single model authority.** Six separated AI roles, each with its own prompt, schema, repair budget.
3. **Five kinds of correctness.** Data, object detection, causal structure, chart communication, predictive/economic value. Measure each separately.
4. **Events, not just bars.** Fractals alone are insufficient; candidate generation combines fractals, directional change, prominence, change points, and displacement-linked origins.
5. **Levels are dynamic evidence.** Birth, salience, touch history, age, decay, active/consumed, owning timeframe.
6. **Anchor preservation.** No prompt compactor may drop an active external swing, the protected point, range endpoints, BOS origins, unswept external liquidity, active HTF POIs, blind-reader references, or critic challenges. Retrieval tools exist for the rest.
7. **Explicit lifecycles.** Sweep/breakout is a state machine, not a binary rule. Inducement is a hypothesis with states. Confidence is decomposed, not averaged.
8. **Abstain when uncertain.** Categories: confirmed, probable, ambiguous, contradicted, insufficient context.
9. **Descriptive before predictive.** Certify perception first; only then test whether it improves outcomes. Never use outcomes to redefine past structure labels.

---

## Concepts covered (16)

| # | Concept | Lifecycle | Owning timeframe | Key programme section |
|---|---|---|---|---|
| 1 | swing | CANDIDATE → STRUCTURAL → PROTECTED → BROKEN; or REJECTED / STALE | per candidate | §4 |
| 2 | protected_point | CANDIDATES → SELECTED → PROTECTED → VIOLATED/SUPERSEDED (cluster or single) | same as BOS owner | §5 |
| 3 | bos | LEVEL_ACTIVE → BREAKOUT_CANDIDATE → ACCEPTED or FAILED | per break | §4 / §6 |
| 4 | choch | INTERNAL_TRACK → CHoCH_CANDIDATE → CONFIRMED or RESUMED | per break | §5 / §4 |
| 5 | mss | EXTERNAL_TRACK → MSS_CANDIDATE → CONFIRMED | external timeframe | §4 / §5 |
| 6 | sweep | LEVEL_ACTIVE → PROBE → SWEEP_CANDIDATE → CONFIRMED_SWEEP | level's owning TF | §6 |
| 7 | breakout | LEVEL_ACTIVE → BREAKOUT_CANDIDATE → ACCEPTED or FAILED | level's owning TF | §6 |
| 8 | probe | ACTIVE → PROBE → CONCLUDED_PROBE (or upgrade) | TF of probing candle | §6 |
| 9 | reclaim | EXCURSION → RECLAIM_ATTEMPTED → CONFIRMED or FAILED | TF of reclaiming candle | §6 |
| 10 | active_range | PROPOSED → ACTIVE → EXTENDED or SUPERSEDED or STALE | per range (Daily→4H→1H→15m) | §7 |
| 11 | liquidity | POTENTIAL → ACTIVE → TESTED → CONSUMED or STALE | per level | §2.2 |
| 12 | poi | PROPOSED → FRESH → PARTIALLY_MITIGATED → FULLY_MITIGATED → INVALIDATED | origin TF (exec TF recorded separately) | §8 |
| 13 | inducement | NO_HYPOTHESIS → CANDIDATE → PATH_ACTIVE → CONSUMED or REJECTED | per evaluation | §9 |
| 14 | displacement | PROPOSED → ACTIVE → CONSUMED | TF of candles | §2.1 / §4.2E |
| 15 | confidence_and_abstention | computed per interpretation (not a lifecycle object) | per interpretation | §17 |
| 16 | future_data_cutoff | fixed at decision time | per TF | §2.3 |

### Note on `confidence_and_abstention`

This is a *decomposition*, not a structural object. The programme's "every concept" field set (candidate_generation_rules etc.) applies to structural objects with a lifecycle on price. The confidence layer has the 6 axes, 5 calibrated categories, and the abstention rule — all of which are specified in the YAML and ground the system in section 17 of the programme. It is correctly defined without those four lifecycle-style fields.

---

## The 14 contested decisions — you adjudicate these

Each line below is what I (the AI) propose as a default. None of it is authoritative yet. Every row carries the alternatives the YAML records. **Pick for each one.** The `decision_log.md` companion records your choice and version-bumps the doctrine.

| # | Decision | Proposed default | Live alternatives |
|---|---|---|---|
| 1 | **wick vs body close** | BODY_CLOSE_REQUIRED_FOR_EXTERNAL_BREAK | wick-alone sufficient / wick-OK-for-sweep-body-for-break / wick-alone |
| 2 | **minimum penetration** | ATR_NORMALISED_0_25_ATR | fixed-tick / 1-bar-body-beyond / no-minimum |
| 3 | **displacement role** | DISPLACEMENT_REQUIRED_FOR_EXTERNAL_BREAK | grades-only / range-only / not-used |
| 4 | **first break behaviour** | FIRST_BREAK_REQUIRES_CONFIRMATION_WINDOW | instant-external / probe-then-break |
| 5 | **external swing ownership** | STRUCTURAL_ROLE_AND_TIMEFRAME | timeframe-only / causal-only / majority-vote-of-generators |
| 6 | **protected-point selection** | CAUSAL_ORIGIN_OF_IMPULSE_OR_CLUSTER | latest-confirmed-opposing-pivot (current bug) / runner-up / multiple-per-TF |
| 7 | **CHoCH vs MSS** | MSS_EQUALS_CHoCH_AT_INTERNAL_SCOPE | distinct / MSS-external-CHoCH-internal / MSS-primary |
| 8 | **sweep confirmation horizon** | MULTI_HORIZON_STATE_MACHINE | fixed-N / immediate-next-bar / reclaim-by-HTF-close |
| 9 | **range replacement** | REPLACE_ON_ANY_OF_FOUR_TRIGGERS | protected-invalidation-only / terminal-extension-only / never |
| 10 | **OB candle vs cluster** | CLUSTER_WITH_INTERNAL_PIVOT | single-candle (current bug) / cluster-no-pivot / both-emitted |
| 11 | **POI ranking** | THREE_SEPARATE_SCORES_PLUS_COMBINED | deterministic-only / AI-only / learned-weighting |
| 12 | **inducement criteria** | FIVE_NECESSARY_CONDITIONS_ALL_REQUIRED | visible-only / shallow-only / no-formal |
| 13 | **abstention threshold** | ABSTAIN_WHEN_AMBIGUOUS_OR_CONTRADICTED | never-abstain / insufficient-context-only / at-confidence-floor |
| 14 | **evidence ID required** | YES_ALL_CLAIMS | trades-only / narrative-may-be-free |

---

## Where this Constitution will go (consumers)

- **Multi-scale candidate atlas** (§2): each generator must emit candidates that satisfy the "required_evidence" fields of each concept.
- **Reconciler role**: rejects candidates whose evidence IDs don't ground; records rejected alternatives; emits the structured selection the doctrine prescribes.
- **Protected-point state machine**: implements doctrine §5 candidate-generation and selection rules; no shortcut to "latest confirmed opposing pivot."
- **Sweep/breakout lifecycle**: implements doctrine §6 multi-horizon states.
- **Active-range state machine**: implements doctrine §7 four replacement triggers + hierarchy.
- **POI ranker**: emits the three separate scores the doctrine requires; refuses to collapse them.
- **Inducement**: implements the five-condition gate; can never emit a label without a defined rejection event.
- **Confidence / abstention**: implements the 6 axes × 5 categories × abstention_rule.
- **Deterministic validators**: implement the "required_evidence" enforcement for every concept.

---

## What this Constitution deliberately does NOT contain

- No implementation timings, tolerances, or weights beyond what the contested decisions flag for your adjudication. Those go in a sibling config once you decide.
- No code. Doctrine is doctrine; code is code. They are versioned and hashed separately.
- No empirical calibration. The empirical POI score is null until outcomes exist (per §8.3, §24).
- No trade authority. Every "trade" object remains blocked (per §19, §27, the safety boundary).
- No silent resolution of contested decisions. Every proposal is marked PROPOSED until you act.

---

## How to adjudicate

For each of the 14 contested decisions, you have three options:

1. **APPROVE the proposed default** — the doctrine clause becomes authoritative for that decision.
2. **APPROVE an alternative** — specify which alternative and any quantitative value (e.g., "0.25 ATR").
3. **DEFER** — leave the decision PROPOSED; the system abstains whenever that decision matters.

All three are recorded in `foundation_programme/pre_outputs/08_constitution_adjudication.md` (the decision log). Every change version-bumps the doctrine and regenerates the SHA-256.

Until then, the Constitution is the canonical doctrine for a system that **must not** emit a CERTIFIED perception.
