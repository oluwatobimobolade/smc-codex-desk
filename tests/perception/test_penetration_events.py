"""A penetration is price taking a level the system already knew about.

The failure modes here are the ones this repository has hit before: counting an
interaction with a level that had not been confirmed yet (lookahead), and
conflating a wick-through with a body-close break. Both are pinned below.
"""
from __future__ import annotations

import pandas as pd
import pytest

from smc_desk.perception.penetration_events import (
    deduplicate_by_bar,
    extract_penetration_events,
)

HIGH = "bearish"  # a swing high tops a bearish turn
LOW = "bullish"


def candles(rows) -> pd.DataFrame:
    """rows: [(high, low, close)] starting 2026-01-01, hourly."""
    stamps = pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame({
        "timestamp": stamps,
        "open": [r[2] for r in rows],
        "high": [r[0] for r in rows],
        "low": [r[1] for r in rows],
        "close": [r[2] for r in rows],
        "volume": [1.0] * len(rows),
    })


def swing(object_id="s1", *, side=HIGH, price=110.0, confirmed_hour=2) -> dict:
    return {
        "object_id": object_id,
        "direction": side,
        "confirmation_status": "confirmed",
        "confirmed_at": str(pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=confirmed_hour)),
        "price_high": price if side == HIGH else price - 1.0,
        "price_low": price if side == LOW else price - 1.0,
    }


# -- the lookahead boundary ---------------------------------------------------


def test_an_interaction_before_confirmation_is_not_a_penetration() -> None:
    """The system cannot react to a level it has not identified yet.

    Price spikes through 110 at hour 1, but the swing is only confirmed at
    hour 4. Counting that spike would credit the system with knowing a level
    two bars before it could have detected one.
    """
    frame = candles([
        (105, 100, 102),
        (115, 104, 106),   # trades through 110, but the swing is not confirmed yet
        (108, 103, 105),
        (108, 103, 105),
        (109, 104, 106),
    ])
    assert extract_penetration_events([swing(confirmed_hour=4)], frame) == []


def test_the_confirming_bar_itself_is_not_an_interaction() -> None:
    """Confirmation establishes the swing; it is not a later visit to it."""
    frame = candles([
        (105, 100, 102),
        (108, 103, 105),
        (112, 104, 106),   # this IS the confirmation bar
        (106, 101, 103),
    ])
    assert extract_penetration_events([swing(confirmed_hour=2)], frame) == []


def test_a_penetration_after_confirmation_is_recorded() -> None:
    frame = candles([
        (105, 100, 102),
        (108, 103, 105),
        (106, 101, 103),
        (112, 104, 111),   # hour 3, after confirmation at hour 2
    ])
    events = extract_penetration_events([swing(confirmed_hour=2)], frame)
    assert len(events) == 1
    assert events[0].bar_index == 3
    assert events[0].bars_since_confirmation == 1


# -- wick versus close --------------------------------------------------------


def test_a_wick_through_counts_because_resting_stops_fill_on_the_trade() -> None:
    """This is what separates a penetration from a structure break.

    Osler's cascade is about orders beyond the level being filled. A wick fills
    them just as surely as a close does.
    """
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103),
        (112, 104, 106),   # wick above 110, closes back below
    ])
    events = extract_penetration_events([swing(confirmed_hour=2)], frame)
    assert len(events) == 1
    assert events[0].closed_beyond is False


def test_a_close_beyond_is_flagged_but_is_still_one_penetration() -> None:
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103),
        (112, 104, 111),
    ])
    assert extract_penetration_events([swing(confirmed_hour=2)], frame)[0].closed_beyond is True


def test_touching_the_level_exactly_is_not_trading_through_it() -> None:
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103),
        (110, 104, 106),   # equals the level, does not exceed it
    ])
    assert extract_penetration_events([swing(confirmed_hour=2)], frame) == []


# -- first touch only ---------------------------------------------------------


def test_only_the_first_touch_counts_because_the_orders_are_gone_after_it() -> None:
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103),
        (112, 104, 106),   # first
        (105, 100, 102),
        (118, 104, 116),   # second visit -- not another penetration
    ])
    events = extract_penetration_events([swing(confirmed_hour=2)], frame)
    assert [e.bar_index for e in events] == [3]


# -- swing lows mirror swing highs --------------------------------------------


def test_a_swing_low_is_penetrated_from_above() -> None:
    frame = candles([
        (105, 100, 102), (104, 99, 101), (103, 98, 100),
        (102, 88, 95),    # trades below the 90 low
    ])
    events = extract_penetration_events([swing(side=LOW, price=90.0, confirmed_hour=2)], frame)
    assert len(events) == 1 and events[0].side == "low"
    assert events[0].penetration_depth == pytest.approx(2.0)


def test_penetration_depth_measures_how_far_beyond() -> None:
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103), (113, 104, 106),
    ])
    assert extract_penetration_events([swing(confirmed_hour=2)], frame)[0].penetration_depth == pytest.approx(3.0)


# -- hygiene ------------------------------------------------------------------


def test_unconfirmed_swings_are_ignored() -> None:
    payload = swing(confirmed_hour=2)
    payload["confirmation_status"] = "candidate"
    frame = candles([(105, 100, 102), (108, 103, 105), (106, 101, 103), (112, 104, 106)])
    assert extract_penetration_events([payload], frame) == []


def test_a_level_never_reached_yields_nothing() -> None:
    frame = candles([(105, 100, 102), (108, 103, 105), (106, 101, 103), (107, 102, 104)])
    assert extract_penetration_events([swing(confirmed_hour=2)], frame) == []


def test_empty_and_malformed_input_is_handled() -> None:
    assert extract_penetration_events([swing()], pd.DataFrame()) == []
    assert extract_penetration_events([swing()], pd.DataFrame({"high": [1.0]})) == []
    assert extract_penetration_events([], candles([(1, 0, 0.5)])) == []


# -- deduplication ------------------------------------------------------------


def test_stacked_levels_taken_by_one_candle_are_one_event() -> None:
    """Three swings at similar prices taken together is one liquidity event.

    Counting them separately would inflate n with observations sharing a single
    outcome window -- the dependence a block bootstrap models, smuggled in as
    extra sample size.
    """
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103), (120, 104, 118),
    ])
    swings = [
        swing("a", price=110.0, confirmed_hour=2),
        swing("b", price=112.0, confirmed_hour=2),
        swing("c", price=114.0, confirmed_hour=2),
    ]
    raw = extract_penetration_events(swings, frame)
    assert len(raw) == 3
    deduped = deduplicate_by_bar(raw)
    assert len(deduped) == 1
    # The deepest survivor is the one whose level was furthest exceeded.
    assert deduped[0].swing_object_id == "a"


def test_highs_and_lows_on_the_same_bar_stay_separate_events() -> None:
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103), (120, 85, 118),
    ])
    swings = [swing("hi", price=110.0, confirmed_hour=2),
              swing("lo", side=LOW, price=90.0, confirmed_hour=2)]
    deduped = deduplicate_by_bar(extract_penetration_events(swings, frame))
    assert {e.side for e in deduped} == {"high", "low"}


def test_events_are_returned_in_chart_order() -> None:
    frame = candles([
        (105, 100, 102), (108, 103, 105), (106, 101, 103),
        (112, 104, 106), (105, 100, 102), (95, 85, 90),
    ])
    swings = [swing("late_low", side=LOW, price=90.0, confirmed_hour=2),
              swing("early_high", price=110.0, confirmed_hour=2)]
    events = extract_penetration_events(swings, frame)
    assert [e.bar_index for e in events] == sorted(e.bar_index for e in events)
