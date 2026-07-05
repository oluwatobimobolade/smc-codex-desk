"""Tests for WP-0037 External AI Agent Brain Handoff Protocol.

These tests prove the system can:
1. Export a complete review packet
2. Validate an agent response
3. Import and validate the response
4. Run through the full validation pipeline
5. Reject invalid responses
6. Treat external agents honestly
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from smc_desk.brain.agent_handoff.agent_audit_manifest import build_agent_audit_manifest
from smc_desk.brain.agent_handoff.agent_schemas import (
    AGENT_PACKET_FILES,
    AGENT_RESPONSE_FILES,
    make_agent_response_template,
)
from smc_desk.brain.agent_handoff.export_agent_packet import export_agent_packet
from smc_desk.brain.agent_handoff.external_agent_provider import ExternalAIAgentProvider
from smc_desk.brain.agent_handoff.import_agent_response import (
    import_agent_response,
    validate_response_structure,
)
from smc_desk.brain.ai_smc_trader_brain import parse_ai_smc_decision
from smc_desk.brain.llm_provider import CallableAISMCProvider


def _make_timeframe_dfs() -> dict[str, pd.DataFrame]:
    timestamps = pd.date_range("2026-07-01", periods=100, freq="15min", tz="UTC")
    base = 63000.0
    df_15m = pd.DataFrame({
        "timestamp": timestamps,
        "open": [base + i * (-1) for i in range(100)],
        "high": [base + i * (-1) + 50 for i in range(100)],
        "low": [base + i * (-1) - 50 for i in range(100)],
        "close": [base + i * (-1) - 10 for i in range(100)],
        "volume": [1000.0] * 100,
    })
    df_1h = df_15m.resample("1h", on="timestamp").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
    df_4h = df_15m.resample("4h", on="timestamp").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
    df_1d = df_15m.resample("1D", on="timestamp").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
    return {"15m": df_15m, "1h": df_1h, "4h": df_4h, "1d": df_1d}


def _make_evidence_pack() -> dict:
    return {
        "schema": "smc_evidence_pack_v1",
        "symbol": "BTCUSDT",
        "active_range_authority": {
            "selected_range": {
                "status": "RESOLVED_ACTIVE_RANGE",
                "timeframe": "4h",
                "direction": "bearish",
                "range_high": 63500.0,
                "range_low": 57800.0,
                "equilibrium": 60650.0,
                "price_location": "premium",
                "range_id": "BTCUSDT:4h:active_range:test",
                "width_atr": 4.5,
                "max_width_atr": 22.0,
                "protected_high_pivot_id": "BTCUSDT:4h:swing_high:test",
                "protected_low_pivot_id": "BTCUSDT:4h:swing_low:test",
                "protected_high": 63500.0,
                "protected_low": 57800.0,
                "authority_notes": ["Active range from protected swing pair."],
            }
        },
        "detector_candidates": {
            "1d": {"structure_breaks": [], "sweeps": [], "order_blocks": [], "liquidity_levels": []},
            "4h": {"structure_breaks": [], "sweeps": [], "order_blocks": [], "liquidity_levels": []},
            "1h": {"structure_breaks": [], "sweeps": [], "order_blocks": [], "liquidity_levels": []},
            "15m": {"structure_breaks": [], "sweeps": [], "order_blocks": [], "liquidity_levels": []},
        },
        "ohlcv_windows": {"1d": [], "4h": [], "1h": [], "15m": []},
        "provenance": {"pack_hash": "test_hash"},
        "data_contract": {"source": "test", "canonical_timeframe": "15m", "execution_authority": "disabled"},
        "authority_contract": {"evidence_only": True, "execution": "disabled", "capital_risk": 0},
        "structure_narrative": {
            "parent_child_context": {"has_parent_child_conflict": False, "status": "ALIGNED", "thesis_sentence": "All timeframes aligned bearish."},
            "timeframes": {},
        },
    }


def _make_chart_paths(tmp_path: Path) -> dict[str, Path]:
    chart_dir = tmp_path / "charts"
    chart_dir.mkdir(exist_ok=True)
    paths: dict[str, Path] = {}
    for tf in ("1d", "4h", "1h", "15m"):
        path = chart_dir / f"clean_{tf}_chart.png"
        from PIL import Image
        Image.new("RGB", (100, 100), color="white").save(path)
        paths[tf] = path
    return paths


def test_external_agent_provider_mode_exists() -> None:
    """EXTERNAL_AI_AGENT must be a valid provider mode."""
    provider = ExternalAIAgentProvider(
        {"schema": "ai_smc_trader_decision_v1", "symbol": "BTCUSDT", "official_state": "WATCH_ONLY", "setup_grade": "C", "direction": "mixed", "setup_model": "test", "bias_summary": {"daily": "mixed", "4h": "mixed", "1h": "mixed", "final_bias": "mixed", "evidence": []}, "active_range": {"timeframe": "4h", "price_location": "unknown", "evidence_object_ids": [], "evidence": []}, "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": ""}, "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": ""}, "active_poi": {"direction": "unknown", "evidence_object_ids": [], "summary": ""}, "entry_plan": {"entry_ready": False, "evidence_object_ids": [], "required_confirmation": [], "summary": ""}, "stop_loss_plan": {"evidence_object_ids": [], "summary": ""}, "target_plan": {"targets": [], "summary": ""}, "rr_status": {"rr": None, "pass_rr": False, "notes": ""}, "invalidation": {"condition": "", "evidence_object_ids": []}, "annotation_plan": {"chart_template": "context_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": ["daily_context", "4h_context", "1h_context", "active_range", "premium_discount", "obvious_liquidity", "swept_liquidity", "displacement_quality", "active_poi", "entry_model", "entry_readiness", "structural_invalidation", "model_completion_liquidity_target", "rr_minimum_three", "final_state"]}, "final_thesis": ""},
        agent_name="Codex",
        agent_model="gpt-4",
    )
    from smc_desk.brain.llm_provider import LLMCompletionRequest
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "EXTERNAL_AI_AGENT"
    assert result.is_real_reasoning is True
    assert result.is_real_llm_call is False
    assert result.metadata["agent_name"] == "Codex"


def test_callable_accepts_external_ai_agent_mode() -> None:
    """CallableAISMCProvider must accept EXTERNAL_AI_AGENT as a valid mode."""
    def _fn(request):
        return {"schema": "ai_smc_trader_decision_v1", "symbol": "BTCUSDT"}
    provider = CallableAISMCProvider(
        _fn,
        provider_name="external_agent",
        model_name="agent_response",
        provider_mode="EXTERNAL_AI_AGENT",
    )
    from smc_desk.brain.llm_provider import LLMCompletionRequest
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "EXTERNAL_AI_AGENT"
    assert result.is_real_reasoning is True
    assert result.is_real_llm_call is False


def test_export_agent_packet_contains_charts_prompts_evidence_schema(tmp_path: Path) -> None:
    """Exported packet must contain charts, prompts, evidence, and schema files."""
    evidence_pack = _make_evidence_pack()
    chart_paths = _make_chart_paths(tmp_path)
    packet_dir = tmp_path / "packet"
    manifest = export_agent_packet(
        symbol="BTCUSDT",
        evidence_pack=evidence_pack,
        chart_paths=chart_paths,
        output_dir=packet_dir,
    )
    for filename in AGENT_PACKET_FILES:
        assert (packet_dir / filename).exists(), f"Missing {filename}"
    assert "schema" in manifest
    assert manifest["schema"] == "ai_smc_agent_packet_v1"
    assert manifest["chart_count"] >= 1


def test_agent_packet_has_hash_and_manifest(tmp_path: Path) -> None:
    """Packet must have run_manifest.json with file hashes and evidence pack hash."""
    evidence_pack = _make_evidence_pack()
    chart_paths = _make_chart_paths(tmp_path)
    packet_dir = tmp_path / "packet"
    manifest = export_agent_packet(
        symbol="BTCUSDT",
        evidence_pack=evidence_pack,
        chart_paths=chart_paths,
        output_dir=packet_dir,
    )
    assert manifest["evidence_pack_hash"]
    assert manifest["file_hashes"]
    assert len(manifest["file_hashes"]) >= 5
    for filename, file_hash in manifest["file_hashes"].items():
        assert len(file_hash) == 64


def test_import_agent_response_requires_official_decision_candidate(tmp_path: Path) -> None:
    """Import must fail if official_decision_candidate.json is missing."""
    response_dir = tmp_path / "response"
    response_dir.mkdir()
    (response_dir / "agent_reasoning_summary.md").write_text("test")
    errors = validate_response_structure(response_dir)
    assert any("official_decision_candidate.json" in e for e in errors)


def test_import_agent_response_requires_agent_reasoning_summary(tmp_path: Path) -> None:
    """Import must fail if agent_reasoning_summary.md is missing."""
    response_dir = tmp_path / "response"
    response_dir.mkdir()
    (response_dir / "official_decision_candidate.json").write_text(json.dumps({"schema": "ai_smc_trader_decision_v1", "symbol": "BTCUSDT", "official_state": "WATCH_ONLY", "setup_grade": "C", "direction": "mixed", "setup_model": "test", "bias_summary": {"daily": "mixed", "4h": "mixed", "1h": "mixed", "final_bias": "mixed", "evidence": []}, "active_range": {"timeframe": "4h", "price_location": "unknown", "evidence_object_ids": [], "evidence": []}, "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": ""}, "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": ""}, "active_poi": {"direction": "unknown", "evidence_object_ids": [], "summary": ""}, "entry_plan": {"entry_ready": False, "evidence_object_ids": [], "required_confirmation": [], "summary": ""}, "stop_loss_plan": {"evidence_object_ids": [], "summary": ""}, "target_plan": {"targets": [], "summary": ""}, "rr_status": {"rr": None, "pass_rr": False, "notes": ""}, "invalidation": {"condition": "", "evidence_object_ids": []}, "annotation_plan": {"chart_template": "context_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": ["daily_context"]}, "final_thesis": ""}))
    errors = validate_response_structure(response_dir)
    assert any("agent_reasoning_summary.md" in e for e in errors)


def test_external_agent_response_must_match_schema(tmp_path: Path) -> None:
    """Response must match ai_smc_trader_decision_v1 schema."""
    response_dir = tmp_path / "response"
    response_dir.mkdir()
    bad_payload = {"schema": "wrong_schema", "symbol": "BTCUSDT"}
    (response_dir / "official_decision_candidate.json").write_text(json.dumps(bad_payload))
    (response_dir / "agent_reasoning_summary.md").write_text("test")
    errors = validate_response_structure(response_dir)
    assert any("ai_smc_trader_decision_v1" in e for e in errors)


def test_external_agent_can_pass_when_validation_passes(tmp_path: Path) -> None:
    """A valid external agent response can produce AGENT_REVIEW_PASS."""
    response_dir = tmp_path / "response"
    response_dir.mkdir()
    decision = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "WATCH_ONLY",
        "setup_grade": "C",
        "direction": "bearish",
        "setup_model": "test_agent_model",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": ["test"]},
        "active_range": {"timeframe": "4h", "high": 63500.0, "low": 57800.0, "equilibrium": 60650.0, "price_location": "premium", "source": "protected_swing_pair", "evidence_object_ids": [], "evidence": ["Active range from protected swing pair."]},
        "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": "Test narrative."},
        "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": "Test."},
        "active_poi": {"direction": "unknown", "evidence_object_ids": [], "summary": "No active POI."},
        "entry_plan": {"entry_ready": False, "evidence_object_ids": [], "required_confirmation": [], "summary": "No entry."},
        "stop_loss_plan": {"evidence_object_ids": [], "summary": "No stop."},
        "target_plan": {"targets": [], "summary": "No target."},
        "rr_status": {"rr": None, "pass_rr": False, "notes": "No RR."},
        "invalidation": {"condition": "Test.", "evidence_object_ids": []},
        "annotation_plan": {"chart_template": "watch_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": ["daily_context", "4h_context", "1h_context", "active_range", "premium_discount", "obvious_liquidity", "swept_liquidity", "displacement_quality", "active_poi", "entry_model", "entry_readiness", "structural_invalidation", "model_completion_liquidity_target", "rr_minimum_three", "final_state"]},
        "final_thesis": "Test thesis.",
        "packet_hash": "test_hash",
    }
    (response_dir / "official_decision_candidate.json").write_text(json.dumps(decision))
    (response_dir / "agent_reasoning_summary.md").write_text("Test reasoning.")
    (response_dir / "annotation_plan.json").write_text(json.dumps({"labels": [], "levels": []}))

    evidence_pack = _make_evidence_pack()
    evidence_pack["provenance"]["pack_hash"] = "test_hash"

    imported = import_agent_response(response_dir, expected_packet_hash="test_hash")
    assert imported["audit"]["packet_hash_match"] is True
    assert imported["decision"].symbol == "BTCUSDT"
    assert imported["decision"].official_state == "WATCH_ONLY"


def test_external_agent_can_pass_when_validation_passes_full(tmp_path: Path) -> None:
    """A valid external agent response with proper self_review passes validation."""
    response_dir = tmp_path / "response"
    response_dir.mkdir()
    decision = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "WATCH_ONLY",
        "setup_grade": "C",
        "direction": "bearish",
        "setup_model": "test_agent_model",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": ["test"]},
        "active_range": {"timeframe": "4h", "high": 63500.0, "low": 57800.0, "equilibrium": 60650.0, "price_location": "premium", "source": "protected_swing_pair", "evidence_object_ids": [], "evidence": ["Active range from protected swing pair."]},
        "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": "Test narrative."},
        "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": "Test."},
        "active_poi": {"direction": "unknown", "evidence_object_ids": [], "summary": "No active POI."},
        "entry_plan": {"entry_ready": False, "evidence_object_ids": [], "required_confirmation": [], "summary": "No entry."},
        "stop_loss_plan": {"evidence_object_ids": [], "summary": "No stop."},
        "target_plan": {"targets": [], "summary": "No target."},
        "rr_status": {"rr": None, "pass_rr": False, "notes": "No RR."},
        "invalidation": {"condition": "Test.", "evidence_object_ids": []},
        "annotation_plan": {"chart_template": "watch_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": ["daily_context", "4h_context", "1h_context", "active_range", "premium_discount", "obvious_liquidity", "swept_liquidity", "displacement_quality", "active_poi", "entry_model", "entry_readiness", "structural_invalidation", "model_completion_liquidity_target", "rr_minimum_three", "final_state"]},
        "self_review": {"active_range_check": "passed", "poi_check": "not_applicable", "annotation_check": "passed", "refusal_check": "passed", "corrections_made": [], "remaining_uncertainties": []},
        "final_thesis": "Test thesis.",
        "packet_hash": "test_hash",
    }
    (response_dir / "official_decision_candidate.json").write_text(json.dumps(decision))
    (response_dir / "agent_reasoning_summary.md").write_text("Test reasoning.")
    (response_dir / "annotation_plan.json").write_text(json.dumps({"labels": [], "levels": []}))

    evidence_pack = _make_evidence_pack()
    evidence_pack["provenance"]["pack_hash"] = "test_hash"

    from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
    imported = import_agent_response(response_dir, expected_packet_hash="test_hash")
    decision_parsed = imported["decision"]
    result = validate_ai_smc_decision(decision_parsed, evidence_pack)
    hard_issues = [i for i in result.issues if i.severity == "hard"]
    assert result.status == "VALIDATED", f"Expected VALIDATED, got {result.status}. Hard: {[(i.code, i.message) for i in hard_issues]}"


def test_manual_json_still_cannot_full_pass() -> None:
    """MANUAL_AI_ASSISTED_JSON still returns PARTIAL_PASS, not full PASS."""
    from smc_desk.colleague.orchestrator_v3 import _status
    from smc_desk.brain.llm_provider import LLMCompletionResult
    from smc_desk.brain.ai_smc_trader_brain import (
        BiasSummary, ActiveRange, LiquidityStory, DisplacementAssessment,
        ActivePOI, EntryPlan, StopLossPlan, TargetPlan, RRStatus,
        InvalidationPlan, AnnotationPlan, SelfReview, AISMCDecision
    )
    decision = AISMCDecision(
        symbol="BTCUSDT",
        official_state="WATCH_ONLY",
        setup_grade="C",
        direction="mixed",
        setup_model="test",
        bias_summary=BiasSummary(daily="mixed", four_hour="mixed", one_hour="mixed", final_bias="mixed", evidence=[]),
        active_range=ActiveRange(timeframe="4h", price_location="unknown"),
        liquidity_story=LiquidityStory(narrative="test"),
        displacement_assessment=DisplacementAssessment(direction="none", quality="none", summary="test"),
        active_poi=ActivePOI(direction="unknown", summary="test"),
        entry_plan=EntryPlan(entry_ready=False, summary="test"),
        stop_loss_plan=StopLossPlan(summary="test"),
        target_plan=TargetPlan(summary="test"),
        rr_status=RRStatus(notes="test"),
        invalidation=InvalidationPlan(condition="test"),
        annotation_plan=AnnotationPlan(chart_template="context_chart", reasoning_order=["daily_context"]),
        self_review=SelfReview(),
        final_thesis="test",
    )
    from dataclasses import dataclass
    @dataclass
    class FakeVR:
        is_stub: bool = False
        is_real_reasoning: bool = True
        provider_mode: str = "MANUAL_AI_ASSISTED_JSON"
    @dataclass
    class FakeVal:
        status: str = "VALIDATED"
        official_decision: dict = None
        def __post_init__(self):
            self.official_decision = {"official_state": "WATCH_ONLY"}
    assert _status(provider_result=FakeVR(), validation_result=FakeVal()) == "PARTIAL_PASS"


def test_local_deterministic_provider_cannot_claim_real_ai() -> None:
    """LOCAL_DETERMINISTIC_PROVIDER returns SAFE_SIMULATION_PASS, not real AI reasoning."""
    from smc_desk.colleague.orchestrator_v3 import _status
    from dataclasses import dataclass
    @dataclass
    class FakeVR:
        is_stub: bool = False
        is_real_reasoning: bool = False
        provider_mode: str = "LOCAL_DETERMINISTIC_PROVIDER"
    @dataclass
    class FakeVal:
        status: str = "VALIDATED"
        official_decision: dict = None
        def __post_init__(self):
            self.official_decision = {"official_state": "WATCH_ONLY"}
    assert _status(provider_result=FakeVR(), validation_result=FakeVal()) == "SAFE_SIMULATION_PASS"


def test_watch_state_from_external_agent_has_no_trade_box() -> None:
    """Watch state from external agent must not have trade box."""
    decision_payload = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "WATCH_ONLY",
        "setup_grade": "C",
        "direction": "bearish",
        "setup_model": "test",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": []},
        "active_range": {"timeframe": "4h", "price_location": "unknown", "evidence_object_ids": [], "evidence": []},
        "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": ""},
        "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": ""},
        "active_poi": {"direction": "unknown", "evidence_object_ids": [], "summary": ""},
        "entry_plan": {"entry_ready": False, "evidence_object_ids": [], "required_confirmation": [], "summary": ""},
        "stop_loss_plan": {"evidence_object_ids": [], "summary": ""},
        "target_plan": {"targets": [], "summary": ""},
        "rr_status": {"rr": None, "pass_rr": False, "notes": ""},
        "invalidation": {"condition": "", "evidence_object_ids": []},
        "annotation_plan": {"chart_template": "watch_chart", "show_trade_box": False, "labels": [], "levels": [], "reasoning_order": ["daily_context"]},
        "final_thesis": "",
    }
    provider = ExternalAIAgentProvider(decision_payload, agent_name="Codex", agent_model="gpt-4")
    from smc_desk.brain.llm_provider import LLMCompletionRequest
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "EXTERNAL_AI_AGENT"
    parsed = json.loads(json.dumps(result.raw_json))
    assert parsed["official_state"] == "WATCH_ONLY"
    assert parsed["annotation_plan"]["show_trade_box"] is False


def test_trade_ready_from_external_agent_requires_grounded_levels() -> None:
    """Trade-ready from external agent requires grounded entry/SL/target with anchors."""
    decision_payload = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "TRADE_PLAN_READY",
        "setup_grade": "A",
        "direction": "bearish",
        "setup_model": "test_trade",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": []},
        "active_range": {"timeframe": "4h", "high": 63500.0, "low": 57800.0, "equilibrium": 60650.0, "price_location": "premium", "source": "protected_swing_pair", "evidence_object_ids": [], "evidence": []},
        "liquidity_story": {"obvious_liquidity": [{"liquidity_id": "4h_ssl", "timeframe": "4h", "side": "sell_side", "price": 57800.0, "label": "SSL", "status": "model_completion_reference"}], "swept_liquidity": [{"liquidity_id": "4h_bsl", "timeframe": "4h", "side": "buy_side", "price": 63500.0, "status": "prior_swept_liquidity"}], "unswept_liquidity": [], "narrative": "test"},
        "displacement_assessment": {"direction": "bearish", "quality": "clean", "structure_broken": True, "evidence_object_ids": ["4h_bear_bos", "1h_bear_disp"], "summary": "Clean bearish displacement."},
        "active_poi": {"poi_id": "1h_supply_origin", "timeframe": "1h", "kind": "order_block", "direction": "bearish", "price_low": 62800.0, "price_high": 63000.0, "freshness": "fresh", "evidence_object_ids": ["1h_supply_origin"], "summary": "1h supply origin."},
        "entry_plan": {"entry_ready": True, "entry_timeframe": "15m", "refinement_timeframe": "5m", "entry_price": 62900.0, "entry_zone_low": 62850.0, "entry_zone_high": 62900.0, "signal_type": "rejection", "required_confirmation": ["15m rejection"], "evidence_object_ids": ["1h_supply_origin"], "entry_anchor": "1h_supply_origin", "mapped_entry_price": 62900.0, "summary": "Entry at 1h supply."},
        "stop_loss_plan": {"stop_price": 63000.0, "structural_invalidation_price": 63000.0, "source": "1h_supply_origin_high", "buffer_notes": "", "evidence_object_ids": ["1h_supply_origin"], "stop_anchor": "1h_supply_origin_high", "mapped_stop_price": 63000.0, "summary": "Stop at 1h supply high."},
        "target_plan": {"targets": [{"price": 57800.0, "label": "4h SSL", "timeframe": "4h", "reason": "Model completion", "evidence_object_ids": ["4h_ssl"], "target_anchor": "4h_ssl", "mapped_target_price": 57800.0}], "model_completion_liquidity_id": "4h_ssl", "summary": "Target 4h SSL."},
        "rr_status": {"rr": 51.0, "pass_rr": True, "notes": "RR=51.0"},
        "invalidation": {"invalidation_price": 63000.0, "condition": "Body close above 1h supply high.", "source": "1h_supply_origin_high", "evidence_object_ids": ["1h_supply_origin"], "invalidation_anchor": "1h_supply_origin_high", "mapped_invalidation_price": 63000.0},
        "annotation_plan": {"chart_template": "trade_plan_chart", "show_trade_box": True, "labels": [], "levels": [], "reasoning_order": ["daily_context", "4h_context", "1h_context", "active_range", "premium_discount", "obvious_liquidity", "swept_liquidity", "displacement_quality", "active_poi", "entry_model", "entry_readiness", "structural_invalidation", "model_completion_liquidity_target", "rr_minimum_three", "final_state"]},
        "self_review": {"active_range_check": "passed", "poi_check": "passed", "annotation_check": "passed", "refusal_check": "passed", "corrections_made": [], "remaining_uncertainties": []},
        "final_thesis": "Trade ready bearish.",
    }
    evidence_pack = _make_evidence_pack()
    evidence_pack["detector_candidates"]["4h"]["structure_breaks"] = [
        {"object_id": "4h_bear_bos", "break_type": "BOS", "direction": "bearish", "confirmed_at": "2026-07-01T00:00:00Z", "structure_scope": "external", "evidence": {"broken_price": "63500.0", "is_unconfirmed_probe": False, "broke_protected_swing": True, "structure_scope": "external"}},
        {"object_id": "1h_bear_disp", "break_type": "BOS", "direction": "bearish", "confirmed_at": "2026-07-02T04:00:00Z", "structure_scope": "internal", "evidence": {"broken_price": "62800.0", "is_unconfirmed_probe": False, "broke_protected_swing": False, "structure_scope": "internal"}},
    ]
    evidence_pack["detector_candidates"]["4h"]["order_blocks"] = [{"object_id": "1h_supply_origin", "direction": "bearish", "price_low": 62800.0, "price_high": 63000.0, "timeframe": "1h"}]
    evidence_pack["detector_candidates"]["4h"]["sweeps"] = [{"object_id": "4h_sweep_high", "price": 63500.0, "side": "buy_side"}]
    evidence_pack["detector_candidates"]["4h"]["liquidity_levels"] = [{"object_id": "4h_ssl", "price": 57800.0, "side": "sell_side"}]

    from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
    decision = parse_ai_smc_decision(decision_payload)
    result = validate_ai_smc_decision(decision, evidence_pack)
    hard_issues = [i for i in result.issues if i.severity == "hard"]
    assert result.status == "VALIDATED", f"Expected VALIDATED, got {result.status}. Hard: {[(i.code, i.message) for i in hard_issues]}"


def test_agent_audit_manifest_includes_identity_and_hashes() -> None:
    """Audit manifest must include agent identity, packet hash, and response hash."""
    audit = build_agent_audit_manifest(
        symbol="BTCUSDT",
        packet_dir=Path("/tmp/packet"),
        response_dir=Path("/tmp/response"),
        packet_manifest={"schema": "ai_smc_agent_packet_v1", "evidence_pack_hash": "abc123"},
        response_audit={"packet_hash_match": True, "response_hash": "def456", "agent_identity": {"agent_name": "Codex"}},
        validation_status="VALIDATED",
        official_state="WATCH_ONLY",
        final_decision_hash="ghi789",
    )
    assert audit["schema"] == "ai_smc_agent_audit_v1"
    assert audit["symbol"] == "BTCUSDT"
    assert audit["packet"]["manifest"]["evidence_pack_hash"] == "abc123"
    assert audit["response"]["audit"]["response_hash"] == "def456"
    assert audit["response"]["audit"]["agent_identity"]["agent_name"] == "Codex"
    assert audit["validation"]["validation_status"] == "VALIDATED"
    assert audit["final_decision_hash"] == "ghi789"


def test_response_template_has_required_fields() -> None:
    """The response template must include all required fields."""
    template = make_agent_response_template()
    assert template["schema"] == "ai_smc_agent_response_v1"
    assert "agent_identity" in template
    assert "packet_hash" in template
    assert "decision" in template
    assert "semantic_anchors" in template
    sa = template["semantic_anchors"]
    for key in ("poi_anchor", "entry_anchor", "stop_anchor", "target_anchor", "invalidation_anchor"):
        assert key in sa
