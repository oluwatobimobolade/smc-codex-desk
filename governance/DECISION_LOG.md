# Decision Log

## 2026-06-25 - Establish Governance Foundation

Decision: Treat the two PDFs in `/Users/tobimobolade/Downloads/` as the current
project-level plan: the Market Colleague constitution above all, and the Master
Strategy Truth Audit as the strategy/repository consolidation directive beneath
it.

Consequences:

- Create governance files before further feature expansion.
- Treat live execution and predictive deployment as disabled.
- Create one active strategy research candidate, RASC-SMC-V1.
- Preserve old strategy material until repository authority audit and
  archive-first cleanup are complete.

Evidence:

- `/Users/tobimobolade/Downloads/SMC Codex Desk.pdf`
- `/Users/tobimobolade/Downloads/Master Strategy Truth Audit.pdf`

## 2026-06-25 - Make PerceptionEngineV2 The Colleague Package Authority

Decision: Create `smc_desk/colleague/` as the initial market-colleague
orchestrator and make `PerceptionEngineV2` the primary perception source in
analysis run packages. Keep the legacy engine only as comparison evidence.

Consequences:

- `tools/run_market_colleague_case.py` delegates to the colleague orchestrator.
- New runs write `analysis_runs/<run_id>/` instead of older ad hoc case folders.
- Prediction, paper execution, and live execution remain disabled.
- The next gate is verified Kimi/TradingView chart-state alignment, not live
  signal promotion.

Evidence:

- `smc_desk/colleague/orchestrator.py`
- `analysis_runs/BTCUSDT_20260619_2345_wp0002_smoke/run_manifest.json`
- `governance/WORK_PACKAGES/WP-0002-COLLEAGUE-ORCHESTRATOR/TEST_REPORT.json`

## 2026-06-25 - Enforce Strict TradingView Alignment And Richer Scenario Graph

Decision: Add a strict TradingView/WebBridge alignment report and upgrade the
MTF scenario graph from simple counts to a richer market-story graph.

Consequences:

- Screenshot-only TradingView manifests now attach as evidence but fail strict
  alignment.
- Wrong TradingView symbols force `SOURCE_MISMATCH` in the decision file.
- Correct manifests must prove symbol, exchange, instrument, all timeframes,
  candle type, linear scale, timezone, and last closed candle per timeframe.
- Scenario packages now include timeframe context nodes, latest structure
  signals, active FVG nodes, selected HTF POI, execution blockers, and
  alternative scenarios.

Evidence:

- `smc_desk/colleague/tradingview_alignment.py`
- `smc_desk/colleague/decision_summary.py`
- `analysis_runs/BTCUSDT_20260619_2345_wp0003_wp0004_smoke/`
- `tests/test_market_colleague_case.py`

## 2026-06-25 - Build Live Alignment, Semantic Memory, And Outcome Spine

Decision: Extend the colleague package with a real WebBridge alignment manifest
builder, conservative SMC semantic candidates, deterministic similar-case
retrieval, and pending outcome contracts.

Consequences:

- `tools/build_tradingview_alignment_manifest.py` can open TradingView through
  Kimi WebBridge, capture screenshots, fetch TradingView OHLCV, and write a
  strict manifest.
- A live BTCUSDT package passed TradingView alignment using real WebBridge
  evidence.
- Semantic graph nodes now include liquidity pool candidates, inducement
  candidates, order-block proxies, and breaker candidates, all marked as
  candidate/proxy evidence.
- Similar cases are retrieved as research context only.
- Outcome contracts are registered but unresolved until future candles are
  evaluated.

Evidence:

- `analysis_runs/BTCUSDT_live_tv_alignment_20260625/tradingview_alignment_manifest.json`
- `analysis_runs/BTCUSDT_live_tv_aligned_colleague_20260625/`
- `smc_desk/colleague/smc_semantics.py`
- `smc_desk/colleague/similar_cases.py`
- `smc_desk/colleague/outcome_logging.py`

## 2026-06-25 - Replicate Live Shadow Across The Crypto Universe

Decision: Add a multi-symbol live shadow runner that repeats TradingView
capture, strict alignment, colleague package generation, graph creation, and
pending outcome registration across ETHUSDT, SOLUSDT, XRPUSDT, and BNBUSDT.

