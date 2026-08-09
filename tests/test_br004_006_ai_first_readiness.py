from __future__ import annotations

import json
from pathlib import Path

import pytest

from smc_desk.brain.doctrine_panel import (
    build_doctrine_source_manifest,
    export_doctrine_panel_packets,
    finalize_doctrine_panel,
    validate_doctrine_output,
)
from smc_desk.brain.structure_lab.runtime import CallableRoleProvider, ReplayRoleProvider, run_structure_lab
from smc_desk.perception.programme_run import run_perception_programme
from smc_desk.evaluation.ai_consensus import (
    build_ai_structure_consensus,
    build_human_certification_template,
)
from smc_desk.research.benchmark_partitions import (
    BenchmarkCaseReference,
    BenchmarkPartition,
    BenchmarkRegistry,
    ProtectedBenchmarkStore,
    build_freeze_manifest,
    build_public_benchmark_pilot,
    build_unpopulated_registry,
    validate_benchmark_registry,
)


def _case_ref(case_id: str, partition: str, start: str, end: str, chart_hash: str, **kwargs):
    return BenchmarkCaseReference(
        case_id=case_id,
        partition=partition,
        symbol="BTCUSDT",
        decision_start=start,
        decision_end=end,
        content_commitment_sha256=(case_id.encode().hex() + "0" * 64)[:64],
        chart_sha256=[chart_hash],
        **kwargs,
    )


def _registry(tmp_path: Path, *, overlap: bool = False, duplicate_chart: bool = False, blind_memory: bool = False):
    dev = _case_ref(
        "dev-1",
        "development_cases",
        "2025-01-01T00:00:00Z",
        "2025-01-01T03:00:00Z",
        "a" * 64,
    )
    blind_start = "2025-01-01T02:00:00Z" if overlap else "2025-02-01T00:00:00Z"
    blind_chart = "a" * 64 if duplicate_chart else "b" * 64
    blind = _case_ref(
        "blind-1",
        "blind_validation_cases",
        blind_start,
        "2025-02-01T03:00:00Z",
        blind_chart,
        case_memory_key="leak" if blind_memory else None,
    )
    annotation = _case_ref(
        "annotation-1",
        "annotation_comprehension_cases",
        "2025-03-01T00:00:00Z",
        "2025-03-01T03:00:00Z",
        "c" * 64,
    )
    doctrine = _case_ref(
        "doctrine-1",
        "doctrine_examples",
        "2024-01-01T00:00:00Z",
        "2024-01-01T03:00:00Z",
        "d" * 64,
    )
    return BenchmarkRegistry(
        registry_id="test-registry",
        partitions={
            "doctrine_examples": BenchmarkPartition(name="doctrine_examples", status="READY", cases=[doctrine]),
            "development_cases": BenchmarkPartition(name="development_cases", status="READY", cases=[dev]),
            "blind_validation_cases": BenchmarkPartition(name="blind_validation_cases", status="LOCKED", cases=[blind]),
            "annotation_comprehension_cases": BenchmarkPartition(name="annotation_comprehension_cases", status="READY", cases=[annotation]),
        },
        blind_storage_root=str(tmp_path / "private_blind"),
        access_ledger=str(tmp_path / "access_ledger.jsonl"),
    )


def test_benchmark_registry_enforces_partition_separation(tmp_path: Path) -> None:
    assert validate_benchmark_registry(_registry(tmp_path))["status"] == "PASS"
    assert "development_blind_overlap" in {
        issue["code"] for issue in validate_benchmark_registry(_registry(tmp_path, overlap=True))["issues"]
    }
    assert "duplicate_chart_across_partitions" in {
        issue["code"] for issue in validate_benchmark_registry(_registry(tmp_path, duplicate_chart=True))["issues"]
    }
    assert "blind_case_memory_key_exposed" in {
        issue["code"] for issue in validate_benchmark_registry(_registry(tmp_path, blind_memory=True))["issues"]
    }


