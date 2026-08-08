from __future__ import annotations

from smc_desk.brain.annotation_candidate_composer import select_local_active_poi
from smc_desk.perception.causal_poi_authority import build_causal_poi_authority


def _break(
    object_id: str,
    when: str,
    *,
    direction: str = "bearish",
    choch: bool = False,
    protected: bool = False,
) -> dict:
    return {
        "object_id": object_id,
        "direction": direction,
        "confirmed_at": when,
        "break_type": "CHOCH" if choch else "BOS",
        "structure_scope": "external",
        "evidence": {
            "structure_scope": "external",
            "broke_protected_swing": protected,
            "valid_choch": choch and protected,
            "displacement_strength": 0.9 if choch else 0.8,
        },
    }


def _ob(object_id: str, break_id: str, low: float, high: float, *, causal: bool = True) -> dict:
    return {
        "object_id": object_id,
        "object_type": "order_block",
        "timeframe": "1h",
        "direction": "bearish",
        "price_low": low,
        "price_high": high,
        "pivot_time": "2026-07-09T04:00:00Z",
        "confirmed_at": "2026-07-10T12:00:00Z",
        "source_candle_ids": [f"{object_id}:origin", f"{object_id}:departure"],
        "evidence": {
            "structure_break_id": break_id,
            "body_ratio": 0.72,
            "originating_fvg_id": "fvg_support" if object_id == "deep_origin" else None,
        },
        "metadata": {
            "causal_link_method": "explicit_break_departure_trace" if causal else "nearest_opposing_candle",
            "origin_geometry": "multi_candle_cluster",
            "origin_cluster_candle_ids": [f"{object_id}:origin"],
            "departure_candle_ids": [f"{object_id}:departure"],
        },
    }


def _fvg(object_id: str, break_id: str, low: float, high: float, *, causal: bool = True) -> dict:
    return {
        "object_id": object_id,
        "object_type": "fvg",
        "timeframe": "1h",
        "direction": "bearish",
        "price_low": low,
        "price_high": high,
        "pivot_time": "2026-07-10T10:00:00Z",
        "confirmed_at": "2026-07-10T13:00:00Z",
        "source_candle_ids": [f"{object_id}:impulse"],
        "evidence": {
            "origin_break_id": break_id,
            "location_context": "causal_impulse_overlap" if causal else "structure_break_displacement_origin",
        },
        "metadata": {
            "causal_link_method": "break_source_candle_overlap" if causal else "time_proximity",
        },
    }


def _active(source_id: str, kind: str, low: float, high: float) -> dict:
    return {
        "poi_id": f"BTCUSDT:1h:{kind}:{source_id}",
        "created_by": kind,
        "timeframe": "1h",
        "direction": "bearish",
        "price_low": low,
        "price_high": high,
        "freshness": "fresh",
        "price_relation": "above_price",
        "validity_status": "VALID_ACTIVE_SETUP_POI",
        "scope": "active_setup",
    }


def _pack(*, old_geometry: bool = False, temporal_fvg: bool = False, outside: bool = False) -> tuple[dict, dict]:
    reversal = _break("choch_origin", "2026-07-09T08:00:00Z", choch=True, protected=True)
    latest = _break("bos_latest", "2026-07-10T16:00:00Z")
    deep_low, deep_high = ((111.0, 113.0) if outside else (106.0, 108.0))
    deep = _ob("deep_origin", "choch_origin", deep_low, deep_high, causal=not old_geometry)
    shallow = _ob("shallow_continuation", "bos_latest", 102.0, 104.0)
    fvg = _fvg("fvg_support", "bos_latest", 103.0, 104.0, causal=not temporal_fvg)
    detector = {
        "1h": {
            "poi_lifecycle_contract": [{"available": True}],
            "structure_breaks": [reversal, latest],
            "order_blocks": [deep, shallow],
            "fvgs": [fvg],
            "poi_grade_fvgs": [fvg],
            "active_pois": [
                _active("deep_origin", "order_block", deep_low, deep_high),
                _active("shallow_continuation", "order_block", 102.0, 104.0),
                _active("fvg_support", "fvg", 103.0, 104.0),
            ],
        }
    }
    graph = {
        "timeframes": {
            "1h": {
                "external_bias": "bearish",
                "latest_external_break": {"object_id": "bos_latest"},
            }
        },
        "parent_child_context": {"has_conflict": False, "aligned_bias": "bearish"},
        "active_range": {
            "status": "RESOLVED",
            "timeframe": "1h",
            "low": 90.0,
            "high": 110.0,
            "equilibrium": 100.0,
        },
    }
    return detector, graph


def test_protected_reversal_origin_outranks_shallow_latest_ob_for_causal_reason() -> None:
    detector, graph = _pack()
    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    primary = result["official_selection"]["primary_causal_poi"]
    assert primary["source_object_id"] == "deep_origin"
    assert primary["lineage_role"] == "protected_reversal_origin"
    assert result["timeframes"]["1h"]["pairwise_decisions"][0]["reasons"] == [
        "winner_has_stronger_causal_lineage_role"
    ]
    assert result["authority_contract"]["reaction_guaranteed"] is False