Consequences:

- The live workflow is no longer BTC-only.
- Every symbol can fail or pass independently, so one flaky capture cannot hide
  the rest of the universe.
- Execution remains disabled; live shadow is observe/log only.

Evidence:

- `smc_desk/colleague/live_shadow.py`
- `tools/run_live_shadow_universe.py`
- `analysis_runs/live_shadow_universe_20260625_eth_sol_xrp_bnb/summary.json`
- `governance/WORK_PACKAGES/WP-0009-LIVE-SHADOW-UNIVERSE/TEST_REPORT.json`

## 2026-06-25 - Resolve Outcome Contracts From Future Candles

Decision: Add a deterministic future-candle outcome resolver for colleague
pending contracts. Non-execute decisions are resolved as observations, never as
trade wins or losses.

Consequences:

- `outcome/resolution.json` can now be filled when enough future 15m candles are
  available.
- Same-candle target/invalidation touches are marked ambiguous instead of being
  guessed.
- No setup, watch, and source-mismatch cases remain no-trade observations.

Evidence:

- `smc_desk/colleague/outcome_resolution.py`
- `tools/resolve_colleague_outcome.py`
- `analysis_runs/BTCUSDT_20260618_1200_outcome_resolution_smoke/outcome/resolution.json`
- `governance/WORK_PACKAGES/WP-0010-OUTCOME-RESOLUTION/TEST_REPORT.json`

## 2026-06-26 - Repair Closed-Candle Availability Contract

Decision: Treat colleague `decision_time` as analysis availability time, not
last-closed candle open time. Live TradingView manifests must pass the last
closed 15m candle close time into colleague runs.

Consequences:

- A candle can enter confirmed history only when its scheduled close time is at
  or before the analysis time.
- Live-shadow no longer drifts one candle backward under the stricter
  truth-boundary slicer.
- Structure-break objects now have one canonical ontology shape with
  `break_type`, allowing the canonical event-ledger prototype to validate.
- This restores tests but does not change execution authority.

Evidence:

- `smc_desk/colleague/live_shadow.py`
- `smc_desk/perception/ontology.py`
- `smc_desk/perception/structure.py`
- `smc_desk/colleague/event_ledger.py`
- `governance/WORK_PACKAGES/WP-0011-TRUTH-BOUNDARY-REPAIR/TEST_REPORT.json`

## 2026-06-26 - Remove Legacy Engine From Current Decision Authority

Decision: Keep the legacy SMC engine as optional comparison evidence, but stop
using its trade plan to build current colleague decisions and scenarios.

Consequences:

- `scenarios/decision.json` is based on PerceptionEngineV2 plus MTF context.
- `scenarios/scenario_tree.json` no longer imports legacy targets, invalidation,
  or action state.
- `tools/run_market_colleague_case.py --no-legacy-comparison` builds a complete
  package without calling the legacy engine.
- Legacy output remains available under `legacy_comparison/` when explicitly
  enabled, but is not decision authority.
- Paper/live execution remains disabled and no market edge is claimed.

Evidence:

- `smc_desk/colleague/decision_summary.py`
- `smc_desk/colleague/orchestrator.py`
- `tests/test_market_colleague_case.py`
- `analysis_runs/BTCUSDT_20260619_2345_wp0012_no_legacy_smoke/run_manifest.json`
- `governance/WORK_PACKAGES/WP-0012-LEGACY-AUTHORITY-ISOLATION/TEST_REPORT.json`

## 2026-06-26 - Build Resolved Observation Cohort

Decision: Build WP-0013 as a resolved local observation cohort, not a
performance backtest.

Consequences:

- 50 colleague packages were built and resolved across BTCUSDT, ETHUSDT,
  SOLUSDT, XRPUSDT, and BNBUSDT.
- All 50 were `NO_SETUP`, so the cohort proves outcome plumbing only.
- No win rate, profit factor, expected value, or edge claim is allowed from this
  cohort.

Evidence:

- `tools/build_resolved_case_cohort.py`
- `analysis_runs/resolved_case_cohort_wp0013_20260626/summary.json`
- `governance/WORK_PACKAGES/WP-0013-RESOLVED-CASE-COHORT/TEST_REPORT.json`

## 2026-06-26 - Create Live-Shadow Human Review Queue

