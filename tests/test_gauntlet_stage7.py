import pytest
from smc_desk.dual_lens import reconcile, VisionRead

def test_external_screenshot_vision_read():
    """Stage 7: External Screenshot Test
    Ensure the dual_lens reconciler successfully processes an external vision read
    with external semantic objects (zones) and compares them to the deterministic engine.
    """
    engine_analysis = {
        "trade_plan": {
            "direction": "bullish",
            "selected_poi": {"kind": "fvg", "low": 100.0, "high": 105.0}
        },
        "metrics": {"latest_close": 106.0, "range_low": 90.0, "range_high": 120.0}
    }

    # Vision layer parses external screenshot
    vision_data = VisionRead(
        lens="vision",
        source="claude-opus-external-screenshot",
        observed_bias="bullish",
        structure_quality="clean",
        structure_quality_score=0.9,
        price_location="above_poi",
        key_zones_seen=[{"kind": "fvg", "low": 101.0, "high": 104.0, "note": "External FVG detection"}],
        tradeable_now=True,
        veto=False
    )

    result = reconcile(engine_analysis, vision_data)
    
    assert result["verdict_alignment"] == "strong_agreement"
    assert result["agreement_score"] > 0.5
    assert result["scores"]["zone"] >= 0.4
    assert result["final_verdict"] == "unknown"  # Engine verdict was absent, defaults to unknown

def test_external_screenshot_vision_veto():
    engine_analysis = {
        "trade_plan": {
            "direction": "bullish",
            "selected_poi": {"kind": "fvg", "low": 100.0, "high": 105.0},
            "verdict": "Tradeable"
        },
        "metrics": {"latest_close": 95.0, "range_low": 90.0, "range_high": 120.0}
    }

    vision_data = VisionRead(
        lens="vision",
        source="claude-opus-external-screenshot",
        observed_bias="bearish",
        structure_quality="messy",
        structure_quality_score=0.2,
        key_zones_seen=[],
        tradeable_now=False,
        veto=True,
        veto_reason="Price broke down completely, bearish momentum"
    )

    result = reconcile(engine_analysis, vision_data, vision_authority_mode="active")
    
    assert result["final_verdict"] == "No-Trade (vision veto)"
    assert result["vision"]["veto"] is True
    assert result["scores"]["direction"] == 0.0