def test_unpopulated_registry_is_honest_about_missing_blind_cases(tmp_path: Path) -> None:
    validation = validate_benchmark_registry(build_unpopulated_registry(tmp_path))
    assert validation["status"] == "PASS"
    assert validation["blind_populated"] is False


def test_blind_store_requires_freeze_and_logs_every_access(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    store = ProtectedBenchmarkStore(tmp_path)
    store.register(registry)
    freeze = build_freeze_manifest(
        registry=registry,
        source_manifest_sha256="1" * 64,
        prompt_manifest_sha256="2" * 64,
        doctrine_manifest_sha256="3" * 64,
        provider_name="test-provider",
        model_name="test-model",
    )
    store.save_freeze(freeze)
    case_dir = store.private_root / "blind-1"
    case_dir.mkdir(parents=True)
    (case_dir / "case.json").write_text(json.dumps({"case_id": "blind-1", "secret": True}))

    with pytest.raises(PermissionError):
        store.read_blind_case("blind-1", actor="agent", action="prompt_development", freeze_id=freeze["freeze_id"])
    with pytest.raises(PermissionError):
        store.read_blind_case("blind-1", actor="agent", action="final_evaluation", freeze_id="wrong")
    payload = store.read_blind_case(
        "blind-1",
        actor="evaluation-agent",
        action="final_evaluation",
        freeze_id=freeze["freeze_id"],
    )
    assert payload["case_id"] == "blind-1"
    entries = [json.loads(line) for line in store.ledger_path.read_text().splitlines()]
    for index in range(1, len(entries)):
        assert entries[index]["previous_entry_sha256"] == entries[index - 1]["entry_sha256"]
    assert entries[-1]["event"] == "blind_access_granted"


def _lab_case() -> dict:
    return {
        "case_id": "case-1",
        "symbol": "BTCUSDT",
        "decision_time": "2026-01-01T12:00:00Z",
        "chart_manifest": {"1h": {"path": "clean_1h.png", "sha256": "a" * 64}},
        "candidate_objects": [
            {"object_id": "E-BOS", "type": "structure_break"},
            {"object_id": "E-POI", "type": "order_block"},
            {"object_id": "E-LIQ", "type": "liquidity"},
        ],
        "formal_structure_graph": {
            "schema": "formal_mtf_structure_graph_v1",
            "invariants": {"status": "PASS"},
            "authority_contract": {"signal_allowed": False},
        },
        "render_manifest": {"status": "RENDERED", "image_sha256": "f" * 64},
    }


def _responses(
    *,
    critic: str = "PASS",
    visual: str = "PASS",
    invented_first: bool = False,
    render_attestation: bool = False,
) -> dict:
    reconciliation = {
        "schema": "candidate_reconciliation_v1",
        "role": "deterministic_candidate_reconciler",
        "accepted_evidence_ids": ["E-BOS", "E-POI", "E-LIQ"],
        "rejected_candidates": [],
        "visual_to_evidence_map": {"V1": ["E-BOS"]},
        "unresolved_conflicts": [],
        "ambiguity_status": "CLEAR",
    }
    bad = {**reconciliation, "accepted_evidence_ids": ["INVENTED"]}
    return {
        "blind_visual_structure_reader": {
            "schema": "blind_visual_structure_read_v1",
            "role": "blind_visual_structure_reader",
            "observations": [
                {
                    "visual_id": "V1",
                    "timeframe": "1h",
                    "kind": "candidate_break",
                    "direction": "bearish",
                    "timestamp": None,
                    "price": None,
                    "confidence": 0.72,
                    "reason": "Visible downside expansion after a local high.",
                }
            ],
            "timeframe_summaries": {"1h": "bearish expansion"},
            "unresolved_visual_questions": [],
            "abstain": False,
        },
        "deterministic_candidate_reconciler": [bad, reconciliation] if invented_first else reconciliation,
        "causal_episode_constructor": {
            "schema": "causal_structure_episode_v1",
            "role": "causal_episode_constructor",
            "controlling_timeframe": "1h",
            "parent_external_state": "bearish",
            "child_internal_state": "bullish",
            "active_leg_evidence_ids": ["E-BOS"],
            "protected_point_evidence_ids": ["E-BOS"],
            "event_sequence_evidence_ids": ["E-BOS"],
            "liquidity_evidence_ids": ["E-LIQ"],
            "selected_poi_evidence_id": "E-POI",
            "causal_story": "Bearish external structure with a bullish internal pullback toward supply.",
            "classification": "PULLBACK",
            "confidence": 0.78,
            "alternatives": [],
            "what_would_change_the_read": ["Body close beyond the protected parent high."],
        },
        "adversarial_structure_critic": {
            "schema": "structure_critic_v1",
            "role": "adversarial_structure_critic",
            "verdict": critic,
            "violations": [],
            "required_corrections": [],
            "promotion_allowed": False,
        },
        "annotation_planner": {
            "schema": "semantic_annotation_selection_v1",
            "role": "annotation_planner",
            "selections": [
                {"object_type": "structure_segment", "semantic_object_id": "E-BOS", "timeframe": "1h", "label": "BOS", "reason": "Controlling break", "priority": 1},
                {"object_type": "poi_zone", "semantic_object_id": "E-POI", "timeframe": "1h", "label": "OB", "reason": "Selected supply", "priority": 2},
            ],
            "hidden_evidence_ids": ["E-LIQ"],
            "clutter_budget": 4,
            "geometry_source": "certified_evidence_resolver",
            "trade_box_allowed": False,
        },
        "visual_annotation_critic": {
            "schema": "visual_annotation_review_v1",
            "role": "visual_annotation_critic",
            "verdict": visual,
            "issues": [],
            "cleanup_requests": [],
            "visual_inspection_basis": "rendered_images" if render_attestation else "not_available",
            "reviewed_render_manifest_sha256": "9" * 64 if render_attestation else None,
            "reviewed_image_sha256": ["8" * 64] if render_attestation else [],
            "promotion_allowed": False,
        },
    }


def test_ai_structure_lab_runs_six_separate_grounded_roles(tmp_path: Path) -> None:
    manifest = run_structure_lab(
        case=_lab_case(),
        provider=ReplayRoleProvider(_responses()),
        output_dir=tmp_path,
    )
    assert manifest["final_status"] == "AI_PANEL_COMPLETE"
    assert manifest["truth_class"] == "AI_WEAK_CONSENSUS_ONLY"
    assert manifest["human_gold_created"] is False
    assert manifest["signal_allowed"] is False
    assert len(manifest["role_audits"]) == 6
    blind_prompt = (tmp_path / "01_blind_visual_structure_reader" / "prompt.txt").read_text()
    assert "E-BOS" not in blind_prompt
    planner = json.loads((tmp_path / "05_annotation_planner" / "parsed_response.json").read_text())
    assert planner["geometry_source"] == "certified_evidence_resolver"
    assert planner["trade_box_allowed"] is False


def test_perception_programme_executes_real_six_role_runtime(tmp_path: Path) -> None:
    def renderer(_plan, _outputs, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "schema": "professional_ai_smc_annotation_render_manifest_v1",
            "status": "PASS",
            "render_manifest_sha256": "9" * 64,
            "rendered_image_count": 1,
            "timeframes": ["1h"],
            "all_planned_objects_rendered": True,
            "pixel_review_status": "PASS",
            "images": [{"annotated_sha256": "8" * 64}],
        }

    envelope = run_perception_programme(
        case=_lab_case(),
        decision_time=_lab_case()["decision_time"],
        role_provider=ReplayRoleProvider(_responses(render_attestation=True)),
        role_output_dir=tmp_path,
        annotation_renderer=renderer,
    )
    assert envelope.role_run_executed is True
    assert envelope.role_run_status == "AI_PANEL_COMPLETE"
    assert envelope.interpretation_source == "GOVERNED_SIX_ROLE_AI_PANEL"
    assert envelope.role_run_manifest_sha256
    assert envelope.annotation_render_status == "PASS"
    assert envelope.candidate_payload_design == "anchor"
    assert envelope.retrieval_tools_advertised is False
    assert envelope.certification["certified"] is False  # doctrine remains proposed
    assert envelope.certification["summary"]["blocks"] == 0


def test_advertised_retrieval_tools_are_actually_callable(tmp_path: Path) -> None:
    """The runtime once refused anchor_tools because the loop did not exist.

    The guarantee has changed rather than disappeared: what the prompt
    advertises must now be executable. A role that emits a tool call gets a
    real answer and can then respond, instead of the tools being described and
    unreachable.
    """
    manifest = run_structure_lab(
        case=_lab_case(),
        provider=ReplayRoleProvider(_responses()),
        output_dir=tmp_path,
        candidate_payload_design="anchor_tools",
    )
    assert manifest["candidate_payload_design"] == "anchor_tools"
    # Every role audit records its tool usage, even when it asked nothing.
    for audit in manifest["role_audits"]:
        assert "tool_calls_used" in audit
        assert "tool_transcript" in audit


def test_a_role_tool_call_is_executed_and_answered(tmp_path: Path) -> None:
    """A role that asks a question gets a real answer from the evidence."""
    case = _lab_case()
    responses = _responses()
    from smc_desk.brain.structure_reasoning_roles import REQUIRED_ROLES
    first_role = REQUIRED_ROLES[0]
    # The role asks once, then answers on the follow-up completion.
    responses[first_role] = [
        {"tool_call": {"tool": "search_candidates", "arguments": {"timeframe": "4h"}}},
        responses[first_role],
    ]
    manifest = run_structure_lab(
        case=case,
        provider=ReplayRoleProvider(responses),
        output_dir=tmp_path,
        candidate_payload_design="anchor_tools",
    )
    audit = next(a for a in manifest["role_audits"] if a["role"] == first_role)
    assert audit["tool_calls_used"] == 1
    call = audit["tool_transcript"][0]
    assert call["call"]["tool"] == "search_candidates"
    assert call["result"], "the tool must return a real answer, not an empty stub"


def test_tool_calls_are_bounded(tmp_path: Path) -> None:
    """A role that only ever asks must not loop forever."""
    from smc_desk.brain.structure_lab.runtime import MAX_TOOL_CALLS_PER_ROLE

    responses = _responses()
    from smc_desk.brain.structure_reasoning_roles import REQUIRED_ROLES
    first_role = REQUIRED_ROLES[0]
    asking = {"tool_call": {"tool": "search_candidates", "arguments": {"timeframe": "4h"}}}
    # Always ask, until the budget is spent and the recorded answer is used.
    responses[first_role] = [asking] * (MAX_TOOL_CALLS_PER_ROLE + 1) + [responses[first_role]]
    manifest = run_structure_lab(
        case=_lab_case(),
        provider=ReplayRoleProvider(responses),
        output_dir=tmp_path,
        candidate_payload_design="anchor_tools",
    )
    audit = next(a for a in manifest["role_audits"] if a["role"] == first_role)
    assert audit["tool_calls_used"] <= MAX_TOOL_CALLS_PER_ROLE


def test_ai_structure_lab_allows_one_bounded_grounding_repair(tmp_path: Path) -> None:
    manifest = run_structure_lab(
        case=_lab_case(),
        provider=ReplayRoleProvider(_responses(invented_first=True)),
        output_dir=tmp_path,
        max_repair_attempts=1,
    )
    audit = manifest["role_audits"][1]
    assert audit["repair_used"] is True
    assert audit["attempts_used"] == 2


def test_ai_structure_lab_downgrades_and_never_promotes(tmp_path: Path) -> None:
    manifest = run_structure_lab(
        case=_lab_case(),
        provider=ReplayRoleProvider(_responses(critic="DOWNGRADE")),
        output_dir=tmp_path,
    )
    assert manifest["final_status"] == "REVIEW_REQUIRED"
    assert manifest["signal_allowed"] is False


def test_visual_critic_cannot_pass_existing_clean_charts_as_rendered_annotation(tmp_path: Path) -> None:
    case = _lab_case()
    case["render_manifest"] = {"status": "EXISTING_CHARTS_ONLY", "charts": case["chart_manifest"]}
    with pytest.raises(ValueError, match="Visual critic cannot PASS"):
        run_structure_lab(
            case=case,
            provider=ReplayRoleProvider(_responses()),
            output_dir=tmp_path,
        )


def test_structure_lab_renders_before_visual_critic_and_records_pixel_gate(tmp_path: Path) -> None:
    def renderer(_plan, _outputs, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "schema": "professional_ai_smc_annotation_render_manifest_v1",
            "status": "PASS",
            "render_manifest_sha256": "9" * 64,
            "rendered_image_count": 1,
            "timeframes": ["1h"],
            "all_planned_objects_rendered": True,
            "pixel_review_status": "PASS",
            "images": [{"annotated_sha256": "8" * 64}],
        }

    manifest = run_structure_lab(
        case=_lab_case(),
        provider=ReplayRoleProvider(_responses(render_attestation=True)),
        output_dir=tmp_path,
        annotation_renderer=renderer,
    )

    assert manifest["final_status"] == "AI_PANEL_COMPLETE"
    assert manifest["annotation_render"]["status"] == "PASS"
    assert manifest["annotation_render"]["pixel_review_status"] == "PASS"
    visual_prompt = (tmp_path / "07_visual_annotation_critic" / "prompt.txt").read_text()
    assert "professional_ai_smc_annotation_render_manifest_v1" in visual_prompt


def test_ai_consensus_is_useful_but_never_gold() -> None:
    episode = _responses()["causal_episode_constructor"]
    reviews = [
        {"reviewer_id": "ai-a", "provider_name": "codex", "model_name": "model-a", "causal_episode": episode},
        {"reviewer_id": "ai-b", "provider_name": "kimi", "model_name": "model-b", "causal_episode": episode},
    ]
    consensus = build_ai_structure_consensus(reviews)
    assert consensus["consensus_status"] == "AGREEMENT"
    assert consensus["truth_class"] == "AI_WEAK_CONSENSUS"
    assert consensus["gold_eligible"] is False
    template = build_human_certification_template(consensus, "case-1")
    assert template["status"] == "AWAITING_HUMAN_CERTIFICATION"
    assert template["reviewer_a"]["decision"] is None


def test_doctrine_panel_exports_source_grounded_ai_research(tmp_path: Path) -> None:
    first = tmp_path / "doctrine_a.md"
    second = tmp_path / "doctrine_b.md"
    first.write_text("A BOS requires a body close beyond a protected structural level.")
    second.write_text("A wick-only penetration is a sweep candidate, not confirmed BOS.")
    manifest = export_doctrine_panel_packets(source_paths=[first, second], output_dir=tmp_path / "panel")
    assert manifest["status"] == "READY_FOR_AI_RESEARCH"
    assert manifest["truth_class"] == "AI_WEAK_DOCTRINE_RESEARCH"
    assert manifest["runtime_authority"] is False
    sources = build_doctrine_source_manifest([first, second])
    valid = {
        "schema": "evidence_researcher_output_v1",
        "role": "evidence_researcher",
        "claims": [
            {"claim_id": "C1", "concept": "BOS", "statement": "Body-close confirmation is required.", "source_ids": ["SRC-001"], "status": "common", "confidence": 0.8}
        ],
        "unresolved_conflicts": [],
        "recommendations": [],
    }
    result = validate_doctrine_output(valid, role="evidence_researcher", allowed_source_ids={"SRC-001", "SRC-002"})
    assert result["runtime_authority"] is False
    invalid = json.loads(json.dumps(valid))
    invalid["claims"][0]["source_ids"] = ["SRC-999"]
    with pytest.raises(ValueError, match="Invented doctrine source IDs"):
        validate_doctrine_output(invalid, role="evidence_researcher", allowed_source_ids={"SRC-001", "SRC-002"})


def test_doctrine_panel_finalization_remains_certification_pending(tmp_path: Path) -> None:
    first = tmp_path / "doctrine_a.md"
    first.write_text("A BOS requires a body close beyond a protected structural level.")
    panel_root = tmp_path / "panel"
    export_doctrine_panel_packets(source_paths=[first], output_dir=panel_root)
    for order, role in enumerate((
        "evidence_researcher",
        "machine_definition_formalizer",
        "counterexample_hunter",
        "doctrine_synthesis_judge",
    ), start=1):
        status = "ACCEPT_FOR_PILOT" if role == "doctrine_synthesis_judge" else "observed"
        response = {
            "schema": f"{role}_output_v1",
            "role": role,
            "claims": [{
                "claim_id": f"{role}-1",
                "concept": "body_close",
                "statement": "Body close is a pilot rule.",
                "source_ids": ["SRC-001"],
                "status": status,
                "confidence": 0.8,
            }],
            "unresolved_conflicts": [],
            "recommendations": [],
        }
        (panel_root / f"{order:02d}_{role}" / "ai_response.json").write_text(json.dumps(response))
    result = finalize_doctrine_panel(panel_root)
    assert result["status"] == "AI_RESEARCH_COMPLETE_AWAITING_CERTIFICATION"
    assert result["accepted_for_pilot"][0]["claim_id"] == "doctrine_synthesis_judge-1"
    assert result["runtime_authority"] is False
    assert result["human_gold_created"] is False


def test_public_benchmark_pilot_registers_ai_weak_cases_without_blind_data(tmp_path: Path) -> None:
    def write_pack(path: Path, symbol: str, decision_time: str, chart_hash: str) -> None:
        path.write_text(json.dumps({
            "symbol": symbol,
            "formal_structure_graph": {"decision_time": decision_time},
            "chart_images": {"1h": {"sha256": chart_hash}},
        }))

    development = tmp_path / "development.json"
    annotation = tmp_path / "annotation.json"
    write_pack(development, "BTCUSDT", "2026-01-01T12:00:00Z", "a" * 64)
    write_pack(annotation, "GBPUSD", "2026-01-01T12:00:00Z", "b" * 64)
    registry = build_public_benchmark_pilot(
        tmp_path / "benchmark",
        development_evidence_pack=development,
        annotation_evidence_pack=annotation,
    )
    validation = validate_benchmark_registry(registry)
    assert validation["status"] == "PASS"
    assert validation["blind_populated"] is False
    assert registry.partitions["development_cases"].truth_status == "AI_WEAK_LABELS"
    assert registry.partitions["annotation_comprehension_cases"].truth_status == "AI_WEAK_LABELS"


def test_callable_provider_records_manual_ai_assisted_mode(tmp_path: Path) -> None:
    responses = _responses()
    provider = CallableRoleProvider(
        lambda role, _prompt, _payload, _attempt: responses[role],
        provider_name="manual-ai-reviewer",
        model_name="operator-json",
        provider_mode="MANUAL_AI_ASSISTED_JSON",
    )
    manifest = run_structure_lab(case=_lab_case(), provider=provider, output_dir=tmp_path)
    assert manifest["provider_mode"] == "MANUAL_AI_ASSISTED_JSON"
    assert manifest["role_audits"][0]["metadata"]["real_ai_reasoning"] is True
