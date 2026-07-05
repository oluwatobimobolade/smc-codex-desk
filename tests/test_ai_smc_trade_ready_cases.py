"""Test that trade-ready AI SMC cases validate correctly through the full pipeline.

These cases prove the system can accept a real trade plan, not just refuse
everything. Each case must:
  1. Pass Pydantic schema validation
  2. Pass the consistency validator
  3. Produce the expected official state
  4. Produce the expected chart template
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import parse_ai_smc_decision
from smc_desk.brain.llm_provider import CallableAISMCProvider
from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ai_smc_cases"


def _load_case(case_id: str) -> dict:
    path = FIXTURES_DIR / f"{case_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _make_timeframe_dfs() -> dict[str, pd.DataFrame]:
    """Create minimal but valid timeframe dataframes for orchestrator."""
    timestamps = pd.date_range("2026-07-01", periods=100, freq="15min", tz="UTC")
    base = 63000.0
    data = {
        "open": [base + i * (-1) for i in range(100)],
        "high": [base + i * (-1) + 50 for i in range(100)],
        "low": [base + i * (-1) - 50 for i in range(100)],
        "close": [base + i * (-1) - 10 for i in range(100)],
        "volume": [1000.0] * 100,
    }
    df_15m = pd.DataFrame(data, index=timestamps)
    df_15m.index.name = "timestamp"

    df_1h = df_15m.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df_4h = df_15m.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df_1d = df_15m.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

    return {"15m": df_15m.reset_index(), "1h": df_1h.reset_index(), "4h": df_4h.reset_index(), "1d": df_1d.reset_index()}


def _make_evidence_pack(case: dict) -> dict:
    """Build a minimal evidence pack from the case fixture."""
    ep = case["evidence_pack"]
    return {
        "schema": "smc_evidence_pack_v1",
        "symbol": "BTCUSDT",
        "active_range_authority": ep["active_range_authority"],
        "detector_candidates": ep["detector_candidates"],
        "structure_narrative": {
            "timeframes": {},
            "parent_child_context": {
                "has_parent_child_conflict": False,
                "status": "ALIGNED",
                "thesis_sentence": "All timeframes aligned bearish."
            }
        },
        "ohlcv_summaries": {},
        "data_contract": {"source": "fixture", "canonical_timeframe": "15m", "execution_authority": "disabled"},
        "authority_contract": {"evidence_only": True, "execution": "disabled", "capital_risk": 0},
        "provenance": {"pack_hash": "fixture01"},
    }


def test_bearish_trade_ready_validates() -> None:
    """A valid bearish trade-ready setup must pass validation and produce TRADE_PLAN_READY."""
    case = _load_case("bearish_trade_ready_01")
    decision = parse_ai_smc_decision(case["ai_decision"])
    pack = _make_evidence_pack(case)
    result = validate_ai_smc_decision(decision, pack)

    hard_issues = [i for i in result.issues if i.severity == "hard"]
    assert result.status == "VALIDATED", f"Expected VALIDATED, got {result.status}. Hard issues: {[(i.code, i.message) for i in hard_issues]}"
    assert case["expected_validation_result"] == "VALIDATED"
    assert result.official_decision["official_state"] == "TRADE_PLAN_READY"
    assert result.official_decision["annotation_plan"]["chart_template"] == "trade_plan_chart"


def test_bearish_trade_ready_runs_through_orchestrator(tmp_path) -> None:
    """Trade-ready case must run through the full orchestrator and produce all artifacts."""
    case = _load_case("bearish_trade_ready_01")
    timeframe_dfs = _make_timeframe_dfs()

    provider = CallableAISMCProvider(
        lambda request, payload=case["ai_decision"]: payload,
        provider_name="fixture_ai_decision",
        model_name="test_fixture",
        provider_mode="MANUAL_AI_ASSISTED_JSON",
    )

    result = run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=timeframe_dfs,
        provider=provider,
        output_dir=tmp_path,
        detector_candidates=case["evidence_pack"]["detector_candidates"],
        session_context={"fixture_case": case["case_id"]},
        enforce_minimum_depth=False,
    )

    assert result.status in ("PARTIAL_PASS", "REVIEW_REQUIRED"), f"Unexpected status: {result.status}"
    assert (tmp_path / "11_ai_smc_trader_brain" / "raw_decision.json").exists()
    assert (tmp_path / "12_ai_consistency_validation" / "validation_result.json").exists()
    assert (tmp_path / "13_official_ai_decision" / "official_decision.json").exists()
    assert (tmp_path / "15_ai_thesis" / "thesis.md").exists()
    assert (tmp_path / "16_formal_structure_graph" / "structure_graph.json").exists()
    assert (tmp_path / "final_report.md").exists()