Decision: Convert aligned live-shadow WATCH/NO_SETUP cases into blind human
review packets while sealing engine context as non-gold evidence.

Consequences:

- Four review cases were created from ETHUSDT, SOLUSDT, XRPUSDT, and BNBUSDT.
- Each case has reviewer templates for `reviewer_a` and `reviewer_b`.
- Adjudication remains required before anything becomes gold truth.

Evidence:

- `tools/build_live_shadow_review_queue.py`
- `review_queues/live_shadow_wp0014_20260626/review_queue_manifest.json`
- `governance/WORK_PACKAGES/WP-0014-LIVE-SHADOW-HUMAN-REVIEW-LOOP/TEST_REPORT.json`

## 2026-06-26 - Split Ontology Authority Contracts Without Runtime Migration

Decision: Create separate target contracts for detector configuration and
strategy execution configuration, but leave runtime `RuleConfig` on the
monolith until a dedicated migration is implemented and tested.

Consequences:

- `PERCEPTION_DETECTOR_CONFIG_V2` is clean of risk/strategy fields.
- `STRATEGY_EXECUTION_CONFIG_V1` holds sequence/risk/decision parameters.
- `PERCEPTION_ONTOLOGY_V2` remains the runtime source for compatibility.
- Promotion is blocked until runtime migration and validation.

Evidence:

- `specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml`
- `specs/STRATEGY_EXECUTION_CONFIG_V1.yaml`
- `tools/audit_ontology_authority.py`
- `reports/current/ONTOLOGY_AUTHORITY_AUDIT_WP0015.json`
- `governance/WORK_PACKAGES/WP-0015-ONTOLOGY-AUTHORITY-SPLIT/TEST_REPORT.json`

## 2026-06-26 - Migrate Runtime Config To Split Contracts

Decision: Switch default runtime `RuleConfig` loading to the split detector and
strategy execution contracts while keeping compatibility adapters for old rule
files.

Consequences:

- Default runtime source is now `split_detector_strategy_configs`.
- `PERCEPTION_ONTOLOGY_V2.yaml` remains a legacy compatibility reference, not
  the default runtime authority.
- Older monolithic, detector-only, strategy-only, and legacy JSON configs still
  load through explicit compatibility modes.
- The migration does not create market edge, paper execution, or live execution
  authority.

Evidence:

- `smc_desk/rules.py`
- `tests/test_runtime_config_split.py`
- `reports/current/RUNTIME_CONFIG_SPLIT_WP0016.json`

## 2026-06-27 - Add End-To-End Market Colleague Gauntlet

Decision: Implement WP-0020 as a single observe-only gauntlet that loads
verified OHLCV, derives MTF packages, recreates clean charts, renders SMC
annotations with provenance, runs the cognitive colleague layer, preserves the
TradingView/Kimi visual-audit boundary, generates an evidence-linked thesis,
writes decision memory, and produces a final PASS/PARTIAL_PASS/FAIL report.

Consequences:

- `tools/run_wp0020_market_colleague_gauntlet.py` is the master operator entry
  point for the gauntlet.
- `smc_desk/colleague/wp0020_gauntlet.py` owns the orchestration and report
  format.
- The BTCUSDT CSV-backed run is a valid `PASS`: the OHLCV, charting,
  annotation, perception, cognitive, thesis, memory, and TradingView/Kimi
  screenshot-capture layers passed. TradingView remains visual audit only, and
  the manifest explicitly says candle-state timing was not independently read
  from the TradingView DOM.
- No strategy edge, paper execution, live execution, or capital-risk authority
  is created.

Evidence:

- `analysis_runs/WP0020_MARKET_COLLEAGUE_GAUNTLET_BTCUSDT/11_final_report/gauntlet_report.json`
- `governance/WORK_PACKAGES/WP-0020-MARKET-COLLEAGUE-GAUNTLET/TEST_REPORT.json`
- `reports/current/MARKET_COLLEAGUE_GAUNTLET_WP0020_REPORT.md`
- `governance/WORK_PACKAGES/WP-0016-RUNTIME-CONFIG-SPLIT/TEST_REPORT.json`

## 2026-06-26 - Refuse BTCUSDT Live Signal Without Verified OHLCV

