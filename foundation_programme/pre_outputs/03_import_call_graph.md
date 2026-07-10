# SMC Codex Desk — Import / Call Graph (WP-0042 pre-output #3)
# Generated: 2026-07-10 against frozen baseline 554e499

## Three orchestrator generations

### smc_desk/colleague/orchestrator.py
SmcDesk internal imports:
10:from smc_desk.case_library import file_sha256
11:from smc_desk.colleague.analysis_package import AnalysisPackageWriter
12:from smc_desk.colleague.decision_summary import (
19:from smc_desk.colleague.request_contract import ColleagueRunRequest, TIMEFRAME_ORDER
20:from smc_desk.colleague.run_context import build_run_market_context, dataframe_to_candles
21:from smc_desk.colleague.tradingview_alignment import build_alignment_report
22:from smc_desk.colleague.outcome_logging import (
28:from smc_desk.colleague.similar_cases import retrieve_similar_cases
29:from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, assert_not_in_holdout
30:from smc_desk.mtf_current import build_mtf_graph
31:from smc_desk.perception.engine_v2 import PerceptionEngineV2
32:from smc_desk.render import render_raw_chart, render_smc_annotated
33:from smc_desk.rendering.mtf_mosaic import render_mtf_mosaic
34:from smc_desk.rules import RuleConfig
35:from smc_desk.colleague.thesis_builder import build_colleague_thesis


### smc_desk/colleague/orchestrator_v2.py
SmcDesk internal imports:
12:from smc_desk.colleague.decision_memory_graph import (
18:from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
19:from smc_desk.data.schemas import Candle
20:from smc_desk.data.truth_validator import MarketTruthReport, validate_market_truth
21:from smc_desk.decision.contradiction_resolver import (
25:from smc_desk.decision.execution_readiness import evaluate_execution_readiness
26:from smc_desk.decision.inducement_continuation_classifier import classify_inducement_continuation
27:from smc_desk.decision.refusal_engine import RefusalDecision, evaluate_refusal
28:from smc_desk.decision.timeframe_role_engine import assess_timeframe_roles
29:from smc_desk.decision.uncertainty_engine import UncertaintyAssessment, score_uncertainty
30:from smc_desk.decision.watch_state_engine import evaluate_watch_state
31:from smc_desk.perception.engine_v2 import PerceptionEngineV2
32:from smc_desk.perception.liquidity_sequence import build_liquidity_sequence_by_timeframe
33:from smc_desk.perception.poi_lifecycle import build_poi_lifecycle_by_timeframe
34:from smc_desk.perception.regime_engine import RegimeAssessment, classify_market_regime
35:from smc_desk.perception.structure_hierarchy import build_mtf_structure_hierarchy, hierarchy_timeframe_signals
36:from smc_desk.rules import RuleConfig, load_rule_config


### smc_desk/colleague/orchestrator_v3.py
SmcDesk internal imports:
16:from smc_desk.brain.ai_smc_consistency_validator import (
22:from smc_desk.brain.annotation_plan_validator import (
26:from smc_desk.brain.ai_smc_trader_brain import AISMCTraderBrain
27:from smc_desk.brain.llm_provider import AISMCProvider, LLMCompletionRequest, LLMCompletionResult
28:from smc_desk.brain.prompt_system import build_prompt_registry_manifest
29:from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
30:from smc_desk.colleague.run_context import TIMEFRAME_DURATIONS, dataframe_to_candles
31:from smc_desk.colleague.smc_thesis_ai_v1 import build_smc_thesis_ai_v1, render_smc_thesis_ai_v1_markdown
32:from smc_desk.data.historical_backfill import DEFAULT_MINIMUM_DEPTH, FOREX_MINIMUM_DEPTH, build_context_depth_report
33:from smc_desk.perception.engine_v2 import PerceptionEngineV2
34:from smc_desk.rendering.clean_mtf_chart_pack import render_clean_mtf_chart_pack
35:from smc_desk.rendering.smc_trader_annotation_renderer import render_smc_trader_annotation_chart
36:from smc_desk.perception.formal_structure_graph import (


## CLI tools and which orchestrator (if any) they invoke
[build_resolved_case_cohort.py] → 27:from smc_desk.colleague.orchestrator import run_colleague_analysis|
[run_chat_ai_brain.py] → 33:from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3|87:    result = run_ai_smc_orchestrator_v3(|
[run_colleague_brain_v2.py] → 14:from smc_desk.colleague.orchestrator_v2 import run_colleague_brain_v2|
[run_import_agent_response.py] → 42:from smc_desk.colleague.orchestrator_v3 import _status|
[run_live_ai_smc_full_system.py] → 25:from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3|58:            result = run_ai_smc_orchestrator_v3(|
[run_market_colleague_case.py] → 29:from smc_desk.colleague.orchestrator import run_colleague_analysis|
[run_wp0036_acceptance_gauntlet.py] → 22:from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3|101:        result = run_ai_smc_orchestrator_v3(|
[sync_market_data.py] → 2:"""Local-first market data orchestrator.|

## Active chain per CURRENT_STATE.yaml
Per governance/CURRENT_STATE.yaml:
33:  colleague_orchestrator: pev2_led_mtf_driven_wp0012d
35:  event_ledger: canonical_deterministic_replayable_wp0012c
37:  legacy_engine: isolated_comparison_only_no_active_authority_path_wp0012a_complete
180:    description: Live Binance OHLCV acquisition uses retry/backoff, route-health preflight, and excludes TradingView from canonical truth.
240:  - Do not treat WP-0020 TradingView screenshots as market truth; visual audit is available, but canonical OHLCV remains the Binance CSV source and TradingView candle timing was not DOM-verified.

## Authority boundary check (legacy engine reachability)
ACTIVE caller: smc_desk/colleague/wp0020_gauntlet.py
ACTIVE caller: smc_desk/colleague/__init__.py
ACTIVE caller: smc_desk/colleague/live_shadow.py
ACTIVE caller: smc_desk/gauntlet/wp0035_ai_brain_gauntlet.py
LEGACY import: smc_desk/__init__.py
LEGACY import: smc_desk/colleague/legacy_comparison.py
LEGACY import: smc_desk/colleague/run_context.py
LEGACY import: tools/build_render_examples.py
LEGACY import: tools/session_context.py
LEGACY import: tools/annotate_chart.py
LEGACY import: tools/generate_live_charts.py
LEGACY import: tools/generate_charts.py
LEGACY import: tools/build_perception_anchor.py
LEGACY import: tools/backtest_smc_elite.py
LEGACY import: tools/build_fusion_gold_set.py
LEGACY import: tools/build_smc_case.py
LEGACY import: tools/analyze_chart.py
LEGACY import: tools/build_research_dataset.py
LEGACY import: tools/detect_smc_zones.py
LEGACY import: tools/run_fifty_trade_audit.py
LEGACY import: tools/derive_htf_from_15m.py
LEGACY import: tools/perception_benchmark.py
LEGACY import: tools/build_perception_gold_batch.py
LEGACY import: tools/mark_chart.py
LEGACY import: tools/backtest_smc_elite_mtf.py
LEGACY import: tools/run_market_colleague_case.py
LEGACY import: tools/build_perception_pilot.py
LEGACY import: tools/replay_setup_states.py
LEGACY import: tools/analyze_live_dual_lens.py
LEGACY import: tools/build_trade_plan.py
LEGACY import: tools/generate_vision_training_data.py
LEGACY import: tools/compare_my_bias_vs_model.py

## AI brain module reachability
smc_desk/colleague/orchestrator_v3.py
smc_desk/brain/__init__.py
smc_desk/brain/annotation_plan_validator.py
smc_desk/brain/prompt_system/prompt_builder.py
smc_desk/brain/ai_smc_trader_brain.py
smc_desk/brain/ai_smc_consistency_validator.py
smc_desk/brain/agent_handoff/import_agent_response.py
smc_desk/gauntlet/wp0035_ai_brain_gauntlet.py
tools/run_wp0035_avaxusdt_stage2.py
tools/run_wp0036_acceptance_gauntlet.py
