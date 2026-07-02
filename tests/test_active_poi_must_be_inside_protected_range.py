from __future__ import annotations

from smc_desk.perception.poi_lifecycle import build_poi_selection, classify_poi_scope


def test_bearish_active_poi_must_not_sit_above_protected_high():
    result = classify_poi_scope(
        {"kind": "supply", "direction": "bearish", "price_low": "66206.6", "price_high": "66388.8"},
        external_bias="bearish",
        protected_high="60924.7",
        protected_low="58030.0",
        current_price="60272.8",
        active_range_high="60924.7",
        active_range_low="58030.0",
    )

    assert result["validity_status"] == "PARENT_SCOPE_POI"
    assert result["scope"] == "parent_scope"
    assert "protected high" in result["rejection_reason"]


def test_validity_outranks_timeframe_and_freshness():
    pois = {
        "1h": [
            {
                "poi_id": "far_fresh_1h",
                "kind": "supply",
                "timeframe": "1h",
                "direction": "bearish",
                "price_low": "66206.6",
                "price_high": "66388.8",
                "freshness": "fresh",
                "price_relation": "below_poi",
                "quality_score": 1.0,
                "current_price": "60272.8",
                "validity_status": "PARENT_SCOPE_POI",
                "scope": "parent_scope",
                "rejection_reason": "above protected high",
            },
            {
                "poi_id": "valid_lower_1h",
                "kind": "supply",
                "timeframe": "1h",
                "direction": "bearish",
                "price_low": "60420.0",
                "price_high": "60880.0",
                "freshness": "partial",
                "price_relation": "below_poi",
                "quality_score": 0.4,
                "current_price": "60272.8",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
                "scope": "active_setup",
                "rejection_reason": None,
            },
        ]
    }

    selection = build_poi_selection(pois, direction="bearish")

    assert selection["selected_active_poi"]["poi_id"] == "valid_lower_1h"
    assert selection["parent_scope_pois"][0]["poi_id"] == "far_fresh_1h"
    assert selection["status"] == "SELECTED_ACTIVE_POI"