Decision: Treat the BTCUSDT live run as visual-only evidence because verified
closed live OHLCV could not be acquired.

Consequences:

- No BTCUSDT live trade was produced.
- Kimi/TradingView screenshots were kept as visual context only.
- TradingView OHLCV timeout, Binance REST DNS failure, and browser-side fetch
  failure were recorded as operational evidence.
- The next work package must repair live OHLCV reliability instead of forcing
  analysis from screenshots.

Evidence:

- `analysis_runs/live_shadow_btcusdt_wp0016_20260626/summary.json`
- `analysis_runs/live_shadow_btcusdt_wp0016_20260626_retry/summary.json`
- `analysis_runs/live_btcusdt_wp0016_20260626/visual_only/screenshots/`
- `reports/current/BTCUSDT_LIVE_SHADOW_WP0016_REPORT.md`

## 2026-06-26 - Stop Strategy Expansion And Reconcile The Actual Baseline

Decision: Treat the other-AI/V4 transfer audit as a stop-the-line baseline
warning, repair the actual local blockers, and make the current local test
result the active validation truth.

Consequences:

- Fixed the FVG compile blocker and canonical FVG lifecycle defect.
- Fixed malformed duplicate-key governance in `NEXT_ACTIONS.yaml`.
- Added regression tests for both FVG terminal-state precedence and governance
  duplicate-key detection.
- Older 389/405/426/453 test-count records remain provenance only.
- The current active baseline is `469 passed, 1 skipped`; the working tree is
  still dirty and must be frozen or cleaned intentionally before release.

Evidence:

- `smc_desk/perception/fvg.py`
- `tests/stress_tests/test_C_minimal_pairs.py`
- `tests/test_governance_foundation.py`
- `governance/WORK_PACKAGES/WP-0017C-BASELINE-RECONCILIATION/TEST_REPORT.json`
- `reports/current/BASELINE_RECONCILIATION_WP0017C_REPORT.md`

## 2026-06-27 - Add Professional SMC Interpretation Layer

Decision: Add WP-0021 as a trader-story layer above raw PerceptionEngineV2
events. Raw BOS/CHoCH/FVG detection remains perception evidence; external bias,
internal retracement, timeframe role, POI watch state, and thesis language are
now derived by a separate professional SMC interpretation layer.

Consequences:

- A weak opposite break inside an active external range cannot flip external
  bias by itself.
- 15M is confirmation-only and cannot override 1H/4H external structure.
- The BTCUSDT 2026-06-27 case now resolves as 4H bearish, 1H bearish external,
  1H bullish internal retracement, `WATCH_BEARISH_RETRACE_TO_SUPPLY`, final
  action `NO_SIGNAL`.
- Aligned HTF hierarchy is not enough to become executable; watch states without
  lower-timeframe confirmation are gated back to `NO_SIGNAL`.
- The SMC thesis V2 writes trader-grade sections with evidence links.

Evidence:

- `smc_desk/perception/structure_hierarchy.py`
- `smc_desk/decision/watch_state_engine.py`
- `smc_desk/colleague/smc_thesis_v2.py`
- `tests/test_wp0021_professional_smc_interpretation.py`
- `analysis_runs/WP0021_BTCUSDT_INTERPRETATION_REPLAY_20260627/`
- `governance/WORK_PACKAGES/WP-0021-PROFESSIONAL-SMC-INTERPRETATION-REPAIR/TEST_REPORT.json`

## 2026-06-27 - Accept Parent Subordination Repair And Promote Detector Rebuild Next

Decision: Accept WP-0021A as the strict parent-subordination and authority
boundary cleanup, while treating the new strategy correctness audit as the
source of truth for the next detector rebuild.

Consequences:

- HTF-to-LTF hierarchy now carries parent context; a child timeframe opposing
  break cannot erase parent protected structure unless the confirmed body close
  breaches the parent protected level.
- `final_state` is now the trader-story headline and `final_action` remains the
  authority stamp.
- The WP-0020 gauntlet no longer imports the legacy `analyze_dataframe` engine
  directly; annotation-only legacy analysis goes through the comparison adapter.
- WP-0022 is redefined as Stage A/B SMC detector rebuild: internal break track,
  BOS-anchored CHoCH, swing prominence, coherent swing hierarchy, equal
  highs/lows, sweeps, order blocks, POI-grade FVGs, and inducement.
