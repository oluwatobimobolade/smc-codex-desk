from __future__ import annotations

from smc_desk.decision.watch_state_engine import evaluate_watch_state


def test_btc_20260627_rejects_66206_supply_as_active_poi():
    hierarchy = {
        "4h": {"external_bias": "bearish"},
        "1h": {
            "external_bias": "bearish",
            "protected_high": "60924.7",
            "protected_low": "58030.0",
            "dealing_range": {
                "range_high": "60924.7",
                "range_low": "58030.0",
            },
        },
    }
    pois = {
        "1h": [
            {
                "poi_id": "BTC_1H_SUPPLY_66206",
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
                "rejection_reason": "Bearish POI sits above the protected high.",
                "protected_high": "60924.7",
                "protected_low": "58030.0",
                "active_range_high": "60924.7",
                "active_range_low": "58030.0",
            }
        ]
    }

    decision = evaluate_watch_state(hierarchy_by_tf=hierarchy, roles={"notes": []}, pois_by_tf=pois)

    assert decision.active_poi is None
    assert decision.final_state in {
        "WATCH_NEW_LOWER_SUPPLY_FORMATION",
        "NO_VALID_ACTIVE_POI_IN_CURRENT_1H_RANGE",
        "REVIEW_REQUIRED_POI_OUTSIDE_PROTECTED_RANGE",
    }
    assert decision.poi_selection["parent_scope_pois"][0]["poi_id"] == "BTC_1H_SUPPLY_66206"
