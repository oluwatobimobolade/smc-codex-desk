# Current Implementation Map

Recorded: 2026-07-12

## Source State

- Repository: `/Users/tobimobolade/smc-codex-desk`
- Commit: `4aa1a23173227430961f662442bf8d57ed2995d6`
- Branch: `wp-0012a-remove-legacy-authority`
- Working tree: dirty; user and prior-agent changes are preserved.
- Consequence: the canonical V2 source is the active baseline, but it is not an
  immutable baseline until the source manifest and dirty patch are archived.

## Canonical Observe-Only Runtime

```text
tools/run_live_ai_smc_full_system.py
  -> smc_desk.colleague.orchestrator_v3.run_ai_smc_orchestrator_v3
  -> smc_desk.perception.engine_v2.PerceptionEngineV2
  -> deterministic candidate/lifecycle enrichment
  -> smc_desk.brain.smc_evidence_pack_builder.build_smc_evidence_pack
  -> formal structure graph + causal POI authority
  -> AISMCTraderBrain
  -> consistency + annotation validators
  -> professional renderer + downgrade-only visual critic
  -> thesis and authority trace
```

`PerceptionEngineV2` remains the canonical candidate source. The formal graph,
causal POI authority, AI decision, and validators may downgrade or refuse; they
do not authorize paper or live execution.

## Experimental Research Runtime

```text
smc_desk.perception.programme_run.run_perception_programme
  -> multi-timeframe candidate atlas
  -> anchor-preserving context retrieval
  -> six-role structure laboratory
  -> semantic annotation bridge + deterministic geometry
  -> deterministic interpretation certification
```

This path is substantial but function-based. At this baseline there is no
public class named `HybridPerceptionEngineV3Experimental`; WP-SMC-01 records
that as a verified interface gap rather than pretending it exists.

## Exact Capability Map

| Concern | Current implementation | Runtime status |
|---|---|---|
| Candle truth/cutoff | `smc_desk.data.schemas.Candle`; `PerceptionEngineV2.analyze`; live harness closed-candle timestamps | canonical, deterministic |
| Swing detection | `smc_desk.perception.swings.SwingDetector`, `MultiScaleSwingDetector` | canonical V2 |
| Experimental swing candidates | `smc_desk.perception.candidates.atlas.build_for_timeframe/build_multi_timeframe`; fractal, prominence, directional-change, changepoint, displacement generators | experimental |
| Structure breaks | `smc_desk.perception.structure.StructureDetector` | canonical V2; known semantic gaps remain |
| Displacement scoring | `smc_desk.perception.displacement.score_break_displacement`; experimental candidate displacement generator | implemented but not a canonical V2 break-acceptance gate |
| Protected points | V2 `_StructureTrack`; experimental `smc_desk.structure.protected_point.generate_candidates/score_candidates/select` | dual implementations; experimental abstains on ambiguity |
| Sweep/liquidity | V2 `LiquidityLevelDetector`, `SweepDetector`; experimental `smc_desk.structure.level_interactions` | V2 candidate source plus experimental lifecycle |
| Active range | `smc_desk.structure.active_range` and `smc_desk.perception.formal_structure_graph` | experimental/formal authority; deterministic invariants |
| Order blocks | `smc_desk.perception.order_blocks.OrderBlockDetector` | canonical candidate generation; working tree contains causal-origin-cluster changes |
| FVG | `smc_desk.perception.fvg.FVGDetector`; lifecycle in POI enrichment | canonical candidate source |
| POI lifecycle | `smc_desk.perception.poi_lifecycle.build_poi_lifecycle_by_timeframe` | canonical enrichment |
| Causal POI selection | `smc_desk.perception.causal_poi_authority.build_causal_poi_authority` | observe-only authority; current untracked source |
| POI ranking | `smc_desk.structure.poi_ranker` and causal pairwise selection | experimental; empirical score explicitly absent |
| Inducement | V2 `smc_desk.perception.inducement.InducementDetector`; hypothesis state in `smc_desk.structure.inducement` | candidate plus experimental hypothesis |
| Formal MTF graph | `smc_desk.perception.formal_structure_graph.build_mtf_structure_graph` | canonical evidence authority, signal disabled |
| AI structure lab | `smc_desk.brain.structure_lab.runtime.run_structure_lab`; six strict role schemas | experimental governed runtime |
| Retrieval | `context_retriever.retrieve_for_case`; `RetrievalTools` | anchor-preserving retrieval active; bounded autonomous tool loop incomplete |
| Interpretation validators | `smc_desk.validation.validate_interpretation/certify_interpretation`; evidence, temporal, invariant, narrative checks | experimental fail-closed certification |
| AI decision validator | `smc_desk.brain.ai_smc_consistency_validator.validate_ai_smc_decision` | canonical V3 output gate |
| Annotation evidence | `smc_desk.brain.annotation_evidence.build_annotation_evidence_index` | deterministic geometry/evidence index |
| Annotation planning | `annotation_candidate_composer`; structure-lab semantic planner and bridge | canonical conservative composer plus experimental AI selection |
| Annotation validation | `annotation_plan_validator.validate_annotation_plan_v2` | canonical fail-closed |
| Annotation rendering | `smc_trader_annotation_renderer`; `structure_lab_annotation_renderer` | sparse local deterministic geometry |
| Visual criticism | `annotation_visual_critic`; structure-lab visual critic hash attestation | cleanup/downgrade only |
| Human gold | reviewer/adjudication/evaluation modules outside this map | scaffold exists; no sufficient blind adjudicated cohort |
| Prediction/execution | research scaffolds; authority matrix disables execution | out of scope and disabled |

## Authority Findings

1. Deterministic code owns prices, times, geometry, lifecycle facts, hashes,
   and hard invariants.
2. AI owns selection, contextual interpretation, alternatives, explanation,
   and semantic annotation choice.
3. Validators may reject or downgrade. Critics cannot promote.
4. The formal graph and causal POI authority are observe-only; their contracts
   do not grant a signal.
5. Kimi/TradingView screenshots are visual audit evidence, not market truth.
6. The current source proves implementation behavior only. It does not prove
   expert SMC accuracy, reaction certainty, predictive edge, or live readiness.