def test_fvg_remains_supporting_when_causal_ob_exists() -> None:
    detector, graph = _pack()
    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    secondaries = result["timeframes"]["1h"]["secondary_reaction_pois"]
    fvg = next(item for item in secondaries if item["source_object_id"] == "fvg_support")
    assert fvg["poi_role"] == "supporting_fvg"
    assert "fvg_is_supporting_unless_no_causal_ob_exists" in fvg["lost_to_primary_reasons"]


def test_nearest_opposing_candle_geometry_is_not_causal_authority() -> None:
    detector, graph = _pack(old_geometry=True)
    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    unresolved = result["timeframes"]["1h"]["unresolved_candidates"]
    deep = next(item for item in unresolved if item["source_object_id"] == "deep_origin")
    assert deep["causal_status"] == "UNRESOLVED_GEOMETRIC_OB_ONLY"


def test_temporal_fvg_proximity_is_not_causal_membership() -> None:
    detector, graph = _pack(temporal_fvg=True)
    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    unresolved = result["timeframes"]["1h"]["unresolved_candidates"]
    fvg = next(item for item in unresolved if item["source_object_id"] == "fvg_support")
    assert fvg["causal_status"] == "UNRESOLVED_TEMPORAL_FVG_LINK"


def test_external_origin_beyond_newer_nested_range_remains_eligible() -> None:
    detector, graph = _pack(outside=True)
    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    primary = result["official_selection"]["primary_causal_poi"]
    assert primary["source_object_id"] == "deep_origin"
    assert primary["range_relationship"] == "accepted_external_origin_beyond_newer_nested_range"
    assert primary["causal_certificate"]["status"] == "PASS"


def test_wrong_side_outside_candidate_is_still_not_promoted() -> None:
    detector, graph = _pack()
    deep_raw = next(item for item in detector["1h"]["order_blocks"] if item["object_id"] == "deep_origin")
    deep_raw["price_low"], deep_raw["price_high"] = 80.0, 82.0
    deep_active = next(item for item in detector["1h"]["active_pois"] if item["poi_id"].endswith("deep_origin"))
    deep_active["price_low"], deep_active["price_high"] = 80.0, 82.0

    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    unresolved = result["timeframes"]["1h"]["unresolved_candidates"]
    deep = next(item for item in unresolved if item["source_object_id"] == "deep_origin")
    assert deep["causal_status"] == "UNRESOLVED_OUTSIDE_ACTIVE_RANGE"
    assert deep["range_relationship"] == "outside_without_external_origin_authority"


def test_annotation_selector_uses_causal_authority_instead_of_nearest_zone() -> None:
    detector, graph = _pack()
    authority = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)
    selected = select_local_active_poi(
        evidence_pack={"causal_poi_authority": authority},
        direction="bearish",
        active_range={},
    )

    assert selected is not None
    assert selected["poi_id"].endswith(":deep_origin")
    assert "deep_origin" in selected["evidence_object_ids"]
    assert "not a guaranteed reaction" in selected["summary"]


def test_internal_break_origin_cannot_become_primary_external_poi() -> None:
    detector, graph = _pack()
    for brk in detector["1h"]["structure_breaks"]:
        brk["structure_scope"] = "internal"
        brk["evidence"]["structure_scope"] = "internal"
    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    assert result["timeframes"]["1h"]["status"] == "UNRESOLVED"
    internal = result["timeframes"]["1h"]["internal_reaction_candidates"]
    assert internal
    assert all(item["causal_status"] == "SECONDARY_INTERNAL_REACTION_CANDIDATE" for item in internal)


def test_standalone_fvg_is_blocked_while_order_block_lineage_is_unresolved() -> None:
    detector, graph = _pack()
    internal = _break("internal_choch", "2026-07-10T14:00:00Z", choch=True)
    internal["structure_scope"] = "internal"
    internal["evidence"]["structure_scope"] = "internal"
    detector["1h"]["structure_breaks"].append(internal)
    for ob in detector["1h"]["order_blocks"]:
        ob["evidence"]["structure_break_id"] = "internal_choch"

    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    timeframe = result["timeframes"]["1h"]
    assert timeframe["status"] == "UNRESOLVED"
    assert timeframe["reason"] == "FVG_PRIMARY_BLOCKED_BY_UNRESOLVED_OB_LINEAGE"
    assert any(
        item["causal_status"] == "UNRESOLVED_FVG_PRIMARY_BLOCKED_BY_OB_LINEAGE"
        for item in timeframe["unresolved_candidates"]
    )