- WP-0023 holds the follow-on Stage C/D wiring: premium/discount enforcement,
  liquidity targets, valid dealing ranges, ATR threading, data depth, and
  story-renderer cleanup.

Evidence:

- `governance/WORK_PACKAGES/WP-0021A-PARENT-SUBORDINATION-AUTHORITY-CLEANUP/TEST_REPORT.json`
- `reports/current/PARENT_SUBORDINATION_AUTHORITY_CLEANUP_WP0021A_REPORT.md`
- `tools/check_authority_boundaries.py`
- `tests/decision/test_btc_supply_retrace_regression.py`

## 2026-06-27 - Implement Stage A/B SMC Detector Rebuild

Decision: Implement WP-0022 as an observe-only detector rebuild inside
PerceptionEngineV2, keeping execution authority disabled.

Consequences:

- `StructureDetector` now emits separate external and internal structure tracks.
- External CHoCH requires a protected-swing body close; internal CHoCH is timing
  evidence and cannot flip external bias.
- Swing evidence now carries scale and ATR-normalized prominence.
- PerceptionEngineV2 emits liquidity levels, sweeps, order blocks, inducements,
  and POI-grade FVGs.
- POI lifecycle prefers certified order blocks and POI-grade FVGs, with the old
  displacement-created POI kept only as fallback.
- Structure hierarchy ignores V2 internal breaks for external bias and is now
  temporally subordinated to the current parent leg, preventing stale child
  breaks from overriding a newer HTF leg.
- BTCUSDT replay returns `ALIGN`, `WATCH_BEARISH_RETRACE_TO_SUPPLY`, and
  `NO_SIGNAL`, matching the corrected manual-chart thesis while preserving
  observe-only authority.

Evidence:

- `tests/test_wp0022_smc_detector_rebuild.py`
- `governance/WORK_PACKAGES/WP-0022-SMC-DETECTOR-REBUILD-STAGE-AB/TEST_REPORT.json`
- `reports/current/SMC_DETECTOR_REBUILD_WP0022_REPORT.md`
- `analysis_runs/WP0022_BTCUSDT_DETECTOR_REBUILD_REPLAY_20260627/06_cognitive/final_colleague_output.json`

## 2026-06-29 - Implement WP-0038 AVAX/EURNZD Repair Pack

Decision: Accept the AVAXUSDT and EUR/NZD issue list as a correctness repair,
not a signal-generation request. Fix perception, chart evidence, forex routing,
validator downgrade safety, and honesty tooling while preserving observe-only
execution authority.

Consequences:

- Official annotation labels at the same price are now separated.
- Evidence packs can carry embedded chart-image bytes for local/vision providers.
- `ManualJSONProvider` is exported from `smc_desk.brain`.
- Session context uses the latest UTC day/current session only.
- Active-range authority prefers 4H before 1H and still rejects broad OHLCV summaries.
- Orchestrator v3 auto-runs PerceptionEngineV2 when candidates are absent.
- Direction vs active-range conflicts are validator warnings, visible in official output.
- Forex pairs get a separate depth profile and live route.
- Forex detector perception trims to the latest contiguous trading segment after session/weekend gaps; crypto gap guards remain strict.
- The conservative live provider no longer lets active-range direction silently override HTF consensus.
- Gold-readiness and trade-ready replay audits exist and explicitly refuse fake proof.
- Context-depth downgrades use the validator's shared trade-plan stripping path.

Evidence:

- `tests/test_wp0038_avax_eurnzd_repairs.py`
- `governance/WORK_PACKAGES/WP-0038-AVAX-EURNZD-REPAIR-PACK/TEST_REPORT.json`
- `governance/WORK_PACKAGES/WP-0038-AVAX-EURNZD-REPAIR-PACK/final_report.md`
- `analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260629_230022/`
- `analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260629_230943/EURNZD/`

## 2026-07-10 — WP-0044 Governance Reconciliation

Decision: close governance ambiguity before beginning the new expert structure
and annotation programme.

