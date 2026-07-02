from __future__ import annotations

from smc_desk.decision.hybrid_stop_selector import (
    select_hybrid_structural_stop,
    PASS,
    REJECTED_NO_STRUCTURAL_STOP,
    REJECTED_REFINED_STOP_INSIDE_LIQUIDITY,
)


def test_hybrid_stop_aggressive_uses_full_structure():
    result = select_hybrid_structural_stop(
        direction="bearish",
        entry_style="aggressive",
        active_poi={"price_high": "101.0"},
        sweep_extreme="101.5",
        protected_extreme="102.0",
    )
    assert result["status"] == PASS
    assert float(result["stop_loss"]) >= 101.0
    assert result["stop_loss_style"] == "hybrid_structural"


def test_hybrid_stop_confirmed_uses_confirmation_swing():
    result = select_hybrid_structural_stop(
        direction="bearish",
        entry_style="FIVE_MINUTE_REFINEMENT_ALLOWED",
        active_poi={"price_high": "101.0"},
        confirmation_swing="100.8",
    )
    assert result["status"] == PASS
    assert float(result["stop_loss"]) == 100.8


def test_refined_stop_inside_liquidity_rejected():
    result = select_hybrid_structural_stop(
        direction="bearish",
        entry_style="CONFIRMED",
        active_poi={"price_high": "101.0"},
        confirmation_swing="100.5",
        nearby_liquidity=["100.5"],
    )
    assert result["status"] == REJECTED_REFINED_STOP_INSIDE_LIQUIDITY
