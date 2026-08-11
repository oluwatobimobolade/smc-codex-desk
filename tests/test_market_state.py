"""Tests for market state and the trader confirmation sequence.

Pins two behaviours the system previously lacked entirely:

  * it moves through a trader's states instead of answering in one shot, and
    every state names what it is waiting for AND what would invalidate it;
  * it remembers, so it can say what changed since the last look -- which
    liquidity was taken, whether bias flipped, whether the POI moved.

Reaching TRADE_PLAN_READY is an evidence statement, never permission to act.
"""
from __future__ import annotations

import pytest

from smc_desk.perception.market_state import (
    ACCEPTED_DISPLACEMENT,
    INVALIDATED,
    LIQUIDITY_EVENT_IDENTIFIED,
    LTF_CONFIRMATION_PENDING,
    MAP_CONTEXT,
    NO_CONTEXT,
    POI_MAPPED,
    PRICE_APPROACHING_POI,
    PRICE_AT_POI,
    TRADE_PLAN_READY,
    build_market_state,
    diff_states,
)


def _pack(
    *,
    coherent=True,
    narrative_state="PULLBACK_ENDING",
    bias="bullish",
    draw_price=67000.0,
    current_price=63000.0,
    significant=True,
    liquidity=None,
):
    graph = {
        "symbol": "BTCUSDT",
        "decision_time": "2026-06-19T23:45:00Z",
        "timeframes": {"4h": {
            "external_bias": bias,
            "protected_high": {"price": 66000.0},
            "protected_low": {"price": 60691.9},
        }},
        "active_range": {
            "status": "RESOLVED", "high": 66419.2, "low": 62232.1,
            "equilibrium": 64325.6, "price_location": "discount",
            "current_price": current_price, "range_id": "4h:dr",
        },
        "narrative_context": {
            "state": narrative_state, "context_timeframe": "4h",
            "context_bias": bias, "is_coherent": coherent,
            "invalidation_note": "The bullish read fails below the 4h protected low at 60691.9.",
            "draw": (
                {"target_price": draw_price, "target_kind": "equal_highs",
                 "direction": bias} if draw_price is not None else {}
            ),
        },
    }
    return {
        "symbol": "BTCUSDT",
        "formal_structure_graph": graph,
        "detector_candidates": {"4h": {"liquidity_levels": liquidity or []}},
        "structural_significance": {
            "timeframes": {"4h": {
                "major_object_ids": ["bos_1"] if significant else [],
                "tradeable_object_ids": ["bos_1"] if significant else [],
            }}
        },
    }


def _poi(
    low=62500.0,
    high=63200.0,
    object_id="4h_ob_demand",
    *,
    first_touch_time=None,
):
    result = {"object_id": object_id, "price_low": low, "price_high": high,
              "alternates": ["alt_1"]}
    if first_touch_time:
        result["first_touch_time"] = first_touch_time
    return result


# -- every state answers both questions ---------------------------------------


@pytest.mark.parametrize("pack_kwargs,poi", [
    ({"coherent": False}, None),
    ({"draw_price": None}, None),
    ({"significant": False}, None),
    ({}, None),
    ({}, _poi()),
])
def test_every_state_names_what_it_waits_for_and_what_invalidates(pack_kwargs, poi):
    state = build_market_state(evidence_pack=_pack(**pack_kwargs), primary_poi=poi)
    assert state.waiting_for, f"{state.state} does not say what it is waiting for"
    assert state.invalidation, f"{state.state} does not say what would invalidate it"


# -- progression ---------------------------------------------------------------


def test_incoherent_narrative_yields_no_context():
    state = build_market_state(evidence_pack=_pack(coherent=False))
    assert state.state == NO_CONTEXT


def test_causal_reconciliation_required_cannot_present_as_aligned_context():
    pack = _pack(coherent=True, bias="bearish")
    pack["formal_causal_episode_graph"] = {
        "authority_contract": {"enforcement_ready": True},
        "invariants": {
            "status": "REVIEW_REQUIRED",
            "violations": ["1d_v1_controlling_external_break_survives_v3"],
        },
    }

    state = build_market_state(evidence_pack=pack)

    assert state.state == NO_CONTEXT
    assert state.bias == "unknown"
    assert state.narrative_state == "RECONCILIATION_REQUIRED"
    assert "causal episode reconciliation required" in state.reasons


