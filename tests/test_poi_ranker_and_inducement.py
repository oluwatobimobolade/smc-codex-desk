"""Tests for the POI ranker and inducement hypothesis (step 6, programme §8/§9).

Pins:
  * Three independent scores (deterministic / ai_semantic / empirical) are
    kept separate; the deterministic score is computed from causal /
    location / lifecycle / quality / narrative features per §8.2.
  * combined_rank uses whatever non-null inputs exist; uncertainty reflects
    how many axes are present (programme §17) -- never false precision.
  * empirical_score stays null until outcomes exist (never invented).
  * AI semantic scores attach from the reconciler and re-rank.
  * Inducement (§9) emits a hypothesis only if ALL five conditions hold;
    a missing condition blocks the candidate; consumption needs intermediate
    interaction + deeper reach + no contradicting event.
"""
from __future__ import annotations

import pytest

from smc_desk.structure.inducement import (
    InducementState,
    confirm_consumption,
    evaluate,
)
from smc_desk.structure.poi_ranker import (
    POIScores,
    attach_ai_semantic,
    deterministic_score,
    score_pois,
)


def _pois():
    return [
        {"object_id": "p1", "origin_timeframe": "4h",
         "causal_features": {"originated_displacement": True, "caused_bos": True,
                             "linked_protected_point": True, "created_fvg": True,
                             "in_active_range": True},
         "location_features": {"direction_aligned": True, "depth_relative_to_shallow": "deeper"},
         "lifecycle_features": {"state": "fresh"},
         "quality_features": {"departure_speed_atr_per_bar": 1.0,
                              "imbalance_size_atr": 0.7, "clean_origin": True},
         "narrative_features": {"liquidity_before": True, "parent_alignment": True}},
        {"object_id": "p2", "origin_timeframe": "15m",
         "causal_features": {"originated_displacement": False},
         "lifecycle_features": {"state": "partially_mitigated"}},
        {"object_id": "p3", "origin_timeframe": "4h",
         "causal_features": {"originated_displacement": True},
         "lifecycle_features": {"state": "fresh"},
         "quality_features": {"clean_origin": True}},
    ]


def test_deterministic_score_uses_all_five_feature_classes():
    p = {"object_id": "x", "origin_timeframe": "4h",
         "causal_features": {"originated_displacement": True, "caused_bos": True,
                             "linked_protected_point": True, "created_fvg": True,
                             "in_active_range": True},
         "location_features": {"direction_aligned": True, "depth_relative_to_shallow": "deeper"},
         "lifecycle_features": {"state": "fresh"},
         "quality_features": {"departure_speed_atr_per_bar": 1.0,
                              "imbalance_size_atr": 0.7, "clean_origin": True},
         "narrative_features": {"liquidity_before": True, "parent_alignment": True}}
    s = deterministic_score(poi=p, active_range={"bar_span": 20}, owning_timeframe="4h")
    # 3+3+2+1+1 (causal) + 1+1 (location) + 2 (lifecycle fresh) + 1+1+1 (quality) + 1+1 (narrative)
    assert s == 19.0


def test_scores_kept_separate_until_inputs_exist():
    scored = score_pois(pois=_pois(), active_range={"bar_span": 20})
    for s in scored:
        assert s.ai_semantic_score is None
        assert s.empirical_score is None
        # combined_rank still assigned by deterministic axis; uncertainty reflects
        # only one axis being present.
        assert s.combined_rank is not None
        assert s.uncertainty in {"probable", "insufficient_context"}


def test_combined_rank_uses_deterministic_when_ai_missing():
    scored = score_pois(pois=_pois(), active_range={"bar_span": 20})
    by_id = {s.poi_id: s for s in scored}
    # p1 has the highest deterministic score -> rank 1
    assert by_id["p1"].combined_rank == 1
    assert by_id["p1"].deterministic_score > by_id["p3"].deterministic_score > by_id["p2"].deterministic_score


