"""Official AI SMC brain orchestrator.

V3 is the canonical authority for SMC Codex Desk as of WP-0043
(GATE-CANONICAL-RUNTIME-001). Every authoritative run must go through this
orchestrator (entry point: ``python -m smc_desk.colleague``). Legacy rule
authority is allowed only as debug comparison via
``smc_desk/colleague/legacy_comparison.py``.

The orchestrator is responsible for:

* building a completed-candle-only context;
* invoking PerceptionEngineV2 and the formal structure graph (WP-0040);
* constructing the AI SMC trader brain evidence pack;
* running the consistency validator and annotation validator;
* writing the ``authority_trace.json`` alongside other run artefacts;
* refusing any decision that violates authority boundaries.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import (
    ValidationIssue,
    ValidationResult,
    strip_trade_plan_for_review,
    validate_ai_smc_decision,
)
from smc_desk.brain.annotation_plan_validator import (
    annotation_validation_to_dict,
    validate_annotation_plan_v2,
)
from smc_desk.brain.ai_smc_trader_brain import AISMCTraderBrain, OFFICIAL_STATES
from smc_desk.brain.llm_provider import AISMCProvider, LLMCompletionRequest, LLMCompletionResult
from smc_desk.brain.prompt_system import build_prompt_registry_manifest
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.colleague.__main__ import build_authority_trace, write_authority_trace
from smc_desk.colleague.run_context import (
    TIMEFRAME_DURATIONS,
    _is_expected_closure,
    _tz_aware,
    dataframe_to_candles,
)
from smc_desk.colleague.smc_thesis_ai_v1 import build_smc_thesis_ai_v1, render_smc_thesis_ai_v1_markdown
from smc_desk.data.historical_backfill import DEFAULT_MINIMUM_DEPTH, FOREX_MINIMUM_DEPTH, build_context_depth_report
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.perception.poi_lifecycle import build_poi_lifecycle_by_timeframe
from smc_desk.perception.structure_hierarchy import build_mtf_structure_hierarchy
from smc_desk.rendering.clean_mtf_chart_pack import render_clean_mtf_chart_pack
from smc_desk.rendering.smc_trader_annotation_renderer import render_smc_trader_annotation_chart
from smc_desk.rendering.bitmap_annotation_review import review_rendered_annotation_bitmap
from smc_desk.rendering.native_mtf_story_pack import render_native_mtf_story_pack
from smc_desk.evaluation.perception_interrogation import (
    calibration_report,
    certification_verdict,
    evaluate_runtime_causal_integrity,
    freeze_poi_ranking,
    generate_chart_perturbations,
    load_adjudicated_evaluation_inputs,
    load_external_validation_readiness,
)
from smc_desk.perception.formal_structure_graph import (
    graph_invariant_violation_codes,
    graph_requires_thesis_only,
    graph_requires_mixed_bias,
    graph_thesis_sentence,
    graph_to_dict_string,
)
from smc_desk.perception.formal_causal_episode_graph import episode_graph_failure_codes
from smc_desk.perception.evidence_contract import contract_ids_for_object


OFFICIAL_AI_SOURCE = "AISMCTraderBrainValidated"
LEGACY_DEBUG_ROLE = "DEBUG_LEGACY_COMPARISON_ONLY"


@dataclass(frozen=True)
class AISMCOrchestratorV3Result:
    output_dir: Path
    status: str
    report: dict[str, Any]
    validation_result: ValidationResult
    provider_result: LLMCompletionResult

    def to_dict(self) -> dict[str, Any]:
        return self.report


def run_ai_smc_orchestrator_v3(
    *,
    symbol: str,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    provider: AISMCProvider | None,
    output_dir: str | Path,
    detector_candidates: Mapping[str, Any] | None = None,
    session_context: Mapping[str, Any] | None = None,
    include_5m: bool = False,
    enforce_minimum_depth: bool = True,
    render_charts: bool = True,
    daily_session_profile: str = "exchange_daily_utc",
) -> AISMCOrchestratorV3Result:
    if provider is None:
        raise ValueError("A real or explicit stub AI SMC provider must be injected; no implicit provider is allowed.")
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    max_candles = 120
    loop_count = 0
    while loop_count < 2:
        loop_count += 1
        
        depth_profile = _select_depth_profile(symbol)
        depth_report = build_context_depth_report(timeframe_dfs, minimum_depths=depth_profile)
        detector_candidates_payload: Mapping[str, Any]
        perception_report: dict[str, Any]
        if detector_candidates is None:
            detector_candidates_payload, perception_report = _run_perception_candidates(symbol=symbol, timeframe_dfs=timeframe_dfs)
        else:
            detector_candidates_payload = detector_candidates
            perception_report = {"source": "caller_supplied_detector_candidates", "auto_perception_ran": False}
        detector_candidates_payload, poi_report = _enrich_detector_candidates_with_pois(
            detector_candidates_payload,
            timeframe_dfs=timeframe_dfs,
        )
        perception_report["poi_lifecycle"] = poi_report
        
        chart_pack = render_clean_mtf_chart_pack(
            timeframe_dfs,
            root / f"09_clean_mtf_chart_pack_run_{loop_count}",
            symbol=symbol,
            include_5m=include_5m,
        )
        context = {
            **dict(session_context or {}),
            "context_depth_report": depth_report,
            "context_depth_warning": any(item["context_depth_warning"] for item in depth_report.values()),
            "context_depth_profile": depth_profile,
            "perception_candidates": perception_report,
        }

        evidence_pack = build_smc_evidence_pack(
            symbol=symbol,
            timeframe_dfs=timeframe_dfs,
            chart_images=chart_pack["chart_paths"],
            detector_candidates=detector_candidates_payload,
            session_context=context,
            embed_images=True,
            daily_session_profile=daily_session_profile,
            max_candles_per_timeframe=max_candles,
        )
        
        # Write files for tracking
        if loop_count == 1:
            # Maintain compatibility with standard path
            _write_json(root / "10_smc_evidence_pack" / "evidence_pack.json", evidence_pack)
        _write_json(root / f"10_smc_evidence_pack_run_{loop_count}" / "evidence_pack.json", evidence_pack)

        provider_result_box: dict[str, LLMCompletionResult] = {}

        def _completion_fn(prompt: str) -> str | Mapping[str, Any]:
            request = LLMCompletionRequest(
                prompt=prompt,
                evidence_pack=evidence_pack,
                chart_images=evidence_pack.get("chart_images", {}),
            )
            provider_result = provider.complete(request)
            provider_result_box["result"] = provider_result
            return provider_result.raw_json

        brain = AISMCTraderBrain(_completion_fn)
        decision = brain.decide(evidence_pack)
        provider_result = provider_result_box["result"]
        validation_result = validate_ai_smc_decision(decision, evidence_pack)
        if enforce_minimum_depth and context["context_depth_warning"]:
            validation_result = _downgrade_for_depth(validation_result, depth_report)

        # AI Critic Pass
        from smc_desk.brain.prompt_system import build_critic_prompt
        critic_prompt = build_critic_prompt(decision.model_dump(mode="json", by_alias=True), evidence_pack)
        critic_request = LLMCompletionRequest(
            prompt=critic_prompt,
            evidence_pack=evidence_pack,
            chart_images=evidence_pack.get("chart_images", {}),
        )
        critic_result = provider.complete(critic_request)
        critic_data = {}
        if isinstance(critic_result.raw_json, Mapping):
            critic_data = dict(critic_result.raw_json)
        elif isinstance(critic_result.raw_json, str):
            try:
                import json as json_lib
                critic_data = json_lib.loads(critic_result.raw_json)
            except Exception:
                pass

        if critic_data.get("veto") or critic_data.get("suggested_downgrade_state") == "REVIEW_REQUIRED":
            from smc_desk.brain.ai_smc_consistency_validator import ValidationIssue
            critic_issue = ValidationIssue(
                code="critic_veto",
                severity="hard",
                message=critic_data.get("critique") or "AI Critic vetoed the proposed decision."
            )
            issues = [*validation_result.issues, critic_issue]
            from smc_desk.brain.ai_smc_consistency_validator import strip_trade_plan_for_review, ValidationResult
            import json as json_lib
            official = strip_trade_plan_for_review(json_lib.loads(json_lib.dumps(validation_result.official_decision, default=str)), issues)
            validation_result = ValidationResult(
                status="REVIEW_REQUIRED",
                decision=validation_result.decision,
                official_decision=official,
                issues=issues,
                smc_model_validity="valid",
                trade_plan_validity="failed"
            )

        # Check for context/bounds warnings to trigger Request-More-Context loop
        has_context_issue = any(
            issue.code in {"context_depth_warning", "active_range_invalid_bounds", "active_range_too_wide"}
            for issue in validation_result.issues
        )
        
        if has_context_issue and loop_count == 1:
            max_candles = 240
            continue
        else:
            break

    official_decision = validation_result.official_decision
    formal_graph = evidence_pack.get("formal_structure_graph") or {}
    causal_episode_graph = evidence_pack.get("formal_causal_episode_graph") or {}
    structure_engine_v3_shadow = evidence_pack.get("structure_engine_v3_shadow") or {}
    causal_poi_authority = evidence_pack.get("causal_poi_authority") or {}
    _write_json(root / "11_ai_smc_trader_brain" / "provider_audit.json", provider_result.audit_record())
    _write_json(root / "11_ai_smc_trader_brain" / "raw_decision.json", decision.model_dump(mode="json", by_alias=True))
    _write_json(root / "12_ai_consistency_validation" / "validation_result.json", validation_result.model_dump(mode="json", by_alias=True))
    _write_json(root / "12_ai_consistency_validation" / "loop_trace.json", {
        "final_loop_count": loop_count,
        "max_candles_used": max_candles,
        "has_context_issue_run_1": has_context_issue if loop_count > 1 else False,
        "critic_pass_metadata": critic_data
    })
    _write_json(root / "13_official_ai_decision" / "official_decision.json", official_decision)

    official_chart_path = None
    chart_manifest: dict[str, Any] = {"status": "disabled"}
    bitmap_review: dict[str, Any] = {"overall_status": "NOT_RENDERED"}
    semantic_image_review: dict[str, Any] = {"status": "NOT_RENDERED"}
    native_mtf_manifest: dict[str, Any] = {"status": "NOT_RENDERED"}
    perturbation_manifest: dict[str, Any] = {"status": "NOT_RENDERED"}
    if render_charts:
        official_chart_path = root / "14_clean_annotation_render" / f"{symbol}_official_ai_annotation.png"
        evidence_rows = len((evidence_pack.get("ohlcv_windows") or {}).get("15m") or []) or None
        official_chart_df = _chart_df(timeframe_dfs, tail_rows=evidence_rows)
        scene = render_smc_trader_annotation_chart(
            official_chart_df,
            validation_result,
            official_chart_path,
            timeframe="15m",
        )
        visual_review = scene.get("visual_critic") or {
            "schema": "professional_smc_annotation_visual_review_v1",
            "status": "NOT_AVAILABLE",
            "critic_authority": "downgrade_or_cleanup_only",
            "issues": [],
        }
        reviewed_result = apply_visual_critic_authority(validation_result, visual_review)
        if reviewed_result.status != validation_result.status:
            validation_result = reviewed_result
            official_decision = validation_result.official_decision
            _write_json(root / "12_ai_consistency_validation" / "validation_result.json", validation_result.model_dump(mode="json", by_alias=True))
            _write_json(root / "13_official_ai_decision" / "official_decision.json", official_decision)
            scene = render_smc_trader_annotation_chart(
                official_chart_df,
                validation_result,
                official_chart_path,
                timeframe="15m",
            )
            visual_review = scene.get("visual_critic") or visual_review
        semantic_image_review = _run_post_render_semantic_image_review(
            provider=provider,
            initial_provider_result=provider_result,
            evidence_pack=evidence_pack,
            image_path=official_chart_path,
            scene=scene,
        )
        if semantic_image_review.get("status") == "REVIEW_REQUIRED":
            semantic_visual_review = {
                "status": "REVIEW_REQUIRED",
                "issues": semantic_image_review.get("issues") or [
                    {"message": "Post-render semantic image review required a downgrade."}
                ],
            }
            reviewed_result = apply_visual_critic_authority(validation_result, semantic_visual_review)
            if reviewed_result.status != validation_result.status:
                validation_result = reviewed_result
                official_decision = validation_result.official_decision
                _write_json(root / "12_ai_consistency_validation" / "validation_result.json", validation_result.model_dump(mode="json", by_alias=True))
                _write_json(root / "13_official_ai_decision" / "official_decision.json", official_decision)
                scene = render_smc_trader_annotation_chart(
                    official_chart_df,
                    validation_result,
                    official_chart_path,
                    timeframe="15m",
                )
                visual_review = scene.get("visual_critic") or visual_review
        bitmap_review = review_rendered_annotation_bitmap(
            official_chart_path,
            scene=scene,
            semantic_review_status=str(semantic_image_review.get("status") or "NOT_PERFORMED_NO_VISION_PROVIDER"),
        )
        chart_manifest = {
            "status": (
                "REVIEW_REQUIRED"
                if visual_review.get("status") == "REVIEW_REQUIRED"
                or bitmap_review.get("deterministic_bitmap_status") != "PASS"
                or semantic_image_review.get("status") == "REVIEW_REQUIRED"
                else "PASS_WITH_SEMANTIC_REVIEW_PENDING"
                if semantic_image_review.get("status") == "NOT_PERFORMED_NO_VISION_PROVIDER"
                else "PASS"
            ),
            "chart_path": str(official_chart_path),
            "scene": scene,
            "source": "validated_ai_annotation_plan",
            "bitmap_review": bitmap_review,
            "semantic_image_review": semantic_image_review,
        }
        _write_json(root / "14_clean_annotation_render" / "annotation_manifest.json", chart_manifest)
        _write_json(root / "14_clean_annotation_render" / "annotation_visual_review.json", visual_review)
        _write_json(root / "14_clean_annotation_render" / "annotation_bitmap_review.json", bitmap_review)
        _write_json(root / "14_clean_annotation_render" / "annotation_semantic_image_review.json", semantic_image_review)
        annotation_validation = validate_annotation_plan_v2(validation_result.decision, evidence_pack)
        annotation_validation_payload = annotation_validation_to_dict(annotation_validation)
        _write_json(root / "14_clean_annotation_render" / "annotation_validation.json", annotation_validation_payload)
        _write_json(
            root / "14_clean_annotation_render" / "annotation_plan_v2.json",
            official_decision.get("annotation_plan_v2") or {
                "schema": "professional_smc_annotation_plan_v2",
                "style": "professional_smc_sparse",
                "objects": [],
                "notes": ["No annotation_plan_v2 was supplied; renderer used legacy annotation_plan."],
            },
        )
        _write_text(
            root / "14_clean_annotation_render" / "annotation_self_review.md",
            _annotation_self_review_markdown(
                scene=scene,
                validation=annotation_validation_payload,
                visual_review=visual_review,
                official_state=str(official_decision.get("official_state")),
            ),
        )
        native_mtf_manifest = render_native_mtf_story_pack(
            timeframe_dfs=timeframe_dfs,
            evidence_pack=evidence_pack,
            validation_result=validation_result,
            output_dir=root / "14_clean_annotation_render" / "native_mtf_story_pack",
            semantic_review_status="NOT_PERFORMED_NO_VISION_PROVIDER",
        )
        perturbation_manifest = generate_chart_perturbations(
            official_chart_path,
            root / "17_perception_interrogation" / "chart_perturbations",
        )
        _write_json(
            root / "17_perception_interrogation" / "chart_perturbation_manifest.json",
            perturbation_manifest,
        )

    thesis = build_smc_thesis_ai_v1(validation_result=validation_result, evidence_pack=evidence_pack)
    _write_json(root / "15_ai_thesis" / "thesis.json", thesis)
    _write_text(root / "15_ai_thesis" / "thesis.md", render_smc_thesis_ai_v1_markdown(thesis))

    _write_json(root / "16_formal_structure_graph" / "structure_graph.json", formal_graph)
    _write_json(root / "16_formal_structure_graph" / "structure_engine_v3_shadow.json", structure_engine_v3_shadow)
    _write_json(root / "16_formal_structure_graph" / "causal_episode_graph_v2.json", causal_episode_graph)
    _write_text(
        root / "16_formal_structure_graph" / "causal_episode_story.md",
        _causal_episode_story_markdown(causal_episode_graph),
    )
    _write_json(root / "16_formal_structure_graph" / "causal_poi_authority.json", causal_poi_authority)
    _render_structure_map(timeframe_dfs, formal_graph, root / "16_formal_structure_graph" / "structure_map.png", symbol=symbol)

    contract_registry = evidence_pack.get("object_evidence_contracts") or {}
    _write_json(root / "17_perception_interrogation" / "object_evidence_contracts.json", contract_registry)
    poi_freeze = _freeze_current_poi_ranking(evidence_pack)
    _write_json(root / "17_perception_interrogation" / "poi_ranking_freeze.json", poi_freeze)
    evaluation_inputs = load_adjudicated_evaluation_inputs(
        Path(__file__).resolve().parents[2] / "data" / "gold_sets" / "ai_smc"
    )
    _write_json(root / "17_perception_interrogation" / "evaluation_input_readiness.json", evaluation_inputs)
    external_validation = load_external_validation_readiness(
        Path(__file__).resolve().parents[2] / "data" / "gold_sets" / "ai_smc" / "validation",
        adjudicated_case_ids=evaluation_inputs["adjudicated_case_ids"],
        minimum_adjudicated_cases=30,
    )
    _write_json(root / "17_perception_interrogation" / "external_validation_readiness.json", external_validation)
    causal_integrity = evaluate_runtime_causal_integrity(
        object_evidence_contracts=contract_registry,
        ohlcv_windows=evidence_pack.get("ohlcv_windows") or {},
        decision_time=str(contract_registry.get("decision_time")),
    )
    _write_json(root / "17_perception_interrogation" / "runtime_causal_integrity.json", causal_integrity)
    calibration = calibration_report(evaluation_inputs["calibration_records"], minimum_records=50)
    _write_json(root / "17_perception_interrogation" / "calibration_readiness.json", calibration)
    annotation_contract_passed = bool(
        official_decision.get("annotation_plan_v2")
        and not any(
            issue.code.startswith("annotation_v2_")
            for issue in validation_result.issues
            if issue.severity == "hard"
        )
    )
    evidence_grounding_failed = any(
        any(
            token in issue.code
            for token in ("unmatched", "missing_evidence", "unresolved_evidence", "price_mismatch", "invented")
        )
        for issue in validation_result.issues
        if issue.severity == "hard"
    )
    blind_cohort = external_validation["blind_cohort_score"]
    certification = certification_verdict(
        catastrophic_gates={
            "future_leakage": causal_integrity.get("status") == "PASS",
            "invented_levels": not evidence_grounding_failed,
            "evidence_contract_identity": not bool(contract_registry.get("duplicate_contract_ids")),
            "internal_external_hierarchy": formal_graph.get("invariants", {}).get("status") == "PASS",
            "ltf_cannot_flip_htf": not graph_requires_mixed_bias(formal_graph) or official_decision.get("direction") == "mixed",
            "wick_is_not_close_bos": any(
                check.get("code") == "wick_probes_are_not_breaks" and check.get("passed") is True
                for check in formal_graph.get("invariants", {}).get("checks", [])
            ),
            "annotation_coordinate_integrity": annotation_contract_passed,
            "poi_future_reaction_excluded": poi_freeze.get("status") == "FROZEN_VALID",
            "sweep_vs_breakout_sequential_gold": bool(external_validation["sweep_breakout_sequential"]["accepted"]),
            "confidence_calibrated": calibration.get("probabilistic_confidence_allowed") is True,
            "abstention_available": bool(external_validation["no_evidence_abstention"]["accepted"]),
            "blind_cohort_no_catastrophic_errors": bool(blind_cohort["accepted"]),
        },
        dimension_scores=blind_cohort.get("dimension_scores") or {},
        adjudicated_case_count=int(evaluation_inputs["adjudicated_case_count"]),
        minimum_adjudicated_cases=30,
        calibration_status=str(calibration.get("status")),
        perturbation_status=(
            "PASS" if external_validation["perturbation_consistency"]["accepted"]
            else "PENDING_REAL_VISION_RESPONSES"
        ),
        blind_cohort_status=str(blind_cohort.get("status") or "MISSING"),
        implementation_contract_coverage=100.0,
    )
    _write_json(root / "17_perception_interrogation" / "certification_verdict.json", certification)

    status = _status(provider_result=provider_result, validation_result=validation_result)
    workflow_status = _workflow_status(provider_result)
    analysis_status = _analysis_status(validation_result)
    prompt_manifest = build_prompt_registry_manifest(include_text=False)
    report = {
        "schema": "ai_smc_orchestrator_v3_report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "status": status,
        "workflow_status": workflow_status,
        "analysis_status": analysis_status,
        "ai_brain_used": True,
        "provider": provider_result.audit_record(),
        "prompt_version": "ai_smc_trader_prompt_v1",
        "prompt_system": prompt_manifest,
        "evidence_pack_hash": (evidence_pack.get("provenance") or {}).get("pack_hash"),
        "chart_image_paths": chart_pack["chart_paths"],
        "context_depth_report": depth_report,
        "context_depth_profile": depth_profile,
        "perception_candidates": perception_report,
        "validation_result": validation_result.status,
        "official_state": official_decision.get("official_state"),
        "hard_issues": [issue.model_dump(mode="json") for issue in validation_result.issues if issue.severity == "hard"],
        "final_chart_template": (official_decision.get("annotation_plan") or {}).get("chart_template"),
        "official_chart": str(official_chart_path) if official_chart_path else None,
        "annotation_bitmap_review_status": bitmap_review.get("overall_status"),
        "annotation_semantic_image_review_status": semantic_image_review.get("status"),
        "native_mtf_story_pack_status": native_mtf_manifest.get("status"),
        "native_mtf_story_pack_path": str(root / "14_clean_annotation_render" / "native_mtf_story_pack" / "native_mtf_render_manifest.json") if render_charts else None,
        "object_evidence_contract_registry_path": str(root / "17_perception_interrogation" / "object_evidence_contracts.json"),
        "evaluation_input_readiness_path": str(root / "17_perception_interrogation" / "evaluation_input_readiness.json"),
        "external_validation_readiness_path": str(root / "17_perception_interrogation" / "external_validation_readiness.json"),
        "runtime_causal_integrity_path": str(root / "17_perception_interrogation" / "runtime_causal_integrity.json"),
        "calibration_readiness_path": str(root / "17_perception_interrogation" / "calibration_readiness.json"),
        "poi_ranking_freeze_path": str(root / "17_perception_interrogation" / "poi_ranking_freeze.json"),
        "chart_perturbation_manifest_path": str(root / "17_perception_interrogation" / "chart_perturbation_manifest.json") if render_charts else None,
        "certification_verdict_path": str(root / "17_perception_interrogation" / "certification_verdict.json"),
        "perception_certification_status": certification.get("status"),
        "perception_certification_score": certification.get("score"),
        "perception_certification_failed_gates": certification.get("failed_catastrophic_gates"),
        "official_decision_source": OFFICIAL_AI_SOURCE,
        "legacy_authority_role": LEGACY_DEBUG_ROLE,
        "legacy_narrative_authority_allowed_for_official_output": False,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "capital_risk": 0,
        "formal_structure_graph_path": str(root / "16_formal_structure_graph" / "structure_graph.json"),
        "structure_engine_v3_shadow_path": str(root / "16_formal_structure_graph" / "structure_engine_v3_shadow.json"),
        "formal_causal_episode_graph_path": str(root / "16_formal_structure_graph" / "causal_episode_graph_v2.json"),
        "causal_episode_story_path": str(root / "16_formal_structure_graph" / "causal_episode_story.md"),
        "causal_episode_invariant_status": (causal_episode_graph.get("invariants") or {}).get("status", "NOT_COMPUTED"),
        "causal_episode_invariant_failures": episode_graph_failure_codes(causal_episode_graph),
        "causal_episode_story_status": (causal_episode_graph.get("current_story") or {}).get("status", "NOT_COMPUTED"),
        "causal_poi_authority_path": str(root / "16_formal_structure_graph" / "causal_poi_authority.json"),
        "causal_poi_status": causal_poi_authority.get("status", "NOT_COMPUTED"),
        "causal_poi_official_direction": causal_poi_authority.get("official_direction", "unknown"),
        "structure_map_chart": str(root / "16_formal_structure_graph" / "structure_map.png"),
        "graph_invariant_status": formal_graph.get("invariants", {}).get("status", "NOT_COMPUTED"),
        "graph_invariant_failures": graph_invariant_violation_codes(formal_graph),
        "graph_parent_child_status": formal_graph.get("parent_child_context", {}).get("status", "NOT_COMPUTED"),
        "graph_thesis_sentence": graph_thesis_sentence(formal_graph),
        "graph_requires_mixed_bias": graph_requires_mixed_bias(formal_graph),
        "graph_requires_thesis_only": graph_requires_thesis_only(formal_graph),
    }
    assert_official_report_uses_ai_brain(report)

    # WP-0043: emit authority_trace.json (mandated by GATE-CANONICAL-RUNTIME-001).
    authority_trace = build_authority_trace(
        command_line=[
            "run_ai_smc_orchestrator_v3",
            f"--symbol={symbol}",
            f"--output-root={root}",
        ],
        output_root=root,
        extra={
            "symbol": symbol,
            "evidence_pack_hash": (evidence_pack.get("provenance") or {}).get("pack_hash"),
            "official_state": official_decision.get("official_state"),
            "validation_status": validation_result.status,
            "graph_invariant_status": formal_graph.get("invariants", {}).get("status", "NOT_COMPUTED"),
            "graph_parent_child_status": formal_graph.get("parent_child_context", {}).get("status", "NOT_COMPUTED"),
            "causal_episode_invariant_status": (causal_episode_graph.get("invariants") or {}).get("status", "NOT_COMPUTED"),
            "provider_model": provider_result.audit_record().get("model"),
            "render_charts": render_charts,
            "loop_count": loop_count,
        },
    )
    authority_trace_info = write_authority_trace(
        root / "authority_trace.json", authority_trace
    )
    report["authority_trace"] = {
        "path": str(root / "authority_trace.json"),
        **authority_trace_info,
    }

    _write_json(root / "final_report.json", report)
    _write_text(root / "final_report.md", _report_markdown(report))
    return AISMCOrchestratorV3Result(
        output_dir=root,
        status=status,
        report=report,
        validation_result=validation_result,
        provider_result=provider_result,
    )


def assert_official_report_uses_ai_brain(report: Mapping[str, Any]) -> None:
    if report.get("official_decision_source") != OFFICIAL_AI_SOURCE:
        raise AssertionError("Official report must use AISMCTraderBrain validated decision authority.")
    if report.get("legacy_narrative_authority_allowed_for_official_output"):
        raise AssertionError("Legacy narrative authority cannot generate official output.")
    if str(report.get("official_decision_source", "")).lower().find("legacy") >= 0:
        raise AssertionError("Official output cannot be generated from legacy authority.")


def _run_perception_candidates(
    *,
    symbol: str,
    timeframe_dfs: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: dict[str, Any] = {}
    report = {"source": "perception_engine_v2_auto", "auto_perception_ran": True, "timeframes": {}}
    for timeframe, df in timeframe_dfs.items():
        if timeframe not in {"15m", "1h", "4h", "1d"}:
            continue
        if df.empty or timeframe not in TIMEFRAME_DURATIONS:
            continue
        try:
            normalized = _normalize_timeframe_df(df)
            normalized_symbol = symbol.upper().replace("/", "").replace("-", "")
            session_profile = (
                "forex_5d"
                if _uses_sessioned_chart_proxy(normalized_symbol)
                else "continuous"
            )
            trim_report = {
                "session_gap_trimmed": False,
                "original_rows": len(normalized),
                "rows_after_trim": len(normalized),
            }
            analysis_df = normalized
            if session_profile == "forex_5d":
                trimmed, proposed_trim_report = _trim_to_latest_contiguous_segment(
                    normalized,
                    timeframe=timeframe,
                    session_profile=session_profile,
                )
                minimum_rows = int(FOREX_MINIMUM_DEPTH.get(timeframe, 0))
                if proposed_trim_report["session_gap_trimmed"] and len(trimmed) >= minimum_rows:
                    analysis_df = trimmed
                    trim_report = proposed_trim_report
                elif proposed_trim_report["session_gap_trimmed"]:
                    trim_report = {
                        **proposed_trim_report,
                        "session_gap_trimmed": False,
                        "trim_refused": True,
                        "trim_refused_reason": (
                            f"Latest contiguous segment has {len(trimmed)} rows; "
                            f"{minimum_rows} are required for {timeframe}."
                        ),
                    }
            candles = dataframe_to_candles(
                analysis_df,
                venue="LOCAL",
                instrument=symbol,
                timeframe=timeframe,
                session_profile=session_profile,
            )
            decision_time = max(candle.close_time for candle in candles)
            snapshot = PerceptionEngineV2(
                expected_instrument=symbol,
                expected_timeframe=timeframe,
            ).analyze(candles, decision_time)
            candidates[timeframe] = snapshot
            report["timeframes"][timeframe] = {
                "status": "PASS",
                "candidate_counts": {
                    "sweeps": len(snapshot.sweeps),
                    "structure_breaks": len(snapshot.structure_breaks),
                    "fvgs": len(snapshot.fvgs),
                    "order_blocks": len(snapshot.order_blocks),
                    "liquidity_levels": len(snapshot.liquidity_levels),
                    "inducements": len(snapshot.inducements),
                    "poi_grade_fvgs": len(snapshot.poi_grade_fvgs),
                },
                "rows_analyzed": len(analysis_df),
                "session_profile": session_profile,
                **trim_report,
            }
        except Exception as exc:
            candidates[timeframe] = {}
            report["timeframes"][timeframe] = {
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    return candidates, report


def _enrich_detector_candidates_with_pois(
    candidates: Mapping[str, Any], *, timeframe_dfs: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the existing deterministic POI lifecycle before evidence sealing."""
    normalized: dict[str, dict[str, Any]] = {}
    for timeframe, raw in candidates.items():
        value = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        normalized[timeframe] = dict(value) if isinstance(value, Mapping) else {}
    current_prices = {
        timeframe: float(df["close"].iloc[-1])
        for timeframe, df in timeframe_dfs.items()
        if timeframe in normalized and not df.empty
    }
    hierarchy = build_mtf_structure_hierarchy(normalized, current_prices=current_prices)
    lifecycle = build_poi_lifecycle_by_timeframe(normalized, hierarchy, current_prices=current_prices)
    counts: dict[str, Any] = {}
    for timeframe, payload in normalized.items():
        all_pois = _dedupe_pois(lifecycle.get(timeframe, []))
        active = [poi for poi in all_pois if _is_canonically_active_poi(poi)]
        payload["pois"] = all_pois
        payload["active_pois"] = active
        counts[timeframe] = {"total": len(all_pois), "active": len(active)}
    return normalized, {"status": "PASS", "counts": counts}