def test_parent_invalidation_is_terminal():
    state = build_market_state(
        evidence_pack=_pack(narrative_state="PARENT_INVALIDATION_PENDING")
    )
    assert state.state == INVALIDATED
    assert state.is_terminal


def test_context_without_a_draw_stops_at_map_context():
    state = build_market_state(evidence_pack=_pack(draw_price=None))
    assert state.state == MAP_CONTEXT
    assert "draw on liquidity" in state.waiting_for.lower()


def test_draw_without_displacement_stops_at_liquidity_event():
    state = build_market_state(evidence_pack=_pack(significant=False))
    assert state.state == LIQUIDITY_EVENT_IDENTIFIED
    assert "displacement" in state.waiting_for.lower()


def test_displacement_without_a_poi_stops_at_accepted_displacement():
    state = build_market_state(evidence_pack=_pack(), primary_poi=None)
    assert state.state == ACCEPTED_DISPLACEMENT
    assert "poi" in state.waiting_for.lower()


def test_price_far_from_poi_is_only_mapped():
    state = build_market_state(
        evidence_pack=_pack(current_price=66000.0), primary_poi=_poi(62500.0, 63200.0)
    )
    assert state.state == POI_MAPPED
    assert "travel toward" in state.waiting_for.lower()


def test_price_near_poi_is_approaching():
    # POI 62500-63200 (height 700); price 62000 is 500 below -> within 2x height.
    state = build_market_state(
        evidence_pack=_pack(current_price=62000.0), primary_poi=_poi(62500.0, 63200.0)
    )
    assert state.state == PRICE_APPROACHING_POI
    assert "reach the poi" in state.waiting_for.lower()


def test_price_inside_poi_waits_for_confirmation():
    state = build_market_state(
        evidence_pack=_pack(current_price=62800.0), primary_poi=_poi(62500.0, 63200.0)
    )
    assert state.state == PRICE_AT_POI
    assert "lower-timeframe" in state.waiting_for.lower()


def test_recorded_arrival_advances_to_ltf_confirmation_pending() -> None:
    state = build_market_state(
        evidence_pack=_pack(current_price=62800.0),
        primary_poi=_poi(first_touch_time="2026-06-19T22:00:00Z"),
    )
    assert state.state == LTF_CONFIRMATION_PENDING
    assert state.entry_model == "ltf_confirmation_close"


def test_post_arrival_sweep_and_displacement_resolve_an_explicit_entry_model() -> None:
    pack = _pack(current_price=62800.0)
    pack["detector_candidates"]["15m"] = {
        "liquidity_levels": [
            {"object_id": "ssl", "side": "sell_side", "price": 62600.0}
        ],
        "sweeps": [
            {
                "object_id": "sweep_ssl",
                "direction": "bullish",
                "confirmed_at": "2026-06-19T22:15:00Z",
                "evidence": {"swept_level_id": "ssl"},
            }
        ],
        "structure_breaks": [
            {
                "object_id": "15m_bull_mss",
                "direction": "bullish",
                "confirmed_at": "2026-06-19T22:30:00Z",
                "evidence": {
                    "is_unconfirmed_probe": False,
                    "displacement_strength": 0.82,
                    "broken_price": 62750.0,
                    "body_close_penetration": 50.0,
                },
            }
        ],
    }

    state = build_market_state(
        evidence_pack=pack,
        primary_poi=_poi(first_touch_time="2026-06-19T22:00:00Z"),
    )

    assert state.state == TRADE_PLAN_READY
    assert state.confirmation_sweep_id == "sweep_ssl"
    assert state.confirmation_break_id == "15m_bull_mss"
    assert state.entry_model == "ltf_confirmation_close"
    assert state.entry_price == 62800.0
    assert state.to_dict()["signal_allowed"] is False


def test_arrival_is_required_before_confirmation_is_even_considered():
    """A trader does not look for entry confirmation before price arrives."""
    approaching = build_market_state(
        evidence_pack=_pack(current_price=62000.0), primary_poi=_poi(62500.0, 63200.0)
    )
    assert approaching.rank < build_market_state(
        evidence_pack=_pack(current_price=62800.0), primary_poi=_poi(62500.0, 63200.0)
    ).rank


