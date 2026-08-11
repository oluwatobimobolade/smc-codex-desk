"""Tests for narrative-driven annotation selection.

Pins the rule that a chart is marked in a trader's order -- location first,
then the structure that built the current context -- and that selection stays
an evidence-id-only surface so deterministic code keeps owning geometry.

Two of these tests exist because rendering real BTCUSDT data exposed the
defects: an external break and its internal twin sharing a price stacked two
labels on one line and hid the more important one.
"""
from __future__ import annotations

import pytest

from smc_desk.brain.narrative_annotation_planner import (
    MIN_LABEL_SEPARATION_ATR,
    plan_narrative_annotations,
)
from smc_desk.brain.structure_lab.annotation_bridge import resolve_semantic_annotation_plan


def _candles(n=60, high=63500.0, low=62500.0):
    """Candles giving ATR ~1000, matching real BTC 4H proportions.

    Penetrations in these fixtures are therefore readable directly as ATR
    multiples: 1500 is major, 900 intermediate, 400 minor, 5 noise.
    """
    return [
        {"timestamp": f"2026-06-{(i % 28) + 1:02d}T00:00:00Z",
         "open": 63000.0, "high": high, "low": low, "close": 63200.0}
        for i in range(n)
    ]


def _brk(object_id, price, penetration, *, scope="external", kind="BOS",
         confirmed="2026-06-15T00:00:00Z"):
    return {
        "object_id": object_id,
        "timeframe": "4h",
        "break_type": kind,
        "direction": "bullish",
        "structure_scope": scope,
        "confirmed_at": confirmed,
        "pivot_time": "2026-06-10T00:00:00Z",
        "confirmation_status": "confirmed",
        "evidence": {
            "broken_price": price,
            "body_close_penetration": penetration,
            "is_unconfirmed_probe": False,
            "structure_scope": scope,
        },
    }


def _pack(breaks, *, with_range=True, with_narrative=True):
    graph = {
        "timeframes": {"4h": {"external_bias": "bullish"}},
        "active_range": (
            {"status": "RESOLVED", "range_id": "4h:dr", "timeframe": "4h",
             "low": 62000.0, "high": 66000.0, "equilibrium": 64000.0,
             "price_location": "discount"}
            if with_range else {"status": "UNRESOLVED"}
        ),
    }
    if with_narrative:
        graph["narrative_context"] = {
            "state": "PULLBACK_ENDING", "context_timeframe": "4h",
            "context_bias": "bullish", "is_coherent": True,
            "sentence": "4h is bullish; 1h is rolling back over.",
        }
    return {
        "ohlcv_windows": {"4h": _candles()},
        "detector_candidates": {"4h": {"structure_breaks": breaks}},
        "formal_structure_graph": graph,
    }


# -- ordering: location before structure --------------------------------------


def test_range_is_selected_first():
    """A trader reads location before structure, so the range is drawn first."""
    plan = plan_narrative_annotations(evidence_pack=_pack([_brk("b1", 63500.0, 900.0)]))
    assert plan["selections"][0]["object_type"] == "range_zone"
    assert any("Range drawn first" in r for r in plan["rationale"])


def test_structure_follows_the_range():
    plan = plan_narrative_annotations(evidence_pack=_pack([_brk("b1", 63500.0, 900.0)]))
    types = [s["object_type"] for s in plan["selections"]]
    assert types == ["range_zone", "structure_segment"]