def test_attach_ai_semantic_re_ranks_and_keeps_empirical_null():
    scored = score_pois(pois=_pois(), active_range={"bar_span": 20})
    # Reconciler picks p3 > p1 > p2 -- the AI axis now disagrees with deterministic.
    scored2 = attach_ai_semantic(scored, ai_ranking={"p1": 1.0, "p3": 5.0, "p2": 0.0})
    for s in scored2:
        assert s.empirical_score is None          # never invented
        assert s.ai_semantic_score is not None    # now attached


def test_uncertainty_never_confirmed_without_all_three_axes():
    scored = score_pois(pois=_pois(), active_range={"bar_span": 20})
    scored2 = attach_ai_semantic(scored, ai_ranking={"p1": 5.0, "p3": 3.0, "p2": 1.0})
    for s in scored2:
        # Empirical axis is still null -> cannot be confirmed.
        assert s.uncertainty != "confirmed"


def test_poi_scores_sha256_stable():
    scored = score_pois(pois=_pois(), active_range={"bar_span": 20})
    scored_again = score_pois(pois=_pois(), active_range={"bar_span": 20})
    for a, b in zip(scored, scored_again):
        assert a.sha256 == b.sha256


def test_inducement_requires_all_five_conditions():
    h = evaluate(
        hypothesis_id="h1", shallow_object_evidence_id="sh1",
        deeper_object_evidence_id="dp1", has_deeper_poi=True,
        has_intermediate_visible_liquidity=True, has_plausible_causal_path=True,
        has_structural_reason_shallow_weaker=True,
        has_unconsumed_liquidity_around_intermediate=True,
        rejection_event_definition="deeper reached without intermediate",
    )
    assert h.state == InducementState.CANDIDATE.value
    assert all(h.conditions.values())


def test_inducement_blocked_when_any_condition_missing():
    h = evaluate(
        hypothesis_id="h2", shallow_object_evidence_id="sh2",
        deeper_object_evidence_id="dp2", has_deeper_poi=True,
        has_intermediate_visible_liquidity=False, has_plausible_causal_path=True,
        has_structural_reason_shallow_weaker=True,
        has_unconsumed_liquidity_around_intermediate=True,
        rejection_event_definition="NA",
    )
    assert h.state == InducementState.NO_HYPOTHESIS.value


def test_inducement_consumption_lifecycle():
    h = evaluate(
        hypothesis_id="h1", shallow_object_evidence_id="sh1",
        deeper_object_evidence_id="dp1", has_deeper_poi=True,
        has_intermediate_visible_liquidity=True, has_plausible_causal_path=True,
        has_structural_reason_shallow_weaker=True,
        has_unconsumed_liquidity_around_intermediate=True,
        rejection_event_definition="deeper reached without intermediate",
    )
    consumed = confirm_consumption(h, intermediate_interacted=True,
                                   deeper_reached=True, no_contradicting_event=True)
    assert consumed.state == InducementState.CONSUMED.value
    assert InducementState.PATH_ACTIVE.value in consumed.lifecycle
    assert InducementState.CONSUMED.value in consumed.lifecycle


def test_inducement_rejected_when_deeper_reached_without_intermediate():
    h = evaluate(
        hypothesis_id="h1", shallow_object_evidence_id="sh1",
        deeper_object_evidence_id="dp1", has_deeper_poi=True,
        has_intermediate_visible_liquidity=True, has_plausible_causal_path=True,
        has_structural_reason_shallow_weaker=True,
        has_unconsumed_liquidity_around_intermediate=True,
        rejection_event_definition="deeper reached without intermediate",
    )
    rejected = confirm_consumption(h, intermediate_interacted=False,
                                   deeper_reached=True, no_contradicting_event=True)
    assert rejected.state == InducementState.REJECTED.value


def test_doctrine_poi_forbids_single_score_shortcut():
    from smc_desk.structure.doctrine import concept
    c = concept("poi")
    fs = " ".join(c.get("forbidden_shortcuts", []))
    assert "single score ranks POIs" in fs