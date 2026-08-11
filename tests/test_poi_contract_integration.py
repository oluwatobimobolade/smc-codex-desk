from __future__ import annotations

from smc_desk.brain.smc_evidence_pack_builder import _market_state
from smc_desk.perception.causal_poi_authority import build_causal_poi_authority
from smc_desk.perception.poi_quality import rank_pois
from tests.test_causal_poi_authority import _pack


def test_causal_authority_cannot_promote_an_ob_rejected_by_the_origin_gate() -> None:
    detector, graph = _pack()
    deep = next(item for item in detector["1h"]["order_blocks"] if item["object_id"] == "deep_origin")
    deep["evidence"].update(
        {
            "poi_grade": False,
            "caused_structure_break": False,
            "admission_status": "departure_lacks_displacement",
        }
    )
    deep["metadata"]["causal_origin_admission"] = {
        "admitted": False,
        "reason": "departure_lacks_displacement",
    }

    result = build_causal_poi_authority(
        detector_candidates=detector,
        formal_structure_graph=graph,
    )

    primary = result["official_selection"]["primary_causal_poi"]
    assert primary["source_object_id"] == "shallow_continuation"
    rejected = result["timeframes"]["1h"]["rejected_candidates"]
    deep_rejection = next(item for item in rejected if item["source_object_id"] == "deep_origin")
    assert deep_rejection["causal_status"] == "REJECTED_CAUSAL_ORIGIN_GATE"


def _production_candidate(object_id: str, *, scope: str, status: str, displacement: float) -> dict:
    return {
        "poi_id": object_id,
        "source_object_id": object_id.split(":")[-1],
        "timeframe": "4h",
        "direction": "bearish",
        "kind": "order_block",
        "price_low": 104.0,
        "price_high": 106.0,
        "freshness": "fresh",
        "linked_break_scope": scope,
        "linked_break_displacement_strength": displacement,
        "causal_status": status,
        "causal_certificate": {"status": "PASS"},
    }


def test_ranker_reads_the_real_causal_authority_schema() -> None:
    external = _production_candidate(
        "4h:order_block:external",
        scope="external",
        status="ELIGIBLE_CAUSAL_OB",
        displacement=0.95,
    )
    internal = _production_candidate(
        "4h:order_block:internal",
        scope="internal",
        status="SECONDARY_INTERNAL_REACTION_CANDIDATE",
        displacement=0.25,
    )

    ranked = rank_pois([internal, external], equilibrium=100.0, current_price=99.0)

    assert [item.object_id for item in ranked] == [
        "4h:order_block:external",
        "4h:order_block:internal",
    ]
    assert ranked[0].caused_structure_break is True
    assert ranked[0].scope == "external"
    assert ranked[0].score > ranked[1].score


def test_market_state_receives_a_real_causal_authority_poi_id() -> None:
    candidate = _production_candidate(
        "4h:order_block:primary",
        scope="external",
        status="ELIGIBLE_CAUSAL_OB",
        displacement=0.9,
    )
    candidate.update({"price_low": 104.0, "price_high": 106.0})
    pack = {
        "symbol": "TESTFX",
        "formal_structure_graph": {
            "decision_time": "2026-08-09T12:00:00Z",
            "timeframes": {
                "1d": {
                    "external_bias": "bearish",
                    "internal_state": "bearish_continuation",
                    "protected_high": {"price": 112.0},
                    "protected_low": {"price": 88.0},
                    "latest_external_break": {
                        "object_id": "1d_break",
                        "direction": "bearish",
                        "confirmed_at": "2026-08-08T00:00:00Z",
                    },
                },
                "4h": {
                    "external_bias": "bearish",
                    "internal_state": "bearish_continuation",
                    "protected_high": {"price": 110.0},
                    "protected_low": {"price": 90.0},
                    "latest_external_break": {
                        "object_id": "4h_break",
                        "direction": "bearish",
                        "confirmed_at": "2026-08-09T08:00:00Z",
                    },
                }
            },
            "active_range": {
                "high": 110.0,
                "low": 90.0,
                "equilibrium": 100.0,
                "current_price": 103.0,
                "price_location": "premium",
            },
            "narrative_context": {
                "state": "ALIGNED_CONTINUATION",
                "context_timeframe": "4h",
                "context_bias": "bearish",
                "is_coherent": True,
                "draw": {"target_price": 90.0, "target_kind": "range_extreme"},
                "invalidation_note": "Invalid above 110.",
            },
        },
        "causal_poi_authority": {
            "scenarios": {
                "bearish": {
                    "primary_causal_poi": candidate,
                    "secondary_reaction_pois": [],
                }
            }
        },
        "detector_candidates": {"4h": {"liquidity_levels": []}},
        "structural_significance": {
            "timeframes": {"4h": {"major_object_ids": ["4h_break"]}}
        },
    }

    state = _market_state(pack)

    assert state["poi"]["primary_id"] == "4h:order_block:primary"
    assert state["state"] in {"POI_MAPPED", "PRICE_APPROACHING_POI"}


def test_market_state_preserves_causal_authority_primary_over_higher_scored_secondary() -> None:
    primary = _production_candidate(
        "4h:order_block:authority-primary",
        scope="external",
        status="ELIGIBLE_CAUSAL_OB",
        displacement=0.15,
    )
    primary.update({"price_low": 96.0, "price_high": 98.0, "primary_reason": "Owns the accepted break lineage."})
    secondary = _production_candidate(
        "4h:order_block:higher-quality-secondary",
        scope="external",
        status="ELIGIBLE_CAUSAL_OB",
        displacement=1.0,
    )
    secondary.update({"price_low": 104.0, "price_high": 106.0})
    pack = {
        "symbol": "TESTFX",
        "formal_structure_graph": {
            "decision_time": "2026-08-09T12:00:00Z",
            "timeframes": {
                "4h": {
                    "external_bias": "bearish",
                    "latest_external_break": {
                        "object_id": "4h_break",
                        "direction": "bearish",
                        "confirmed_at": "2026-08-09T08:00:00Z",
                    },
                }
            },
            "active_range": {
                "high": 110.0,
                "low": 90.0,
                "equilibrium": 100.0,
                "current_price": 103.0,
                "price_location": "premium",
            },
            "narrative_context": {
                "state": "ALIGNED_CONTINUATION",
                "context_timeframe": "4h",
                "context_bias": "bearish",
                "is_coherent": True,
                "draw": {"target_price": 90.0, "target_kind": "range_extreme"},
                "invalidation_note": "Invalid above 110.",
            },
        },
        "causal_poi_authority": {
            "scenarios": {
                "bearish": {
                    "status": "SELECTED",
                    "primary_causal_poi": primary,
                    "secondary_reaction_pois": [secondary],
                }
            }
        },
        "detector_candidates": {"4h": {"liquidity_levels": []}},
        "structural_significance": {"timeframes": {"4h": {"major_object_ids": ["4h_break"]}}},
    }

    state = _market_state(pack)

    assert state["poi"]["primary_id"] == "4h:order_block:authority-primary"
    assert state["poi"]["alternates"] == ["4h:order_block:higher-quality-secondary"]