def test_authority_selected_primary_poi_is_drawn_and_resolves_to_detector_geometry():
    pack = _pack([_brk("b1", 63500.0, 900.0)])
    pack["detector_candidates"]["4h"]["order_blocks"] = [{
        "object_id": "ob-primary",
        "timeframe": "4h",
        "direction": "bullish",
        "pivot_time": "2026-06-12T00:00:00Z",
        "candidate_at": "2026-06-12T00:00:00Z",
        "confirmed_at": "2026-06-13T00:00:00Z",
        "confirmation_status": "confirmed",
        "activity_status": "active",
        "mitigation_status": "untouched",
        "price_low": 62500.0,
        "price_high": 63000.0,
        "evidence": {"poi_grade": True, "caused_structure_break": True},
    }]
    pack["causal_poi_authority"] = {
        "scenarios": {
            "bullish": {
                "status": "SELECTED",
                "controlling_timeframe": "4h",
                "primary_causal_poi": {
                    "poi_id": "4h:order_block:ob-primary",
                    "source_object_id": "ob-primary",
                    "timeframe": "4h",
                    "kind": "order_block",
                    "direction": "bullish",
                    "price_low": 62500.0,
                    "price_high": 63000.0,
                    "freshness": "fresh",
                    "causal_status": "ELIGIBLE_CAUSAL_OB",
                    "causal_certificate": {"status": "PASS"},
                    "primary_reason": "Owns the accepted external break lineage.",
                },
            }
        }
    }

    plan = plan_narrative_annotations(evidence_pack=pack)
    poi = next(item for item in plan["selections"] if item["object_type"] == "poi_zone")
    assert poi["semantic_object_id"] == "ob-primary"
    assert "price_low" not in poi and "price_high" not in poi

    resolution = resolve_semantic_annotation_plan(plan, pack)
    assert resolution["status"] == "PASS", resolution["issues"]
    resolved = next(
        item for item in resolution["annotation_plan_v2"]["objects"]
        if item["object_type"] == "poi_zone"
    )
    assert resolved["price_low"] == pytest.approx(62500.0)
    assert resolved["price_high"] == pytest.approx(63000.0)


def test_spent_or_noncausal_authority_primary_is_not_drawn():
    pack = _pack([_brk("b1", 63500.0, 900.0)])
    pack["detector_candidates"]["4h"]["order_blocks"] = [{
        "object_id": "ob-rejected", "timeframe": "4h", "direction": "bullish",
        "pivot_time": "2026-06-12T00:00:00Z", "confirmed_at": "2026-06-13T00:00:00Z",
        "confirmation_status": "confirmed", "price_low": 62500.0, "price_high": 63000.0,
    }]
    pack["causal_poi_authority"] = {"scenarios": {"bullish": {
        "status": "SELECTED",
        "primary_causal_poi": {
            "poi_id": "4h:order_block:ob-rejected", "source_object_id": "ob-rejected",
            "timeframe": "4h", "kind": "order_block", "direction": "bullish",
            "price_low": 62500.0, "price_high": 63000.0, "freshness": "invalidated",
            "causal_status": "REJECTED_CAUSAL_ORIGIN_GATE",
            "causal_certificate": {"status": "FAIL"},
        },
    }}}

    plan = plan_narrative_annotations(evidence_pack=pack)

    assert not any(item["object_type"] == "poi_zone" for item in plan["selections"])
    assert any("failed the shared causal/lifecycle contract" in item for item in plan["rationale"])


# -- the two defects real rendering exposed -----------------------------------


def test_internal_twin_sharing_a_price_is_dropped():
    """External structure owns the story; a co-located internal twin is noise.

    Rendering real BTC data produced '4H BOS' and '4H Internal BOS' at the
    identical price, stacking labels and hiding the external one.
    """
    breaks = [
        _brk("ext", 64738.0, 900.0, scope="external"),
        _brk("int", 64738.0, 900.0, scope="internal"),
    ]
    plan = plan_narrative_annotations(evidence_pack=_pack(breaks))
    ids = [s["semantic_object_id"] for s in plan["selections"]]
    assert "ext" in ids
    assert "int" not in ids
    assert any("duplicates external structure" in r for r in plan["rationale"])


def test_marks_too_close_together_are_dropped():
    """Two marks inside the label-separation floor render as one."""
    breaks = [
        _brk("strong", 63500.0, 1500.0),
        _brk("weak_nearby", 63505.0, 900.0),
    ]
    plan = plan_narrative_annotations(evidence_pack=_pack(breaks))
    ids = [s["semantic_object_id"] for s in plan["selections"]]
    assert "strong" in ids
    assert "weak_nearby" not in ids


