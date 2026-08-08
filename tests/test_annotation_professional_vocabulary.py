"""Tests for the professional SMC annotation vocabulary.

The 2026-07-17 BTCUSDT run had 6,591 evidence objects available, a resolved
4H dealing range, price in premium and two POI candidates -- and drew exactly
one object, a 15m Internal CHoCH. Part of that was refusal state, but part was
structural: the plan schema had no way to express a dealing range, a sweep, or
an equal-highs pool, so those could never be drawn even when known.

These tests pin the added vocabulary and, critically, that adding it did not
weaken the fail-closed contract: the AI still selects only certified evidence
IDs and deterministic code still owns every coordinate.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from smc_desk.brain.ai_smc_trader_brain import AnnotationDrawingObject, AnnotationPlanV2
from smc_desk.brain.structure_lab.annotation_bridge import resolve_semantic_annotation_plan


def _range_object(**overrides):
    payload = {
        "object_type": "range_zone",
        "semantic_object_id": "4h:dr:65589.7:61806.0",
        "timeframe": "4h",
        "label": "4H Dealing Range",
        "reason": "Active range governing current premium/discount location.",
        "kind": "range",
        "direction": "bearish",
        "price_low": 61806.0,
        "price_high": 65589.7,
        "equilibrium_price": 63697.85,
        "start_index": 0,
        "end_index": 119,
        "start_time": "2026-07-01T00:00:00Z",
        "end_time": "2026-07-17T12:00:00Z",
    }
    payload.update(overrides)
    return payload


# -- schema -------------------------------------------------------------------


def test_range_zone_is_a_valid_annotation_object():
    obj = AnnotationDrawingObject.model_validate(_range_object())
    assert obj.object_type == "range_zone"
    assert obj.equilibrium_price == pytest.approx(63697.85)


def test_range_zone_requires_equilibrium():
    with pytest.raises(ValidationError):
        AnnotationDrawingObject.model_validate(_range_object(equilibrium_price=None))


def test_range_equilibrium_must_sit_inside_the_range():
    with pytest.raises(ValidationError):
        AnnotationDrawingObject.model_validate(_range_object(equilibrium_price=70000.0))


def test_range_kind_is_reserved_for_range_zone():
    with pytest.raises(ValidationError):
        AnnotationDrawingObject.model_validate(
            _range_object(object_type="poi_zone", kind="range")
        )


def test_sweep_marker_and_equal_levels_validate():
    sweep = AnnotationDrawingObject.model_validate({
        "object_type": "sweep_marker", "semantic_object_id": "sweep_1", "timeframe": "1h",
        "label": "Sweep", "reason": "Sell-side liquidity taken before reversal.",
        "kind": "sweep", "direction": "bearish", "price": 61800.0,
        "start_index": 40, "end_index": 43,
        "start_time": "2026-07-10T00:00:00Z", "end_time": "2026-07-10T03:00:00Z",
    })
    assert sweep.object_type == "sweep_marker"

    eq = AnnotationDrawingObject.model_validate({
        "object_type": "equal_levels", "semantic_object_id": "eql_1", "timeframe": "1h",
        "label": "EQL", "reason": "Equal lows forming a sell-side pool.",
        "kind": "equal_lows", "direction": "bullish", "price": 61806.0,
        "start_index": 10, "end_index": 60,
        "start_time": "2026-07-05T00:00:00Z", "end_time": "2026-07-12T00:00:00Z",
    })
    assert eq.kind == "equal_lows"


def test_sweep_marker_rejects_wrong_kind():
    with pytest.raises(ValidationError):
        AnnotationDrawingObject.model_validate({
            "object_type": "sweep_marker", "semantic_object_id": "s", "timeframe": "1h",
            "label": "x", "reason": "y", "kind": "bos", "price": 1.0,
            "start_index": 1, "end_index": 2,
            "start_time": "a", "end_time": "b",
        })


def test_plan_accepts_a_full_professional_object_set():
    plan = AnnotationPlanV2.model_validate({
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": [_range_object()],
        "notes": [],
    })
    assert len(plan.objects) == 1


# -- bridge: deterministic geometry still owns every coordinate ---------------


def _evidence_pack():
    candles = [
        {"timestamp": f"2026-07-{(i % 28) + 1:02d}T00:00:00Z",
         "open": 63000.0, "high": 63500.0, "low": 62500.0, "close": 63200.0}
        for i in range(40)
    ]
    return {
        "ohlcv_windows": {"4h": candles, "1h": candles},
        "formal_structure_graph": {
            "active_range": {
                "range_id": "4h:dr", "timeframe": "4h", "direction": "bearish",
                "low": 61806.0, "high": 65589.7,
            }
        },
        "detector_candidates": {
            "1h": {
                "liquidity_levels": [{
                    "object_id": "eql_pool", "timeframe": "1h", "direction": "bullish",
                    "price": 61806.0, "price_low": 61806.0, "price_high": 61806.0,
                    "pivot_time": "2026-07-05T00:00:00Z",
                    "confirmed_at": "2026-07-06T00:00:00Z",
                    "confirmation_status": "confirmed",
                }],
            },
        },
    }


def test_bridge_resolves_range_from_certified_evidence_and_derives_equilibrium():
    """The planner supplies an ID only; the bridge computes the geometry."""
    resolution = resolve_semantic_annotation_plan(
        {
            "clutter_budget": 5,
            "selections": [{
                "semantic_object_id": "4h:dr", "timeframe": "4h",
                "object_type": "range_zone", "label": "4H Dealing Range",
                "reason": "Governing range for current location.",
            }],
        },
        _evidence_pack(),
    )
    assert resolution["status"] == "PASS", resolution["issues"]
    obj = resolution["annotation_plan_v2"]["objects"][0]
    assert obj["object_type"] == "range_zone"
    assert obj["price_low"] == 61806.0 and obj["price_high"] == 65589.7
    # Equilibrium derived by deterministic code, never supplied by the planner.
    assert obj["equilibrium_price"] == pytest.approx((61806.0 + 65589.7) / 2)


def test_bridge_spans_the_range_across_the_visible_window():
    resolution = resolve_semantic_annotation_plan(
        {"clutter_budget": 5, "selections": [{
            "semantic_object_id": "4h:dr", "timeframe": "4h",
            "object_type": "range_zone", "label": "R", "reason": "context",
        }]},
        _evidence_pack(),
    )
    obj = resolution["annotation_plan_v2"]["objects"][0]
    assert obj["start_index"] == 0 and obj["end_index"] == 39


def test_bridge_resolves_equal_levels_from_liquidity_evidence():
    resolution = resolve_semantic_annotation_plan(
        {"clutter_budget": 5, "selections": [{
            "semantic_object_id": "eql_pool", "timeframe": "1h",
            "object_type": "equal_levels", "label": "EQL",
            "reason": "Sell-side pool below price.",
        }]},
        _evidence_pack(),
    )
    assert resolution["status"] == "PASS", resolution["issues"]
    obj = resolution["annotation_plan_v2"]["objects"][0]
    assert obj["object_type"] == "equal_levels"
    assert obj["price"] == 61806.0


def test_range_selection_without_certified_range_fails_closed():
    """A range cannot be conjured from a swing; the bridge must refuse."""
    resolution = resolve_semantic_annotation_plan(
        {"clutter_budget": 5, "selections": [{
            "semantic_object_id": "eql_pool", "timeframe": "1h",
            "object_type": "range_zone", "label": "fake range", "reason": "invented",
        }]},
        _evidence_pack(),
    )
    assert resolution["status"] == "REVIEW_REQUIRED"
    assert any(i["code"] == "range_selection_without_certified_range"
               for i in resolution["issues"])


def test_unknown_evidence_id_still_fails_closed_for_new_types():
    resolution = resolve_semantic_annotation_plan(
        {"clutter_budget": 5, "selections": [{
            "semantic_object_id": "ghost", "timeframe": "4h",
            "object_type": "range_zone", "label": "x", "reason": "y",
        }]},
        _evidence_pack(),
    )
    assert resolution["status"] == "REVIEW_REQUIRED"
    assert any(i["code"] == "unresolved_semantic_object" for i in resolution["issues"])
    assert resolution["ai_geometry_authority"] is False


# -- renderer -----------------------------------------------------------------


def test_renderer_draws_every_new_object_type():
    """Each new type must actually render; a silent no-draw would break the
    render-before-critic contract that requires every planned object to appear.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from smc_desk.rendering.structure_lab_annotation_renderer import _draw_object

    fig, ax = plt.subplots()
    try:
        assert _draw_object(ax, _range_object(end_index=39), 40, 4000.0) is True
        assert _draw_object(ax, {
            "object_type": "sweep_marker", "kind": "sweep", "direction": "bearish",
            "price": 61800.0, "start_index": 10, "end_index": 12, "label": "Sweep",
        }, 40, 4000.0) is True
        assert _draw_object(ax, {
            "object_type": "equal_levels", "kind": "equal_lows", "direction": "bullish",
            "price": 61806.0, "start_index": 5, "end_index": 30, "label": "EQL",
        }, 40, 4000.0) is True
    finally:
        plt.close(fig)


def test_renderer_refuses_range_without_equilibrium():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from smc_desk.rendering.structure_lab_annotation_renderer import _draw_object

    fig, ax = plt.subplots()
    try:
        obj = _range_object(end_index=39)
        obj.pop("equilibrium_price")
        assert _draw_object(ax, obj, 40, 4000.0) is False
    finally:
        plt.close(fig)
