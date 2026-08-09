"""Tests for the multi-timeframe narrative hierarchy.

Pins the replacement of the unanimity vote. The old rule was::

    aligned_bias = aligned[0] if len(set(aligned)) == 1 else "mixed"

which abstained on every retracement — i.e. on every setup worth waiting for.
These tests pin the trader-faithful reading instead:

  * the highest resolved context timeframe owns bias;
  * a disagreeing child is a retracement INSIDE that bias, never a vote
    against it, and never collapses the read to "mixed";
  * a child only threatens the parent by body-closing beyond the parent's
    protected level;
  * the read names a draw on liquidity and picks ONE primary POI;
  * the module stays observe-only.

The centrepiece is ``test_the_20260717_btcusdt_case_is_no_longer_mixed``,
which replays the exact live run that produced
``final bias = mixed -> REVIEW_REQUIRED`` with a near-empty chart.
"""
from __future__ import annotations

import pytest

from smc_desk.perception.narrative_hierarchy import (
    ALIGNED_CONTINUATION,
    INSUFFICIENT_CONTEXT,
    PARENT_INVALIDATION_PENDING,
    PULLBACK_ENDING,
    RETRACEMENT_WITHIN_PARENT,
    read_narrative,
    resolve_liquidity_draw,
    select_primary_poi,
)


def _node(bias, *, internal=None, protected_high=None, protected_low=None,
          break_id=None, body_close=None):
    node = {"external_bias": bias, "internal_state": internal or "none"}
    if protected_high is not None:
        node["protected_high"] = {"price": protected_high}
    if protected_low is not None:
        node["protected_low"] = {"price": protected_low}
    if break_id is not None:
        node["latest_external_break"] = {
            "object_id": break_id, "body_close_price": body_close,
            "confirmed_at": "2026-07-17T12:00:00Z",
        }
    return node


# -- the regression that motivated this module --------------------------------


def test_the_20260717_btcusdt_case_is_no_longer_mixed():
    """Replay of analysis_runs/LIVE_TV_APP_BTCUSDT_20260717.

    Recorded thesis: "Daily=bearish_external_bullish_internal_pullback;
    4H=bullish; 1H=bearish; final bias=mixed" -> REVIEW_REQUIRED, 1 object
    drawn from 6,591 available. The same evidence must now read as a coherent
    bearish retracement story.
    """
    timeframes = {
        "1d": _node("bearish", internal="bullish_internal_pullback",
                    protected_high=67000.0, protected_low=60000.0,
                    break_id="1d_bos_bearish", body_close=61500.0),
        "4h": _node("bullish", internal="bullish_internal_continuation",
                    protected_high=65589.7, protected_low=61806.0,
                    break_id="4h_bos_bullish", body_close=64800.0),
        "1h": _node("bearish", internal="bearish_internal_continuation",
                    protected_high=65100.0, protected_low=63900.0,
                    break_id="1h_choch_bearish", body_close=64200.0),
    }
    active_range = {"high": 65589.7, "low": 61806.0, "equilibrium": 63697.85,
                    "price_location": "premium", "range_id": "4h:dr"}
    liquidity = [
        # Range low: external scope, but only a 1h reference.
        {"object_id": "liq_sell_61806", "price": 61806.0, "timeframe": "1h",
         "kind": "equal_lows", "touch_count": 2, "activity_status": "active"},
        # Already taken, so it cannot be a draw however important it looks.
        {"object_id": "liq_buy_65589", "price": 65589.7, "timeframe": "1d",
         "kind": "prior_day_high", "activity_status": "consumed"},
        # The strongest live sell-side pool: daily timeframe, inside the range.
        {"object_id": "liq_pdl_63000", "price": 63000.0, "timeframe": "1d",
         "kind": "prior_day_low", "touch_count": 2, "activity_status": "active"},
    ]

    read = read_narrative(timeframes=timeframes, active_range=active_range,
                          current_price=64650.0, liquidity_levels=liquidity)

    assert read.state == RETRACEMENT_WITHIN_PARENT
    assert read.context_timeframe == "1d" and read.context_bias == "bearish"
    assert read.is_coherent, "this is a readable story, not a refusal"
    assert "4h" in read.retracing_timeframes
    assert "1h" in read.confirming_timeframes
    assert read.price_location == "premium"
    # It must answer 'where is price going?' -- the old thesis never did --
    # and it must name WHAT it is targeting, not just "some liquidity".
    assert read.draw.direction == "bearish"
    assert read.draw.target_price == 63000.0
    assert read.draw.target_kind == "prior_day_low"
    assert read.draw.target_object_id == "liq_pdl_63000"
    # Consumed liquidity is spent and cannot be a draw.
    assert read.draw.target_object_id != "liq_buy_65589"
    assert read.invalidation_note and "67000" in read.invalidation_note


