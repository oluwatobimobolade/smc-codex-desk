"""Official AI SMC brain orchestrator.

V3 is the migration point where the AI SMC trader brain becomes the official
analysis path. Legacy rule authority is allowed only as debug comparison.
"""
from __future__ import annotations

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
from smc_desk.brain.ai_smc_trader_brain import AISMCTraderBrain
from smc_desk.brain.llm_provider import AISMCProvider, LLMCompletionRequest, LLMCompletionResult
from smc_desk.brain.prompt_system import build_prompt_registry_manifest
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.colleague.run_context import TIMEFRAME_DURATIONS, dataframe_to_candles
from smc_desk.colleague.smc_thesis_ai_v1 import build_smc_thesis_ai_v1, render_smc_thesis_ai_v1_markdown
from smc_desk.data.historical_backfill import DEFAULT_MINIMUM_DEPTH, FOREX_MINIMUM_DEPTH, build_context_depth_report
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.rendering.clean_mtf_chart_pack import render_clean_mtf_chart_pack
from smc_desk.rendering.smc_trader_annotation_renderer import render_smc_trader_annotation_chart
from smc_desk.perception.formal_structure_graph import (
    graph_invariant_violation_codes,
    graph_requires_thesis_only,
    graph_requires_mixed_bias,
    graph_thesis_sentence,
    graph_to_dict_string,
)


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
) -> AISMCOrchestratorV3Result:
    if provider is None:
        raise ValueError("A real or explicit stub AI SMC provider must be injected; no implicit provider is allowed.")
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    from smc_desk.rules import load_rule_config
    config = load_rule_config()
    daily_profile = getattr(config, "daily_session_profile", "exchange_daily_utc")

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
            daily_session_profile=daily_profile,
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
    if render_charts:
        official_chart_path = root / "14_clean_annotation_render" / f"{symbol}_official_ai_annotation.png"
        scene = render_smc_trader_annotation_chart(
            _chart_df(timeframe_dfs),
            validation_result,
            official_chart_path,
            timeframe="15m",
        )
        chart_manifest = {
            "status": "PASS",
            "chart_path": str(official_chart_path),
            "scene": scene,
            "source": "validated_ai_annotation_plan",
        }
        _write_json(root / "14_clean_annotation_render" / "annotation_manifest.json", chart_manifest)
        visual_review = scene.get("visual_critic") or {
            "schema": "professional_smc_annotation_visual_review_v1",
            "status": "NOT_AVAILABLE",
            "critic_authority": "downgrade_or_cleanup_only",
            "issues": [],
        }
        _write_json(root / "14_clean_annotation_render" / "annotation_visual_review.json", visual_review)
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

    thesis = build_smc_thesis_ai_v1(validation_result=validation_result, evidence_pack=evidence_pack)
    _write_json(root / "15_ai_thesis" / "thesis.json", thesis)
    _write_text(root / "15_ai_thesis" / "thesis.md", render_smc_thesis_ai_v1_markdown(thesis))

    _write_json(root / "16_formal_structure_graph" / "structure_graph.json", formal_graph)
    _render_structure_map(timeframe_dfs, formal_graph, root / "16_formal_structure_graph" / "structure_map.png", symbol=symbol)

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
        "official_decision_source": OFFICIAL_AI_SOURCE,
        "legacy_authority_role": LEGACY_DEBUG_ROLE,
        "legacy_narrative_authority_allowed_for_official_output": False,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "capital_risk": 0,
        "formal_structure_graph_path": str(root / "16_formal_structure_graph" / "structure_graph.json"),
        "structure_map_chart": str(root / "16_formal_structure_graph" / "structure_map.png"),
        "graph_invariant_status": formal_graph.get("invariants", {}).get("status", "NOT_COMPUTED"),
        "graph_invariant_failures": graph_invariant_violation_codes(formal_graph),
        "graph_parent_child_status": formal_graph.get("parent_child_context", {}).get("status", "NOT_COMPUTED"),
        "graph_thesis_sentence": graph_thesis_sentence(formal_graph),
        "graph_requires_mixed_bias": graph_requires_mixed_bias(formal_graph),
        "graph_requires_thesis_only": graph_requires_thesis_only(formal_graph),
    }
    assert_official_report_uses_ai_brain(report)
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
            gap_trim_report: dict[str, Any] = {"session_gap_trimmed": False}
            if _uses_sessioned_chart_proxy(symbol.upper().replace("/", "").replace("-", "")):
                normalized, gap_trim_report = _trim_to_latest_contiguous_segment(normalized, timeframe=timeframe)
            candles = dataframe_to_candles(
                normalized,
                venue="LOCAL",
                instrument=symbol,
                timeframe=timeframe,
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
                "rows_analyzed": len(normalized),
                **gap_trim_report,
            }
        except Exception as exc:
            candidates[timeframe] = {}
            report["timeframes"][timeframe] = {
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    return candidates, report


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


def _trim_to_latest_contiguous_segment(df: pd.DataFrame, *, timeframe: str) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    diffs = timestamps.diff()
    gap_positions = [idx for idx, delta in enumerate(diffs.iloc[1:], start=1) if delta != expected]
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


def _chart_df(timeframe_dfs: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    for tf in ("15m", "5m", "1h", "4h", "1d"):
        df = timeframe_dfs.get(tf)
        if df is not None:
            return df.tail(240).copy()
    raise ValueError("No dataframe available for official chart rendering.")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
