"""Tests for the liquidity model.

The detector answers "where are the equal highs and lows?"; these pin the
questions a trader actually asks — what has been taken, what remains, and
which remaining pool makes structural sense as the next target.

The rule that matters most: **nearest is a tie-break, not a reason**. A trader
steps over a minor internal pool to reach a prior daily high, and the ranking
has to reproduce that.
"""
from __future__ import annotations

import pytest

from smc_desk.perception.liquidity_model import (
    build_liquidity_map,
    classify_kind,
    classify_scope,
    resolve_draw,
    score_importance,
)


def _level(object_id, price, **kw):
    payload = {"object_id": object_id, "price": price, "timeframe": "1h"}
    payload.update(kw)
    return payload


# -- classification -----------------------------------------------------------


def test_kind_is_read_from_an_explicit_field_first():
    assert classify_kind({"kind": "prior_day_high"}) == "prior_day_high"


def test_kind_is_inferred_from_a_label_when_not_explicit():
    assert classify_kind({"object_id": "x", "label": "Prior Week High"}) == "prior_week_high"
    assert classify_kind({"object_id": "idm_1", "label": "inducement"}) == "inducement"


def test_multi_touch_clusters_are_equal_levels():
    assert classify_kind({"side": "buy_side", "constituent_swing_ids": ["a", "b"]}) == "equal_highs"
    assert classify_kind({"side": "sell_side", "touch_count": 3}) == "equal_lows"


def test_single_untyped_level_is_unknown_not_guessed():
    assert classify_kind({"object_id": "plain"}) == "unknown"


def test_scope_is_external_beyond_the_range_and_internal_inside():
    assert classify_scope(70000.0, 66000.0, 62000.0) == "external"
    assert classify_scope(60000.0, 66000.0, 62000.0) == "external"
    assert classify_scope(64000.0, 66000.0, 62000.0) == "internal"


def test_scope_is_unknown_without_a_range():
    assert classify_scope(64000.0, None, None) == "unknown"


# -- importance ---------------------------------------------------------------


def test_swept_liquidity_scores_zero_because_it_is_spent():
    reasons = []
    assert score_importance(kind="prior_day_high", timeframe="1d", scope="external",
                            touch_count=3, swept=True, reasons=reasons) == 0.0
    assert any("spent" in r for r in reasons)


def test_higher_timeframe_outranks_lower_for_the_same_kind():
    daily = score_importance(kind="equal_highs", timeframe="1d", scope="external",
                             touch_count=2, swept=False, reasons=[])
    intraday = score_importance(kind="equal_highs", timeframe="15m", scope="external",
                                touch_count=2, swept=False, reasons=[])
    assert daily > intraday


def test_external_scope_outranks_internal():
    external = score_importance(kind="equal_highs", timeframe="1h", scope="external",
                                touch_count=2, swept=False, reasons=[])
    internal = score_importance(kind="equal_highs", timeframe="1h", scope="internal",
                                touch_count=2, swept=False, reasons=[])
    assert external > internal


def test_touch_count_refines_but_does_not_decide():
    """A triple-tapped 15m level is still not a prior daily high."""
    tapped_intraday = score_importance(kind="equal_highs", timeframe="15m", scope="internal",
                                       touch_count=4, swept=False, reasons=[])
    daily_level = score_importance(kind="prior_day_high", timeframe="1d", scope="external",
                                   touch_count=1, swept=False, reasons=[])
    assert daily_level > tapped_intraday


def test_every_score_carries_its_reason():
    reasons = []
    score_importance(kind="equal_lows", timeframe="4h", scope="external",
                     touch_count=2, swept=False, reasons=reasons)
    assert reasons and "equal_lows" in reasons[0]


# -- map assembly -------------------------------------------------------------


def _map():
    return build_liquidity_map(
        liquidity_levels=[
            _level("pdh", 66500.0, kind="prior_day_high", timeframe="1d"),
            _level("eqh_near", 64200.0, kind="equal_highs", timeframe="15m", touch_count=2),
            _level("eql_below", 62500.0, kind="equal_lows", timeframe="1h", touch_count=2),
            _level("taken", 63900.0, kind="equal_highs", timeframe="1h",
                   activity_status="consumed"),
        ],
        current_price=64000.0, range_high=66000.0, range_low=62000.0,
    )


def test_map_separates_swept_from_unswept():
    m = _map()
    assert {p.object_id for p in m.swept} == {"taken"}
    assert "taken" not in {p.object_id for p in m.unswept}


def test_map_splits_above_and_below_price():
    m = _map()
    assert {p.object_id for p in m.above()} == {"pdh", "eqh_near"}
    assert {p.object_id for p in m.below()} == {"eql_below"}


def test_sides_are_inferred_from_price_when_absent():
    m = _map()
    by_id = {p.object_id: p for p in m.pools}
    assert by_id["pdh"].side == "buy_side"
    assert by_id["eql_below"].side == "sell_side"


def test_map_is_serialisable_and_observe_only():
    payload = _map().to_dict()
    assert payload["schema"] == "liquidity_map_v1"
    assert payload["signal_allowed"] is False
    assert payload["counts"]["swept"] == 1


# -- the draw: importance beats proximity -------------------------------------


def test_draw_prefers_the_important_pool_over_the_nearest_one():
    """The heart of this module.

    A 15m equal-high sits 200 away; a prior daily high sits 2,500 away. The
    old 'nearest unswept pool' rule picked the 15m level. A trader targets the
    daily high and treats the 15m level as something taken on the way.
    """
    draw = resolve_draw(_map(), context_bias="bullish")
    assert draw is not None
    assert draw.object_id == "pdh", "importance must beat proximity"
    assert draw.kind == "prior_day_high"


def test_draw_respects_direction():
    draw = resolve_draw(_map(), context_bias="bearish")
    assert draw is not None and draw.object_id == "eql_below"


def test_draw_never_targets_swept_liquidity():
    m = build_liquidity_map(
        liquidity_levels=[
            _level("spent", 66500.0, kind="prior_day_high", timeframe="1d",
                   activity_status="consumed"),
            _level("live", 64500.0, kind="equal_highs", timeframe="1h", touch_count=2),
        ],
        current_price=64000.0, range_high=66000.0, range_low=62000.0,
    )
    draw = resolve_draw(m, context_bias="bullish")
    assert draw is not None and draw.object_id == "live"


def test_no_draw_without_directional_context():
    assert resolve_draw(_map(), context_bias="unknown") is None


def test_no_draw_when_nothing_remains_on_that_side():
    m = build_liquidity_map(
        liquidity_levels=[_level("below", 62500.0, kind="equal_lows")],
        current_price=64000.0, range_high=66000.0, range_low=62000.0,
    )
    assert resolve_draw(m, context_bias="bullish") is None


def test_ranking_is_deterministic():
    a = [p.object_id for p in _map().ranked()]
    b = [p.object_id for p in _map().ranked()]
    assert a == b


def test_malformed_levels_are_skipped_not_fatal():
    m = build_liquidity_map(
        liquidity_levels=[
            {"no_id": True},
            {"object_id": "no_price"},
            _level("good", 64500.0, kind="equal_highs"),
        ],
        current_price=64000.0,
    )
    assert {p.object_id for p in m.pools} == {"good"}