def test_the_draw_prefers_importance_over_proximity():
    """A daily pool further away beats a 15m pool sitting closer to price."""
    read = read_narrative(
        timeframes={
            "1d": _node("bearish", protected_high=67000.0),
            "4h": _node("bullish", break_id="4h", body_close=64800.0),
        },
        active_range={"high": 66000.0, "low": 62000.0, "price_location": "premium"},
        current_price=64000.0,
        liquidity_levels=[
            {"object_id": "near_15m", "price": 63800.0, "timeframe": "15m",
             "kind": "equal_lows", "activity_status": "active"},
            {"object_id": "far_daily", "price": 62200.0, "timeframe": "1d",
             "kind": "prior_day_low", "touch_count": 2, "activity_status": "active"},
        ],
    )
    assert read.draw.target_object_id == "far_daily"
    assert "importance" in read.draw.rationale


def test_separate_sweep_object_prevents_retargeting_spent_liquidity():
    read = read_narrative(
        timeframes={"1d": _node("bullish")},
        active_range={"high": 120.0, "low": 80.0, "price_location": "discount"},
        current_price=100.0,
        liquidity_levels=[
            {
                "object_id": "spent_pool",
                "price_low": 109.0,
                "price_high": 111.0,
                "timeframe": "1d",
                "evidence": {
                    "level_kind": "equal_highs",
                    "side": "buy_side",
                    "touch_count": 2,
                },
            }
        ],
        swept_object_ids=["spent_pool"],
    )

    assert read.draw.target_object_id != "spent_pool"
    assert read.draw.target_kind == "range_extreme"


def test_that_case_picks_one_primary_poi_instead_of_hedging():
    """The recorded run offered a bullish AND a bearish POI. Choose one."""
    timeframes = {
        "1d": _node("bearish", protected_high=67000.0),
        "4h": _node("bullish", break_id="4h", body_close=64800.0),
    }
    read = read_narrative(
        timeframes=timeframes,
        active_range={"high": 65589.7, "low": 61806.0, "price_location": "premium"},
        current_price=64650.0,
        liquidity_levels=[{"object_id": "sell", "price": 62000.0, "activity_status": "active"}],
    )
    pois = [
        {"object_id": "4h_ob_bull", "direction": "bullish",
         "price_low": 62410.1, "price_high": 63084.0, "lifecycle": "fresh"},
        {"object_id": "1h_ob_bear", "direction": "bearish",
         "price_low": 64512.0, "price_high": 64974.5, "lifecycle": "fresh"},
        {"object_id": "4h_ob_bear_far", "direction": "bearish",
         "price_low": 66000.0, "price_high": 66500.0, "lifecycle": "fresh"},
    ]
    primary = select_primary_poi(narrative=read, poi_candidates=pois)
    assert primary is not None
    assert primary["object_id"] == "1h_ob_bear", "counter-trend POI must not be primary"
    assert "4h_ob_bear_far" in primary["alternates"]
    assert primary["selection_reason"]


# -- state resolution ---------------------------------------------------------


def test_full_agreement_is_continuation_and_warns_about_chasing():
    read = read_narrative(timeframes={
        "1d": _node("bullish"), "4h": _node("bullish"), "1h": _node("bullish"),
    })
    assert read.state == ALIGNED_CONTINUATION
    assert read.is_coherent
    assert "chasing" in read.expectation.lower()


def test_child_body_close_beyond_parent_protected_threatens_the_parent():
    """The one case where a child legitimately challenges its parent."""
    timeframes = {
        "1d": _node("bearish", protected_high=65000.0),
        "4h": _node("bullish", break_id="4h_bos", body_close=65500.0),   # beyond 65000
    }
    read = read_narrative(timeframes=timeframes)
    assert read.state == PARENT_INVALIDATION_PENDING
    assert "4h" in read.invalidating_timeframes
    assert not read.is_coherent, "a threatened parent is not a tradeable story"


