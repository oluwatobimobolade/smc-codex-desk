from datetime import datetime, timedelta, timezone

from smc_desk.perception.experimental_break_engine import (
    BreakLevel,
    ExperimentalBreakLifecycleEngine,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(index, open_, high, low, close):
    return {
        "close_time": (BASE + timedelta(minutes=15 * index)).isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


def _accepted_candles():
    return [
        _candle(0, 99.6, 100.8, 99.5, 100.7),
        _candle(1, 100.7, 101.0, 100.4, 100.8),
        _candle(2, 100.8, 101.2, 100.6, 101.0),
    ]


def _level(**changes):
    values = {
        "level_id": "swing-high-1",
        "price": 100.0,
        "break_direction": "bullish",
        "scope": "external",
        "prior_direction": "bullish",
    }
    values.update(changes)
    return BreakLevel(**values)


def test_first_accepted_break_is_initial_direction_not_bos():
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(prior_direction=None),
        candles=_accepted_candles(),
        atr=1.0,
        decision_time=_accepted_candles()[-1]["close_time"],
    )

    assert result.event_type == "INITIAL_DIRECTION_BREAK"
    assert result.lifecycle_state == "ACCEPTED_BREAKOUT"


def test_wick_only_penetration_is_probe_not_break():
    candles = [_candle(0, 99.7, 100.4, 99.5, 99.9)]
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(), candles=candles, atr=1.0, decision_time=candles[-1]["close_time"]
    )

    assert result.event_type == "WICK_PROBE"
    assert result.body_close_time is None


def test_wick_probe_expires_instead_of_confirming_from_a_stale_interaction():
    candles = [_candle(0, 99.7, 100.4, 99.5, 99.9)]
    candles.extend(_candle(i, 99.8, 99.95, 99.6, 99.8) for i in range(1, 8))
    # A much later close above the old level must not revive the expired probe.
    candles.append(_candle(8, 99.6, 100.9, 99.5, 100.7))
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(), candles=candles, atr=1.0, decision_time=candles[-1]["close_time"]
    )

    assert result.event_type == "EXPIRED_WICK_PROBE"
    assert result.lifecycle_state == "EXPIRED"
    assert result.body_close_time is None
    assert result.bars_observed_after_interaction >= 6


def test_weak_external_body_close_is_not_accepted():
    candles = [_candle(0, 99.99, 100.06, 99.98, 100.02)] + [
        _candle(i, 100.01, 100.05, 99.99, 100.01) for i in range(1, 7)
    ]
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(), candles=candles, atr=1.0, decision_time=candles[-1]["close_time"]
    )

    assert result.event_type == "FAILED_BREAKOUT"
    assert "displacement_score_below_external_threshold" in result.reasons


def test_internal_opposite_acceptance_is_choch():
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(scope="internal", prior_direction="bearish"),
        candles=_accepted_candles(),
        atr=1.0,
        decision_time=_accepted_candles()[-1]["close_time"],
    )

    assert result.event_type == "INTERNAL_CHOCH_BULLISH"


def test_same_direction_external_acceptance_is_bos():
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(prior_direction="bullish"),
        candles=_accepted_candles(),
        atr=1.0,
        decision_time=_accepted_candles()[-1]["close_time"],
    )

    assert result.event_type == "EXTERNAL_BOS_BULLISH"


def test_external_opposite_is_mss_candidate_until_parent_is_invalidated():
    candidate = ExperimentalBreakLifecycleEngine().classify(
        level=_level(prior_direction="bearish", invalidates_parent_narrative=False),
        candles=_accepted_candles(),
        atr=1.0,
        decision_time=_accepted_candles()[-1]["close_time"],
    )
    confirmed = ExperimentalBreakLifecycleEngine().classify(
        level=_level(prior_direction="bearish", invalidates_parent_narrative=True),
        candles=_accepted_candles(),
        atr=1.0,
        decision_time=_accepted_candles()[-1]["close_time"],
    )

    assert candidate.event_type == "EXTERNAL_MSS_CANDIDATE_BULLISH"
    assert confirmed.event_type == "EXTERNAL_MSS_CONFIRMED_BULLISH"


def test_future_rows_cannot_change_decision_time_classification():
    visible = [_candle(0, 99.6, 100.8, 99.5, 100.7)]
    future = [_candle(1, 100.7, 101.0, 99.0, 99.2), _candle(2, 99.2, 99.5, 98.5, 98.8)]
    engine = ExperimentalBreakLifecycleEngine()
    cutoff = visible[-1]["close_time"]

    without_future = engine.classify(level=_level(), candles=visible, atr=1.0, decision_time=cutoff)
    with_future = engine.classify(level=_level(), candles=visible + future, atr=1.0, decision_time=cutoff)

    assert without_future.to_dict() == with_future.to_dict()
    assert with_future.event_type == "BREAKOUT_CANDIDATE"


def test_signal_authority_is_always_false():
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(),
        candles=_accepted_candles(),
        atr=1.0,
        decision_time=_accepted_candles()[-1]["close_time"],
    )

    assert result.authority_contract["signal_allowed"] is False
    assert result.authority_contract["live_execution_allowed"] is False


def test_wrong_direction_body_close_cannot_be_accepted():
    candles = [_candle(0, 101.4, 101.5, 100.2, 100.7)] + [
        _candle(i, 100.7, 101.0, 100.4, 100.8) for i in range(1, 7)
    ]
    result = ExperimentalBreakLifecycleEngine().classify(
        level=_level(), candles=candles, atr=1.0, decision_time=candles[-1]["close_time"]
    )

    assert result.event_type == "FAILED_BREAKOUT"
    assert "displacement_direction_mismatch" in result.reasons
    assert "gap_open_requires_separate_interaction_policy" in result.reasons


def test_bearish_lifecycle_is_symmetric():
    candles = [
        _candle(0, 100.4, 100.5, 99.2, 99.3),
        _candle(1, 99.3, 99.6, 99.0, 99.2),
        _candle(2, 99.2, 99.4, 98.8, 99.0),
    ]
    result = ExperimentalBreakLifecycleEngine().classify(
        level=BreakLevel(
            level_id="swing-low-1",
            price=100.0,
            break_direction="bearish",
            scope="external",
            prior_direction="bullish",
            invalidates_parent_narrative=True,
        ),
        candles=candles,
        atr=1.0,
        decision_time=candles[-1]["close_time"],
    )

    assert result.event_type == "EXTERNAL_MSS_CONFIRMED_BEARISH"