- `orchestrator_v3` is the canonical runtime; v1/v2 and the old dual-lens tool are comparison-only.
- Validation is append-only and bound to an exact commit or recorded worktree state.
- `latest_validation` is prohibited because it hid newer work behind WP-0022.
- The two controlling PDFs are registered by exact bytes and SHA-256.
- The companion repository is historical reference only.
- The preserved WP-0041A stash was restored and integrated with WP-0043; the stash remains as a recovery copy.
- The next approved programme is BR-001 through BR-006, not immediate detector redesign.

Authority remains research-only. No predictive or execution promotion is created.

## 2026-07-10 - Build The Perception Foundation Before SMC Semantics

Decision: do not tune BOS, CHoCH, protected structure, ranges, liquidity, or
POIs until market truth and experiment authority are independently sealed.

- Removed indirect legacy imports from the canonical path. Perception V2 now
  reads detector-only config; canonical context utilities use pure data modules.
- Certified every derived 1H/4H/1D bar against exact canonical 15m source rows.
- Made partial HTF candles, duplicate/out-of-order/missing rows, source mismatch,
  and future append leakage explicit test failures or exclusions.
- Defined AI as the semantic structure brain: it selects, relates, challenges,
  explains, and abstains. It cannot move levels, change candles, use future data,
  bypass graph invariants, or promote a trade.
- Sealed deterministic baseline runs with source, environment, data, authority,
  AI-role, result, and output hashes.
- Real BTCUSDT baseline reproduced with identical stable outputs.

BR-001 through BR-003 are a validated local foundation slice. The full bridge
gate remains closed pending protected benchmarks and independent human truth.

## 2026-07-10 - Make AI The Operating SMC Colleague, Not An Unchecked Authority

Decision: use AI as the principal interpreter and annotation planner for routine
SMC research, while deterministic market truth, certified geometry, formal graph
invariants, and blind benchmark access remain non-negotiable controls.

- AI handles clean-chart reading, candidate reconciliation, causal structure
  narrative, sparse annotation selection, and two separate downgrade-only
  critiques.
- Human review is not required for every daily analysis. It is reserved for
  later constitutional certification, disagreement study, and promotion of
  doctrine beyond AI weak consensus.
- Public development and annotation cases are usable immediately as AI weak
  labels. The blind benchmark remains inaccessible to training, tuning, prompt
  development, and case memory; it may open only for frozen final evaluation.
- The first source-grounded doctrine panel accepts only five conservative pilot
  rules. Displacement thresholds and deeper-order-block ranking stay explicit
  competing hypotheses rather than hidden code changes.
- The first BTCUSDT AI-assisted run used the clean 4H/1H charts and formal
  graph. It recognized the later 4H/1D bearish parent, treated the earlier 1H
  bullish move as stale recovery, selected two sparse marks, and produced no
  signal.

This creates a professional AI-first research system without confusing an AI
consensus, replay result, or test pass for human gold truth or market edge.

## 2026-07-11 - Require Rendered Proof Before AI Visual Approval

Decision: close the gap between semantic annotation planning and visual review.
The AI remains responsible for selecting the few SMC objects that tell the
market story, but deterministic evidence remains solely responsible for their
geometry. The visual critic may run only after the final images exist.

Consequences:

- Selected evidence IDs are resolved to price/time geometry through a certified
  bridge; unsupported, wick-only, unconfirmed, or timeframe-mismatched objects
  fail closed.
- The renderer produces sparse per-timeframe charts and proves each annotation
  against a clean baseline with object and pixel reconciliation.
- A visual PASS must cite the exact render-manifest hash and every annotated
  image hash. Reviewing `EXISTING_CHARTS_ONLY`, a missing render, or stale hashes
  cannot pass.
- The BTCUSDT proof contains only the controlling 4H CHoCH, its protected high,
  and an explicitly subordinate dashed 1H stale recovery. It remains
  `THESIS_ONLY`, with no trade box and no signal authority.

Evidence:

- `smc_desk/brain/structure_lab/annotation_bridge.py`
- `smc_desk/rendering/structure_lab_annotation_renderer.py`
- `tests/test_wp0041b_ai_annotation_render_loop.py`
- `analysis_runs/WP0041B_AI_ANNOTATION_RENDER_LOOP_BTCUSDT_20260711/`
- `governance/WORK_PACKAGES/WP-0041B-AI-ANNOTATION-RENDER-LOOP/TEST_REPORT.json`