def test_degenerate_protected_levels_cannot_manufacture_an_invalidation():
    """Both protected sides resolving to one derived number is unverifiable.

    The graph falls back to the broken swing price for BOTH protected_high and
    protected_low when a node carries no explicit protected price. Trusting
    that would turn ordinary pullbacks into parent invalidations. Doctrine says
    a child cannot flip its parent, so the ambiguity resolves for the parent.
    """
    parent = _node("bearish", protected_high=61500.0, protected_low=61500.0,
                   break_id="1d", body_close=61300.0)
    parent["latest_external_break"]["broken_price"] = 61500.0
    read = read_narrative(timeframes={
        "1d": parent,
        "4h": _node("bullish", break_id="4h", body_close=64800.0),
    })
    assert read.state == RETRACEMENT_WITHIN_PARENT
    assert read.invalidating_timeframes == ()


def test_protected_level_on_the_wrong_side_is_not_protective():
    """A 'protected high' below the parent's own break price cannot invalidate."""
    parent = _node("bearish", protected_high=61500.0, protected_low=60000.0,
                   break_id="1d", body_close=61300.0)
    parent["latest_external_break"]["broken_price"] = 63000.0   # high sits BELOW this
    read = read_narrative(timeframes={
        "1d": parent,
        "4h": _node("bullish", break_id="4h", body_close=64800.0),
    })
    assert read.state == RETRACEMENT_WITHIN_PARENT


def test_child_below_parent_protected_is_only_a_retracement():
    timeframes = {
        "1d": _node("bearish", protected_high=65000.0),
        "4h": _node("bullish", break_id="4h_bos", body_close=64000.0),   # inside 65000
    }
    read = read_narrative(timeframes=timeframes)
    assert read.state == RETRACEMENT_WITHIN_PARENT
    assert read.invalidating_timeframes == ()


def test_pullback_ending_when_fastest_retracer_turns_back():
    timeframes = {
        "1d": _node("bearish", protected_high=67000.0),
        "4h": _node("bullish", internal="bearish_internal_pullback",
                    break_id="4h", body_close=64000.0),
    }
    read = read_narrative(timeframes=timeframes)
    assert read.state == PULLBACK_ENDING
    assert read.is_coherent
    assert "continuation setups form" in read.expectation


def test_no_resolved_context_is_honest_about_it():
    read = read_narrative(timeframes={"4h": _node("unknown"), "1h": _node("unknown")})
    assert read.state == INSUFFICIENT_CONTEXT
    assert not read.is_coherent


def test_never_returns_mixed_for_any_combination():
    """The whole point: no bias combination may collapse to 'mixed'."""
    from itertools import product
    for d1, d4, d1h in product(["bullish", "bearish"], repeat=3):
        read = read_narrative(timeframes={
            "1d": _node(d1, protected_high=70000.0, protected_low=50000.0),
            "4h": _node(d4, break_id="4h", body_close=60000.0),
            "1h": _node(d1h, break_id="1h", body_close=60000.0),
        })
        assert read.context_bias in {"bullish", "bearish"}
        assert read.state != "mixed"
        assert read.sentence, "every state must be explainable in a sentence"


# -- draw on liquidity --------------------------------------------------------


def test_draw_prefers_nearest_unswept_pool_in_context_direction():
    draw = resolve_liquidity_draw(
        context_bias="bearish", active_range={"high": 110.0, "low": 90.0},
        current_price=100.0,
        liquidity_levels=[
            {"object_id": "near", "price": 96.0, "activity_status": "active"},
            {"object_id": "far", "price": 92.0, "activity_status": "active"},
            {"object_id": "wrong_side", "price": 104.0, "activity_status": "active"},
        ],
    )
    assert draw.target_object_id == "near"
    assert draw.direction == "bearish"


def test_consumed_liquidity_cannot_be_a_draw():
    draw = resolve_liquidity_draw(
        context_bias="bearish", active_range={"high": 110.0, "low": 90.0},
        current_price=100.0,
        liquidity_levels=[{"object_id": "spent", "price": 96.0, "activity_status": "consumed"}],
    )
    assert draw.target_object_id != "spent"
    assert draw.target_kind == "range_extreme"   # falls back to the range low


def test_draw_falls_back_to_range_extreme():
    draw = resolve_liquidity_draw(
        context_bias="bullish", active_range={"high": 110.0, "low": 90.0},
        current_price=100.0, liquidity_levels=[],
    )
    assert draw.target_kind == "range_extreme"
    assert draw.target_price == 110.0


