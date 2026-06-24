import pytest
from smc_desk.dual_lens import reconcile, VisionRead

def test_deliberately_wrong_overlay_rejection():
    """Stage 8: Deliberately Wrong Overlay Test
    If the vision layer extracts a zone that is shifted by 5 ticks (due to a bad overlay
    or hallucination), it must fail the overlap threshold and get rejected.
    """
    # Engine selects FVG at 100-105
    engine_analysis = {
        "trade_plan": {
            "direction": "bullish",
            "selected_poi": {"kind": "fvg", "low": 100.0, "high": 105.0},
            "verdict": "Tradeable"
        },
        "metrics": {"latest_close": 106.0, "range_low": 90.0, "range_high": 120.0}
    }

    # Vision layer sees the overlay shifted by 5 units (105-110)
    vision_data = VisionRead(
        lens="vision",
        source="claude-opus",
        observed_bias="bullish",
        structure_quality="clean",
        structure_quality_score=0.9,
        price_location="above_poi",
        key_zones_seen=[{"kind": "fvg", "low": 105.0, "high": 110.0, "note": "Shifted FVG"}],
        tradeable_now=True,
        veto=False
    )

    # Reconciliation must catch the mismatch (0% overlap)
    result = reconcile(engine_analysis, vision_data, vision_authority_mode="active")
    
    # Due to 0% overlap, zone_score drops.
    assert result["scores"]["zone"] < 0.4
    
    # Verify the zone conflict was raised
    assert any("Vision did not confirm the engine's selected POI" in c for c in result["conflicts"])

def test_deliberately_wrong_overlay_marginal():
    """If the overlay is shifted by just 1 candle or marginal amount, overlap drops."""
    engine_analysis = {
        "trade_plan": {
            "direction": "bullish",
            "selected_poi": {"kind": "fvg", "low": 100.0, "high": 105.0},
            "verdict": "Tradeable"
        },
        "metrics": {"latest_close": 106.0, "range_low": 90.0, "range_high": 120.0}
    }

    # Shifted slightly: 104-109 (overlap is 1.0 out of 5.0 = 20%)
    vision_data = VisionRead(
        lens="vision",
        source="claude-opus",
        observed_bias="bullish",
        structure_quality="clean",
        structure_quality_score=0.9,
        price_location="above_poi",
        key_zones_seen=[{"kind": "fvg", "low": 104.0, "high": 109.0, "note": "Marginally Shifted FVG"}],
        tradeable_now=True,
        veto=False
    )

    result = reconcile(engine_analysis, vision_data, vision_authority_mode="active")
    
    assert result["scores"]["zone"] == 0.2  # 1.0 / 5.0
    # Requires 0.4 for agreement, so it must fail zone agreement
    assert result["scores"]["zone"] < 0.4