# -- state content -------------------------------------------------------------


def test_state_carries_the_running_picture():
    state = build_market_state(
        evidence_pack=_pack(current_price=62800.0), primary_poi=_poi()
    )
    assert state.bias == "bullish"
    assert state.context_timeframe == "4h"
    assert state.range_high == 66419.2 and state.range_low == 62232.1
    assert state.protected_low == 60691.9
    assert state.draw_price == 67000.0
    assert state.primary_poi_id == "4h_ob_demand"
    assert state.alternate_poi_ids == ("alt_1",)
    assert state.reasons


def test_state_is_observe_only():
    payload = build_market_state(evidence_pack=_pack(), primary_poi=_poi()).to_dict()
    assert payload["signal_allowed"] is False
    assert payload["authority"] == "observe_only_market_state"


def test_missing_graph_is_handled_not_crashed():
    state = build_market_state(evidence_pack={})
    assert state.state == NO_CONTEXT
    assert state.waiting_for


# -- memory --------------------------------------------------------------------


def test_first_observation_has_no_prior():
    current = build_market_state(evidence_pack=_pack(), primary_poi=_poi())
    transition = diff_states(None, current)
    assert transition.advanced is True
    assert "first observation" in transition.notes[0]


def test_advancing_through_the_sequence_is_reported():
    earlier = build_market_state(evidence_pack=_pack(), primary_poi=None)
    later = build_market_state(
        evidence_pack=_pack(current_price=62800.0), primary_poi=_poi()
    )
    transition = diff_states(earlier, later)
    assert transition.advanced and not transition.regressed
    assert any("advanced" in n for n in transition.notes)


def test_newly_swept_liquidity_is_remembered():
    """The core memory case: what got taken while we were not watching."""
    before = build_market_state(evidence_pack=_pack(liquidity=[
        {"object_id": "pool_a", "price": 64000.0, "activity_status": "active"},
    ]))
    after = build_market_state(evidence_pack=_pack(liquidity=[
        {"object_id": "pool_a", "price": 64000.0, "activity_status": "consumed"},
    ]))
    transition = diff_states(before, after)
    assert "pool_a" in transition.newly_swept_liquidity
    assert any("liquidity taken" in n for n in transition.notes)


def test_real_sweep_objects_mark_the_referenced_level_as_spent():
    pack = _pack(liquidity=[
        {
            "object_id": "pool_a",
            "price_low": 63990.0,
            "price_high": 64010.0,
            "timeframe": "4h",
            "evidence": {"level_kind": "equal_highs", "side": "buy_side", "touch_count": 2},
        }
    ])
    pack["detector_candidates"]["4h"]["sweeps"] = [
        {"object_id": "sweep_1", "evidence": {"swept_level_id": "pool_a"}}
    ]

    state = build_market_state(evidence_pack=pack)

    assert "pool_a" in state.swept_liquidity_ids
    assert "pool_a" not in state.unswept_liquidity_ids


def test_bias_flip_is_reported():
    before = build_market_state(evidence_pack=_pack(bias="bullish"))
    after = build_market_state(evidence_pack=_pack(bias="bearish"))
    transition = diff_states(before, after)
    assert transition.bias_changed
    assert any("bias changed" in n for n in transition.notes)


def test_poi_change_is_reported():
    before = build_market_state(evidence_pack=_pack(), primary_poi=_poi(object_id="poi_1"))
    after = build_market_state(evidence_pack=_pack(), primary_poi=_poi(object_id="poi_2"))
    transition = diff_states(before, after)
    assert transition.poi_changed


def test_standing_still_reports_what_it_is_still_waiting_for():
    state = build_market_state(evidence_pack=_pack(), primary_poi=None)
    transition = diff_states(state, state)
    assert not transition.advanced and not transition.regressed
    assert any("still" in n for n in transition.notes)


def test_regression_is_reported():
    later = build_market_state(evidence_pack=_pack(current_price=62800.0), primary_poi=_poi())
    earlier = build_market_state(evidence_pack=_pack(coherent=False))
    transition = diff_states(later, earlier)
    assert transition.regressed
