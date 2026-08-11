from __future__ import annotations

from types import SimpleNamespace

from smc_desk.brain.ai_smc_consistency_validator import _resolve_anchor_price


def _decision(direction: str = "bearish") -> SimpleNamespace:
    return SimpleNamespace(
        direction=direction,
        active_range=SimpleNamespace(high=120.0, low=80.0),
        active_poi=SimpleNamespace(price_low=100.0, price_high=110.0),
    )


def test_default_ob_entry_is_midpoint_on_exact_and_semantic_resolution_paths() -> None:
    pack = {
        "detector_candidates": {
            "4h": {
                "order_blocks": [
                    {"object_id": "supply", "price_low": 100.0, "price_high": 110.0}
                ]
            }
        }
    }
    decision = _decision("bearish")

    exact = _resolve_anchor_price("supply", ["supply"], pack, decision, "entry")
    semantic = _resolve_anchor_price("active_poi", [], pack, decision, "entry")

    assert exact == 105.0
    assert semantic == 105.0


def test_named_proximal_and_distal_models_are_direction_aware() -> None:
    pack = {"detector_candidates": {}}

    assert _resolve_anchor_price(
        "active_poi_proximal", [], pack, _decision("bearish"), "entry"
    ) == 100.0
    assert _resolve_anchor_price(
        "active_poi_distal", [], pack, _decision("bearish"), "entry"
    ) == 110.0
    assert _resolve_anchor_price(
        "active_poi_proximal", [], pack, _decision("bullish"), "entry"
    ) == 110.0
    assert _resolve_anchor_price(
        "active_poi_distal", [], pack, _decision("bullish"), "entry"
    ) == 100.0