def _dedupe_pois(pois: Any) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for raw in pois or []:
        if not isinstance(raw, Mapping):
            continue
        poi = dict(raw)
        key = str(poi.get("poi_id") or "")
        if not key:
            key = "|".join(str(poi.get(name) or "") for name in ("timeframe", "kind", "direction", "price_low", "price_high"))
        unique.setdefault(key, poi)
    return list(unique.values())


def _is_canonically_active_poi(poi: Mapping[str, Any]) -> bool:
    freshness = str(poi.get("freshness") or "").lower()
    relation = str(poi.get("price_relation") or "").lower()
    return (
        poi.get("validity_status") == "VALID_ACTIVE_SETUP_POI"
        and poi.get("scope") == "active_setup"
        and freshness not in {"invalidated", "consumed", "full"}
        and not relation.startswith("invalidated")
    )


def _select_depth_profile(symbol: str) -> Mapping[str, int]:
    normalized = symbol.upper().replace("/", "").replace("-", "")
    if _is_forex_pair(normalized):
        return FOREX_MINIMUM_DEPTH
    return DEFAULT_MINIMUM_DEPTH


def _is_forex_pair(symbol: str) -> bool:
    currencies = {"AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"}
    return len(symbol) == 6 and symbol[:3] in currencies and symbol[3:] in currencies


