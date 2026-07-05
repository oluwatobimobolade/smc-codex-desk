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


def test_deeper_bullish_order_block_outranks_shallow_inducement_and_fvg():
    pois = {
        "15m": [
            {
                "poi_id": "nearest_shallow_ob",
                "kind": "demand",
                "created_by": "order_block",
                "timeframe": "15m",
                "direction": "bullish",
                "price_low": "0.7383",
                "price_high": "0.7416",
                "freshness": "fresh",
                "price_relation": "above_poi",
                "quality_score": 0.82,
                "current_price": "0.7500",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
                "scope": "active_setup",
            },
            {
                "poi_id": "fvg_between_price_and_ob",
                "kind": "fvg",
                "created_by": "fvg",
                "timeframe": "15m",
                "direction": "bullish",
                "price_low": "0.7320",
                "price_high": "0.7348",
                "freshness": "fresh",
                "price_relation": "above_poi",
                "quality_score": 0.90,
                "current_price": "0.7500",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
                "scope": "active_setup",
            },
            {
                "poi_id": "deeper_origin_ob",
                "kind": "demand",
                "created_by": "order_block",
                "timeframe": "15m",
                "direction": "bullish",
                "price_low": "0.7288",
                "price_high": "0.7316",
                "freshness": "fresh",
                "price_relation": "above_poi",
                "quality_score": 0.80,
                "current_price": "0.7500",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
                "scope": "active_setup",
            },
        ]
    }

    selection = build_poi_selection(pois, direction="bullish")
    ranked = selection["current_range_pois"]
    by_id = {item["poi_id"]: item for item in ranked}

    assert selection["selected_active_poi"]["poi_id"] == "deeper_origin_ob"
    assert by_id["deeper_origin_ob"]["reaction_role"] == "deeper_order_block_reaction_candidate"
    assert by_id["nearest_shallow_ob"]["reaction_role"] == "front_inducement_risk"
    assert by_id["nearest_shallow_ob"]["deeper_reaction_poi_id"] == "deeper_origin_ob"
    assert by_id["fvg_between_price_and_ob"]["reaction_role"] == "fvg_path_to_deeper_order_block"


def test_deeper_bearish_supply_outranks_nearest_shallow_supply():
    pois = {
        "15m": [
            {
                "poi_id": "nearest_shallow_supply",
                "kind": "supply",
                "created_by": "order_block",
                "timeframe": "15m",
                "direction": "bearish",
                "price_low": "104.0",
                "price_high": "105.0",
                "freshness": "fresh",
                "price_relation": "below_poi",
                "quality_score": 0.84,
                "current_price": "100.0",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
                "scope": "active_setup",
            },
            {
                "poi_id": "deeper_supply_origin",
                "kind": "supply",
                "created_by": "order_block",
                "timeframe": "15m",
                "direction": "bearish",
                "price_low": "110.0",
                "price_high": "112.0",
                "freshness": "fresh",
                "price_relation": "below_poi",
                "quality_score": 0.80,
                "current_price": "100.0",
                "validity_status": "VALID_ACTIVE_SETUP_POI",
                "scope": "active_setup",
            },
        ]
    }

    selection = build_poi_selection(pois, direction="bearish")
    by_id = {item["poi_id"]: item for item in selection["current_range_pois"]}

    assert selection["selected_active_poi"]["poi_id"] == "deeper_supply_origin"
    assert by_id["nearest_shallow_supply"]["reaction_role"] == "front_inducement_risk"
    assert by_id["deeper_supply_origin"]["reaction_role"] == "deeper_order_block_reaction_candidate"
