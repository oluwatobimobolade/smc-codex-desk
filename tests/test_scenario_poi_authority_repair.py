from __future__ import annotations

from smc_desk.perception.causal_poi_authority import build_causal_poi_authority
from smc_desk.perception.poi_lifecycle import build_pois_for_timeframe
from tests.test_causal_poi_authority import _pack


def test_lifecycle_maps_opposing_poi_instead_of_erasing_it() -> None:
    snapshot = {
        "order_blocks": [
            {
                "object_id": "bullish_origin",
                "object_type": "order_block",
                "direction": "bullish",
                "price_low": 95.0,
                "price_high": 97.0,
                "mitigation_status": "untouched",
                "terminal_reason": "none",
                "evidence": {"structure_break_id": "bullish_bos"},
            }
        ],
        "structure_breaks": [],
        "fvgs": [],
    }
    hierarchy = {
        "external_bias": "bearish",
        "protected_high": 110.0,
        "protected_low": 90.0,
        "dealing_range": {"range_low": 90.0, "range_high": 110.0},
    }

    pois = build_pois_for_timeframe(
        timeframe="15m",
        snapshot=snapshot,
        hierarchy=hierarchy,
        current_price=100.0,
    )

    assert len(pois) == 1
    mapped = pois[0].to_dict()
    assert mapped["direction"] == "bullish"
    assert mapped["hierarchy_bias"] == "bearish"
    assert mapped["bias_alignment"] == "opposing"
    assert mapped["validity_status"] == "INVALID_DIRECTION_MISMATCH"


def test_formal_graph_can_reconcile_only_provisional_direction_mismatch() -> None:
    detector, graph = _pack()
    detector["1h"]["pois"] = []
    for active in detector["1h"]["active_pois"]:
        mapped = dict(active)
        mapped["legacy_validity_status"] = mapped["validity_status"]
        mapped["validity_status"] = "INVALID_DIRECTION_MISMATCH"
        mapped["scope"] = "rejected"
        mapped["hierarchy_bias"] = "bullish"
        mapped["bias_alignment"] = "opposing"
        detector["1h"]["pois"].append(mapped)
    detector["1h"]["active_pois"] = []

    result = build_causal_poi_authority(
        detector_candidates=detector,
        formal_structure_graph=graph,
    )

    primary = result["official_selection"]["primary_causal_poi"]
    assert primary["source_object_id"] == "deep_origin"
    assert primary["validity_status"] == "VALID_ACTIVE_SETUP_POI"
    assert primary["scope"] == "active_setup"

