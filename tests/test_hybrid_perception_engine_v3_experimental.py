from pathlib import Path

import pytest

from smc_desk.harness import synthetic
from smc_desk.perception.experimental_break_engine import BreakLevel
from smc_desk.perception.experimental_engine_v3 import HybridPerceptionEngineV3Experimental


def test_experimental_facade_is_observe_only_and_not_canonical():
    engine = HybridPerceptionEngineV3Experimental()

    assert engine.canonical_baseline == "PerceptionEngineV2"
    assert engine.authority_contract == {
        "canonical": False,
        "signal_allowed": False,
        "paper_execution_allowed": False,
        "live_execution_allowed": False,
        "predictive_edge_claim_allowed": False,
        "critic_may_promote": False,
    }


def test_experimental_replay_preserves_provenance_and_cannot_promote():
    case = synthetic.bullish_bos_accepted()
    result = HybridPerceptionEngineV3Experimental().run(
        case=case.case,
        candidate_pool=case.case["candidate_objects"]["4h"]["swings"],
        decision_time=case.decision_time,
        per_timeframe_cutoff=case.per_timeframe_cutoff,
        interpretation=case.expected_interpretation,
    )
    payload = result.to_dict()

    assert result.envelope.interpretation_source == "SUPPLIED_REPLAY_FIXTURE"
    assert result.envelope.certification["certified"] is False
    assert result.envelope.certification["abstained"] is True
    assert payload["authority_contract"]["signal_allowed"] is False
    assert payload["promotion_status"] == "NOT_PROMOTED"


def test_experimental_run_without_ai_or_replay_abstains():
    case = synthetic.bullish_bos_accepted()
    result = HybridPerceptionEngineV3Experimental().run(
        case=case.case,
        decision_time=case.decision_time,
        per_timeframe_cutoff=case.per_timeframe_cutoff,
    )

    assert result.envelope.interpretation_source == "NONE"
    assert result.envelope.certification["certified"] is False
    assert result.envelope.certification["abstained"] is True


def test_canonical_v2_does_not_import_experimental_v3():
    canonical_source = Path("smc_desk/perception/engine_v2.py").read_text(encoding="utf-8")

    assert "experimental_engine_v3" not in canonical_source
    assert "HybridPerceptionEngineV3Experimental" not in canonical_source


def test_negative_fill_budget_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        HybridPerceptionEngineV3Experimental(fill_budget=-1)


def test_facade_exposes_experimental_break_lifecycle_without_signal_authority():
    engine = HybridPerceptionEngineV3Experimental()
    result = engine.classify_break(
        level=BreakLevel(
            level_id="test-high",
            price=100.0,
            break_direction="bullish",
            scope="external",
            prior_direction=None,
        ),
        candles=[
            {"close_time": "2026-01-01T00:15:00Z", "open": 99.6, "high": 100.8, "low": 99.5, "close": 100.7},
            {"close_time": "2026-01-01T00:30:00Z", "open": 100.7, "high": 101.0, "low": 100.4, "close": 100.8},
            {"close_time": "2026-01-01T00:45:00Z", "open": 100.8, "high": 101.2, "low": 100.6, "close": 101.0},
        ],
        atr=1.0,
        decision_time="2026-01-01T00:45:00Z",
    )

    assert result.event_type == "INITIAL_DIRECTION_BREAK"
    assert result.authority_contract["signal_allowed"] is False
