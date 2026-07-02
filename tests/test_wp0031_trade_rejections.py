from __future__ import annotations

from smc_desk.decision.trade_rejection_engine import evaluate_trade_rejections
from smc_desk.decision.setup_classifier import NO_CLEAR_MODEL


def test_trade_rejected_no_clear_model():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": NO_CLEAR_MODEL},
        active_poi={},
    )
    assert "REJECTED_NO_CLEAR_MODEL" in result["hard_rejections"]


def test_trade_rejected_against_htf_control():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": "BREAKER_RETEST_SHORT"},
        htf_control=False,
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
    )
    assert "REJECTED_AGAINST_HTF_CONTROL" in result["hard_rejections"]


def test_low_quality_choch_without_liquidity_sweep():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": "LIQUIDITY_SWEEP_REVERSAL_SHORT"},
        liquidity_sweep=False,
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
    )
    assert "LOW_QUALITY_CHOCH_NO_LIQUIDITY_SWEEP" in result["hard_rejections"]


def test_rejected_no_displacement():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": "HTF_SUPPLY_REACTION_SHORT"},
        displacement=False,
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
    )
    assert "REJECTED_NO_DISPLACEMENT" in result["hard_rejections"]


def test_rejected_invalid_poi():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": "HTF_SUPPLY_REACTION_SHORT"},
        active_poi={"validity_status": "INVALID"},
    )
    assert "REJECTED_INVALID_POI" in result["hard_rejections"]


def test_missed_trade_no_chase():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": "CONTINUATION_RETRACE_SHORT"},
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
        move_state="MOVE_STARTED_NOT_CHASEABLE",
    )
    assert "MISSED_TRADE_NO_CHASE" in result["hard_rejections"]


def test_bad_rr_wait_for_better_entry():
    result = evaluate_trade_rejections(
        setup_model={"setup_type": "HTF_SUPPLY_REACTION_SHORT"},
        active_poi={"validity_status": "VALID_ACTIVE_SETUP_POI"},
        rr_validation={"status": "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY"},
    )
    assert "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY" in result["hard_rejections"]