def test_duplicate_origin_lineages_prefer_external_break_and_deeper_ob() -> None:
    external = _break("4h_external_bos", "2026-07-08T20:00:00Z", direction="bullish")
    internal = _break("4h_internal_bos", "2026-07-08T20:00:00Z", direction="bullish")
    internal["structure_scope"] = "internal"
    internal["evidence"]["structure_scope"] = "internal"
    deep_external = _ob("deep_origin", "4h_external_bos", 1.332445, 1.336988)
    deep_external["pivot_time"] = "2026-07-08T08:00:00Z"
    deep_external["direction"] = "bullish"
    deep_external["timeframe"] = "4h"
    deep_internal = _ob("deep_origin", "4h_internal_bos", 1.332445, 1.336988)
    deep_internal["pivot_time"] = "2026-07-08T08:00:00Z"
    deep_internal["direction"] = "bullish"
    deep_internal["timeframe"] = "4h"
    shallow = _ob("shallow_internal", "4h_internal_bos", 1.338652, 1.342138)
    shallow["pivot_time"] = "2026-07-08T12:00:00Z"
    shallow["direction"] = "bullish"
    shallow["timeframe"] = "4h"

    def active(source: str, low: float, high: float) -> dict:
        item = _active(source, "order_block", low, high)
        item["direction"] = "bullish"
        item["timeframe"] = "4h"
        item["poi_id"] = f"GBPUSD:4h:order_block:{source}"
        return item

    detector = {
        "4h": {
            "poi_lifecycle_contract": [{"available": True}],
            "structure_breaks": [external, internal],
            "order_blocks": [deep_external, deep_internal, shallow],
            "fvgs": [],
            "poi_grade_fvgs": [],
            "active_pois": [
                active("deep_origin", 1.332445, 1.336988),
                active("shallow_internal", 1.338652, 1.342138),
            ],
            "pois": [],
        }
    }
    graph = {
        "timeframes": {"4h": {"external_bias": "bullish", "latest_external_break": {"object_id": "4h_external_bos"}}},
        "parent_child_context": {"has_conflict": False, "aligned_bias": "bullish"},
        "active_range": {"status": "RESOLVED", "timeframe": "4h", "low": 1.338151, "high": 1.345153, "equilibrium": 1.341652},
    }

    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    primary = result["official_selection"]["primary_causal_poi"]
    assert primary["source_object_id"] == "deep_origin"
    assert primary["linked_break_id"] == "4h_external_bos"
    assert set(primary["linked_break_ids"]) == {"4h_external_bos", "4h_internal_bos"}
    assert primary["owns_latest_external_break"] is True
    assert primary["range_relationship"] == "accepted_external_origin_beyond_newer_nested_range"
    assert primary["causal_certificate"]["status"] == "PASS"
    shallow_secondary = next(
        item for item in result["timeframes"]["4h"]["secondary_reaction_pois"]
        if item["source_object_id"] == "shallow_internal"
    )
    assert shallow_secondary["causal_status"] == "SECONDARY_INTERNAL_REACTION_CANDIDATE"


def test_parent_scope_child_obs_refine_external_primary_without_owning_it() -> None:
    detector, graph = _pack(outside=True)
    graph["active_range"]["timeframe"] = "1h"
    deep = next(item for item in detector["1h"]["order_blocks"] if item["object_id"] == "deep_origin")
    deep["price_low"], deep["price_high"] = 111.0, 118.0
    active = next(item for item in detector["1h"]["active_pois"] if item["poi_id"].endswith("deep_origin"))
    active["price_low"], active["price_high"] = 111.0, 118.0

    child_break = _break("15m_internal_bull", "2026-07-10T12:00:00Z", direction="bearish")
    child_break["direction"] = "bearish"
    child_ob = _ob("child_refinement", "15m_internal_bull", 113.0, 115.0)
    child_ob["direction"] = "bearish"
    child_ob["timeframe"] = "15m"
    detector["15m"] = {
        "poi_lifecycle_contract": [{"available": True}],
        "structure_breaks": [child_break],
        "order_blocks": [child_ob],
        "fvgs": [],
        "poi_grade_fvgs": [],
        "active_pois": [],
        "pois": [{
            "poi_id": "BTCUSDT:15m:order_block:child_refinement",
            "created_by": "order_block",
            "timeframe": "15m",
            "direction": "bearish",
            "price_low": 113.0,
            "price_high": 115.0,
            "freshness": "fresh",
            "price_relation": "below_price",
            "validity_status": "PARENT_SCOPE_POI",
            "scope": "parent_scope",
        }],
    }
    graph["timeframes"]["15m"] = {
        "external_bias": "bearish",
        "latest_external_break": {"object_id": "15m_internal_bull"},
    }

    result = build_causal_poi_authority(detector_candidates=detector, formal_structure_graph=graph)

    refinement = result["official_selection"]["execution_refinements"][0]
    assert refinement["source_object_id"] == "child_refinement"
    assert refinement["poi_role"] == "execution_refinement"
    assert refinement["parent_primary_poi_id"].endswith("deep_origin")
    assert result["timeframes"]["15m"]["status"] == "UNRESOLVED"