def test_no_direction_means_no_invented_draw():
    draw = resolve_liquidity_draw(
        context_bias="unknown", active_range={"high": 110.0, "low": 90.0},
        current_price=100.0, liquidity_levels=[],
    )
    assert draw.target_price is None


# -- authority ----------------------------------------------------------------


def test_read_is_observe_only():
    read = read_narrative(timeframes={"1d": _node("bullish"), "4h": _node("bullish")})
    payload = read.to_dict()
    assert payload["signal_allowed"] is False
    assert payload["authority"] == "observe_only_narrative_read"


def test_incoherent_read_selects_no_poi():
    read = read_narrative(timeframes={"4h": _node("unknown")})
    assert select_primary_poi(narrative=read, poi_candidates=[
        {"object_id": "x", "direction": "bullish", "price_low": 1, "price_high": 2},
    ]) is None


def test_invalidated_poi_is_never_primary():
    read = read_narrative(timeframes={"1d": _node("bearish"), "4h": _node("bearish")})
    primary = select_primary_poi(narrative=read, poi_candidates=[
        {"object_id": "dead", "direction": "bearish", "price_low": 1, "price_high": 2,
         "lifecycle": "invalidated"},
    ])
    assert primary is None


# -- POI selection ranks on SMC quality, not on nearness ----------------------
#
# select_primary_poi used to sort aligned candidates by distance to the draw and
# nothing else, while its docstring claimed it weighed equilibrium. These tests
# hold the corrected behaviour: proximity is the tie-break, never the reason.


def _bear_poi(object_id, low, high, *, caused=False, scope="internal"):
    return {
        "object_id": object_id, "direction": "bearish",
        "price_low": low, "price_high": high, "lifecycle": "fresh",
        "metadata": {"linked_break_scope": scope},
        "evidence": {"caused_structure_break": caused, "poi_grade": caused,
                     "structure_scope": scope},
    }


def test_causal_poi_beats_a_nearer_one_that_broke_nothing():
    """The zone that caused the move wins even from further away.

    This is the founder's chart complaint in test form: an indicator marks the
    closest box, a trader marks the origin of the displacement.
    """
    read = read_narrative(timeframes={"1d": _node("bearish"), "4h": _node("bearish")})
    primary = select_primary_poi(
        narrative=read,
        poi_candidates=[
            _bear_poi("near_but_idle", 64000.0, 64200.0),
            _bear_poi("far_but_causal", 66000.0, 66500.0, caused=True, scope="external"),
        ],
        current_price=64100.0,  # sitting inside the idle zone
    )
    assert primary is not None
    assert primary["object_id"] == "far_but_causal"
    assert "near_but_idle" in primary["alternates"]
    assert primary["quality_score"] > 0


def test_equilibrium_is_actually_honoured_now():
    """Supply in premium beats supply in discount once a range is supplied."""
    read = read_narrative(timeframes={"1d": _node("bearish"), "4h": _node("bearish")})
    primary = select_primary_poi(
        narrative=read,
        poi_candidates=[
            _bear_poi("discount_supply", 60000.0, 60500.0, caused=True),
            _bear_poi("premium_supply", 68000.0, 68500.0, caused=True),
        ],
        equilibrium=64000.0,
        current_price=60200.0,  # nearer the discount zone, which must still lose
    )
    assert primary is not None
    assert primary["object_id"] == "premium_supply"
    assert primary["quality_factors"]["location"] == "premium"


def test_selection_reason_states_the_criteria_not_just_the_verdict():
    read = read_narrative(timeframes={"1d": _node("bearish"), "4h": _node("bearish")})
    primary = select_primary_poi(
        narrative=read,
        poi_candidates=[
            _bear_poi("winner", 68000.0, 68500.0, caused=True, scope="external"),
            _bear_poi("loser", 64000.0, 64200.0),
        ],
        equilibrium=64000.0,
    )
    assert primary is not None
    reason = primary["selection_reason"].lower()
    assert "structure" in reason
    assert "external" in reason
    assert "not proximity" in reason
    assert primary["ranked_alternates"][0]["object_id"] == "loser"


def test_missing_equilibrium_does_not_manufacture_a_location_verdict():
    """No dealing range means no premium/discount claim -- not a guessed one."""
    read = read_narrative(timeframes={"1d": _node("bearish"), "4h": _node("bearish")})
    primary = select_primary_poi(
        narrative=read,
        poi_candidates=[_bear_poi("only", 64000.0, 64200.0, caused=True)],
    )
    assert primary is not None
    assert primary["quality_factors"]["location"] == "unknown"