def _uses_sessioned_chart_proxy(symbol: str) -> bool:
    return _is_forex_pair(symbol) or symbol in {"XAU", "XAUUSD", "GCF", "GC=F", "GC"}


def _normalize_timeframe_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={"index": "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out.sort_values("timestamp").reset_index(drop=True)


def _trim_to_latest_contiguous_segment(
    df: pd.DataFrame,
    *,
    timeframe: str,
    session_profile: str = "continuous",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Keep the latest contiguous segment for sessioned markets such as FX.

    The perception engine should still reject unexplained missing candles, but
    weekend/session closures in forex are not the same thing as corrupt data.
    Trimming is conservative: it uses only the latest post-gap segment and
    records the loss of older context in the perception report.
    """
    if len(df) <= 1:
        return df, {"session_gap_trimmed": False, "original_rows": len(df), "rows_after_trim": len(df)}
    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    expected = TIMEFRAME_DURATIONS[timeframe]
    gap_positions: list[int] = []
    for idx in range(1, len(timestamps)):
        previous_close = timestamps.iloc[idx - 1] + expected
        next_open = timestamps.iloc[idx]
        if next_open == previous_close:
            continue
        if _is_expected_closure(
            _tz_aware(previous_close),
            _tz_aware(next_open),
            session_profile,
            timeframe=timeframe,
        ):
            continue
        gap_positions.append(idx)
    if not gap_positions:
        return df, {"session_gap_trimmed": False, "original_rows": len(df), "rows_after_trim": len(df)}
    start = gap_positions[-1]
    trimmed = df.iloc[start:].reset_index(drop=True)
    return trimmed, {
        "session_gap_trimmed": True,
        "original_rows": len(df),
        "rows_after_trim": len(trimmed),
        "latest_gap_before": str(timestamps.iloc[start]),
        "expected_step": str(expected),
    }


def _downgrade_for_depth(result: ValidationResult, depth_report: Mapping[str, Any]) -> ValidationResult:
    issue = ValidationIssue(
        code="context_depth_warning",
        severity="hard",
        message="HTF context is shallower than the minimum depth; reduce authority to REVIEW_REQUIRED.",
    )
    issues = [*result.issues, issue]
    official = strip_trade_plan_for_review(json.loads(json.dumps(result.official_decision, default=str)), issues)
    official["context_depth_report"] = depth_report
    return ValidationResult(status="REVIEW_REQUIRED", decision=result.decision, official_decision=official, issues=issues)


def _workflow_status(provider_result: LLMCompletionResult) -> str:
    """How the AI reasoning was produced (workflow status).

    This is about the HANDSHAKE, not the market analysis. A successful
    workflow can still produce WATCH_ONLY, THESIS_ONLY, or REVIEW_REQUIRED
    as the correct analysis result.

    Provider mode is checked FIRST so that the mode-specific workflow names
    are always returned, regardless of is_real_reasoning settings.
    """
    mode = getattr(provider_result, "provider_mode", "")
    if mode == "STUB_PROVIDER" or provider_result.is_stub:
        return "STUB_WORKFLOW"
    if mode == "LOCAL_DETERMINISTIC_PROVIDER":
        return "LOCAL_DETERMINISTIC_WORKFLOW"
    if mode == "MANUAL_AI_ASSISTED_JSON":
        return "MANUAL_ASSISTED_WORKFLOW"
    if mode == "EXTERNAL_AI_AGENT":
        return "AGENT_REVIEW_WORKFLOW"
    if mode == "HUMAN_OVERRIDE":
        return "HUMAN_OVERRIDE_WORKFLOW"
    if mode == "REAL_VISION_LLM_PROVIDER":
        return "REAL_LLM_WORKFLOW"
    if not provider_result.is_real_reasoning:
        return "NOT_REAL_AI_WORKFLOW"
    return "UNKNOWN_WORKFLOW"


def _analysis_status(validation_result: ValidationResult) -> str:
    """The market analysis result from the validator.

    This is about the MARKET, not the AI workflow. A VALIDATED analysis
    means the decision passed all hard checks. REVIEW_REQUIRED means the
    validator caught issues.
    """
    return validation_result.status


def _status(*, provider_result: LLMCompletionResult, validation_result: ValidationResult) -> str:
    """Combined status. Workflow success + analysis result.

    Returns a composite string like "AGENT_REVIEW_PASS:VALIDATED" or
    "AGENT_REVIEW_PASS:REVIEW_REQUIRED". The first part is the workflow
    status, the second is the analysis status. A successful workflow can
    still produce REVIEW_REQUIRED as the correct market analysis.
    """
    workflow = _workflow_status(provider_result)
    analysis = _analysis_status(validation_result)
    return f"{workflow}:{analysis}"


def _chart_df(timeframe_dfs: Mapping[str, pd.DataFrame], *, tail_rows: int | None = None) -> pd.DataFrame:
    for tf in ("15m", "5m", "1h", "4h", "1d"):
        df = timeframe_dfs.get(tf)
        if df is not None:
            return df.tail(tail_rows or 240).copy()
    raise ValueError("No dataframe available for official chart rendering.")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _freeze_current_poi_ranking(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    authority = evidence_pack.get("causal_poi_authority") or {}
    registry = evidence_pack.get("object_evidence_contracts") or {}
    contracts = registry.get("contracts") if isinstance(registry, Mapping) else {}
    ranked: list[dict[str, Any]] = []
    for direction in ("bullish", "bearish"):
        scenario = (authority.get("scenarios") or {}).get(direction) if isinstance(authority, Mapping) else None
        if not isinstance(scenario, Mapping):
            continue
        candidates = [scenario.get("primary_causal_poi"), *(scenario.get("secondary_reaction_pois") or [])]
        for raw in candidates:
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            source_id = str(item.get("source_object_id") or item.get("poi_id") or "")
            contract_ids = contract_ids_for_object(registry, source_id, timeframe=str(item.get("timeframe") or ""))
            contract = contracts.get(contract_ids[0]) if isinstance(contracts, Mapping) and contract_ids else None
            if isinstance(contract, Mapping):
                item["first_knowable_candle"] = contract.get("first_knowable_candle")
            ranked.append(item)
    decision_time = str(registry.get("decision_time") or evidence_pack.get("formal_structure_graph", {}).get("decision_time"))
    return freeze_poi_ranking(
        ranked_pois=ranked,
        visible_candles=(evidence_pack.get("ohlcv_windows") or {}).get("15m") or [],
        decision_time=decision_time,
        doctrine_hash=str(registry.get("doctrine_hash") or "unknown"),
    )


def _render_structure_map(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    graph: Mapping[str, Any],
    output_path: Path,
    *,
    symbol: str,
) -> None:
    """Render a sparse structure map: gray parent range, thick external BOS, dashed internal, no trade box."""
    if not graph or not graph.get("timeframes"):
        return
    from smc_desk.rendering.structure_map_renderer import render_structure_map
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_structure_map(timeframe_dfs, graph, output_path, symbol=symbol)


def _annotation_self_review_markdown(
    *,
    scene: Mapping[str, Any],
    validation: Mapping[str, Any],
    visual_review: Mapping[str, Any],
    official_state: str,
) -> str:
    issues = validation.get("issues") or []
    source = scene.get("level_source") or "annotation_plan"
    lines = [
        "# Annotation Self-Review",
        "",
        f"- Official state: `{official_state}`",
        f"- Render source: `{source}`",
        f"- Validation: `{validation.get('status')}`",
        f"- Local visual critic: `{visual_review.get('status')}` ({visual_review.get('critic_authority')})",
        f"- Drawing objects: `{scene.get('drawing_object_count', 0)}` total / `{scene.get('visible_drawing_object_count', 0)}` visible",
        f"- Visible levels: `{scene.get('visible_level_count', 0)}`",
        f"- Trade box: `{scene.get('show_trade_box')}`",
        "",
    ]
    if issues:
        lines.append("## Issues")
        for issue in issues:
            lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
    else:
        lines.extend(
            [
                "## Result",
                "The official annotation plan passed the professional sparse-markup checks. It remains subordinate to the formal graph and does not create execution authority.",
            ]
        )
    critic_issues = visual_review.get("issues") or []
    if critic_issues:
        lines.extend(["", "## Visual Critic"])
        for issue in critic_issues:
            lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
    return "\n".join(lines) + "\n"


def _causal_episode_story_markdown(graph: Mapping[str, Any]) -> str:
    current = graph.get("current_story") if isinstance(graph, Mapping) else {}
    current = current if isinstance(current, Mapping) else {}
    invariants = graph.get("invariants") if isinstance(graph, Mapping) else {}
    invariants = invariants if isinstance(invariants, Mapping) else {}
    lines = [
        "# Formal Causal Episode Story V2",
        "",
        f"- Story status: `{current.get('status', 'INCOMPLETE')}`",
        f"- Invariants: `{invariants.get('status', 'REVIEW_REQUIRED')}`",
        f"- Controlling timeframe: `{current.get('controlling_timeframe')}`",
        f"- Summary: {current.get('summary') or 'No coherent accepted episode was available.'}",
        "",
        "## Authority",
        "Observe-only and downgrade-only. This story cannot authorize entry, stop, target, paper execution, or live execution.",
    ]
    violations = list(invariants.get("violations") or [])
    if violations:
        lines.extend(["", "## Reconciliation Failures"])
        lines.extend(f"- `{code}`" for code in violations)
    route = current.get("route_map")
    if isinstance(route, Mapping):
        lines.extend(
            [
                "",
                "## Route Map",
                f"- Direction: `{route.get('direction')}`",
                f"- Primary POI: `{(route.get('primary_poi') or {}).get('poi_id') if isinstance(route.get('primary_poi'), Mapping) else None}`",
                f"- Candidate invalidation: `{route.get('invalidation')}`",
                f"- External liquidity objective: `{route.get('liquidity_objective')}`",
                f"- Confirmation: {route.get('confirmation_requirement')}",
            ]
        )
    return "\n".join(lines) + "\n"


def _run_post_render_semantic_image_review(
    *,
    provider: AISMCProvider,
    initial_provider_result: LLMCompletionResult,
    evidence_pack: Mapping[str, Any],
    image_path: Path,
    scene: Mapping[str, Any],
) -> dict[str, Any]:
    if not initial_provider_result.is_real_reasoning:
        return {
            "schema": "smc_annotation_semantic_image_review_v1",
            "status": "NOT_PERFORMED_NO_VISION_PROVIDER",
            "reviewer_mode": initial_provider_result.provider_mode,
            "issues": [],
            "authority_contract": {"can_downgrade": True, "can_promote": False},
        }
    raw_bytes = image_path.read_bytes()
    image_manifest = {
        "official_annotation": {
            "path": str(image_path),
            "exists": True,
            "media_type": "image/png",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "base64": base64.b64encode(raw_bytes).decode("ascii"),
        }
    }
    prompt = json.dumps(
        {
            "role": "Downgrade-only professional SMC bitmap critic",
            "instructions": [
                "Inspect the final rendered chart itself, not only the drawing JSON.",
                "Check that each visible line connects the intended local swing and accepted break, POI identity and bounds are correct, labels do not overlap, and the chart tells one causal episode.",
                "Compare against formal_causal_episode_graph and the supplied scene.",
                "You may return PASS or REVIEW_REQUIRED. You may never promote a trade or invent a level.",
                "Return strict JSON with status, issues, and cleanup_requests.",
            ],
            "formal_causal_episode_graph": evidence_pack.get("formal_causal_episode_graph"),
            "scene": scene,
            "response_schema": {
                "status": "PASS or REVIEW_REQUIRED",
                "issues": [{"code": "string", "message": "string"}],
                "cleanup_requests": ["string"],
            },
        },
        sort_keys=True,
        default=str,
    )
    result = provider.complete(
        LLMCompletionRequest(
            prompt=prompt,
            evidence_pack=evidence_pack,
            chart_images=image_manifest,
            prompt_version="smc_annotation_semantic_image_review_v1",
        )
    )
    raw = result.raw_json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, Mapping) or raw.get("status") not in {"PASS", "REVIEW_REQUIRED"}:
        return {
            "schema": "smc_annotation_semantic_image_review_v1",
            "status": "REVIEW_REQUIRED",
            "reviewer_mode": result.provider_mode,
            "issues": [{"code": "semantic_image_review_schema_invalid", "message": "Vision provider did not return the required downgrade-only review schema."}],
            "cleanup_requests": [],
            "provider_audit": result.audit_record(),
            "authority_contract": {"can_downgrade": True, "can_promote": False},
        }
    normalized_issues = [
        dict(issue)
        if isinstance(issue, Mapping)
        else {"code": "semantic_image_review_issue", "message": str(issue)}
        for issue in raw.get("issues") or []
    ]
    return {
        "schema": "smc_annotation_semantic_image_review_v1",
        "status": raw.get("status"),
        "reviewer_mode": result.provider_mode,
        "issues": normalized_issues,
        "cleanup_requests": list(raw.get("cleanup_requests") or []),
        "provider_audit": result.audit_record(),
        "authority_contract": {"can_downgrade": True, "can_promote": False},
    }


def apply_visual_critic_authority(
    validation_result: ValidationResult,
    visual_review: Mapping[str, Any],
) -> ValidationResult:
    """Enforce the critic's one-way authority: keep state or downgrade only."""
    if visual_review.get("status") != "REVIEW_REQUIRED" or validation_result.status == "REVIEW_REQUIRED":
        return validation_result
    messages = [
        str(issue.get("message"))
        for issue in visual_review.get("issues", []) or []
        if isinstance(issue, Mapping) and issue.get("message")
    ]
    issue = ValidationIssue(
        code="annotation_visual_critic_veto",
        severity="hard",
        message="; ".join(messages) or "The downgrade-only annotation visual critic rejected the official scene.",
    )
    issues = [*validation_result.issues, issue]
    official = strip_trade_plan_for_review(validation_result.official_decision, issues)
    return ValidationResult(
        status="REVIEW_REQUIRED",
        decision=validation_result.decision,
        official_decision=official,
        issues=issues,
        smc_model_validity=validation_result.smc_model_validity,
        trade_plan_validity="failed",
    )


def _report_markdown(report: Mapping[str, Any]) -> str:
    lines = [f"# {report.get('symbol')} AI SMC Orchestrator V3", ""]
    lines.append(f"Status: `{report.get('status')}`")
    lines.append(f"Workflow status: `{report.get('workflow_status')}` (how the AI reasoned)")
    lines.append(f"Analysis status: `{report.get('analysis_status')}` (what the market says)")
    lines.append(f"AI brain used: `{report.get('ai_brain_used')}`")
    provider = report.get("provider") or {}
    lines.append(f"Provider: `{provider.get('provider_name')}` / `{provider.get('model_name')}`")
    lines.append(f"Validation: `{report.get('validation_result')}`")
    lines.append(f"Official state: `{report.get('official_state')}`")
    lines.append(f"Chart template: `{report.get('final_chart_template')}`")
    lines.append(f"Graph invariants: `{report.get('graph_invariant_status')}`")
    lines.append(f"Causal episode invariants: `{report.get('causal_episode_invariant_status')}`")
    lines.append(f"Causal episode story: `{report.get('causal_episode_story_status')}`")
    lines.append(f"Parent-child context: `{report.get('graph_parent_child_status')}`")
    lines.append("")
    if report.get("graph_invariant_failures"):
        lines.append("## Graph Invariant Failures")
        for code in report.get("graph_invariant_failures") or []:
            lines.append(f"- `{code}`")
        lines.append("")
    if report.get("hard_issues"):
        lines.append("## Hard Issues")
        for issue in report.get("hard_issues") or []:
            lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
    else:
        lines.append("No hard validation issues.")
    lines.append("")
    lines.append("Legacy narrative authority role: `DEBUG_LEGACY_COMPARISON_ONLY`")
    lines.append("Execution: `disabled`")
    return "\n".join(lines)