def test_separated_marks_both_survive():
    breaks = [
        _brk("low_level", 62500.0, 1500.0),
        _brk("high_level", 65500.0, 1500.0),
    ]
    plan = plan_narrative_annotations(evidence_pack=_pack(breaks))
    ids = {s["semantic_object_id"] for s in plan["selections"]}
    assert {"low_level", "high_level"} <= ids


# -- ranking and budget --------------------------------------------------------


def test_strongest_structure_wins_when_capped():
    breaks = [
        _brk("weak", 62200.0, 400.0),
        _brk("strongest", 63500.0, 2000.0),
        _brk("middle", 65000.0, 1000.0),
    ]
    plan = plan_narrative_annotations(evidence_pack=_pack(breaks), structure_limit=1)
    structure = [s for s in plan["selections"] if s["object_type"] == "structure_segment"]
    assert len(structure) == 1
    assert structure[0]["semantic_object_id"] == "strongest"


def test_insignificant_structure_is_never_drawn():
    """A marginal poke must not reach the chart even with budget to spare."""
    plan = plan_narrative_annotations(evidence_pack=_pack([_brk("poke", 63500.0, 5.0)]))
    assert [s["object_type"] for s in plan["selections"]] == ["range_zone"]


def test_selection_respects_the_clutter_budget():
    breaks = [_brk(f"b{i}", 62000.0 + i * 800, 1500.0) for i in range(8)]
    plan = plan_narrative_annotations(
        evidence_pack=_pack(breaks), structure_limit=8, clutter_budget=3
    )
    assert len(plan["selections"]) <= 3


# -- fail-closed behaviour -----------------------------------------------------


def test_no_narrative_means_no_selections():
    plan = plan_narrative_annotations(evidence_pack=_pack([], with_narrative=False))
    assert plan["selections"] == []
    assert plan["rationale"]


def test_unresolved_range_still_allows_structure():
    """A missing range must not suppress the rest of the story."""
    plan = plan_narrative_annotations(
        evidence_pack=_pack([_brk("b1", 63500.0, 1500.0)], with_range=False)
    )
    types = [s["object_type"] for s in plan["selections"]]
    assert "range_zone" not in types
    assert "structure_segment" in types


def test_planner_emits_ids_only_never_geometry():
    """The planner must not be able to supply a price or timestamp."""
    plan = plan_narrative_annotations(evidence_pack=_pack([_brk("b1", 63500.0, 1500.0)]))
    forbidden = {"price", "price_low", "price_high", "equilibrium_price",
                 "start_index", "end_index", "start_time", "end_time"}
    for selection in plan["selections"]:
        assert not (forbidden & set(selection)), f"planner leaked geometry: {selection}"


def test_planner_creates_no_authority():
    plan = plan_narrative_annotations(evidence_pack=_pack([_brk("b1", 63500.0, 1500.0)]))
    assert plan["signal_allowed"] is False
    assert plan["authority"] == "observe_only_narrative_selection"


# -- integration with the certified bridge ------------------------------------


def test_plan_resolves_cleanly_through_the_bridge():
    pack = _pack([_brk("b1", 63500.0, 1500.0)])
    plan = plan_narrative_annotations(evidence_pack=pack)
    resolution = resolve_semantic_annotation_plan(plan, pack)
    assert resolution["status"] == "PASS", resolution["issues"]
    assert resolution["resolved_object_count"] == resolution["planned_selection_count"]
    assert resolution["ai_geometry_authority"] is False
    # Equilibrium still derived by the bridge, not the planner.
    ranges = [o for o in resolution["annotation_plan_v2"]["objects"]
              if o["object_type"] == "range_zone"]
    assert ranges and ranges[0]["equilibrium_price"] == pytest.approx(64000.0)
