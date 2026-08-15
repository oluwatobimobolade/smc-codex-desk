"""Scoring logged decisions against the market, with no human in the loop.

The constitution names human alignment as `optional_external_audit_not_
autonomous_truth_owner`. These tests hold the boundary that makes that possible:
the resolver must score only from candles the decision could not have seen, and
must refuse rather than guess when the market has not yet produced enough of them.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from smc_desk.evaluation.outcome_resolution import (
    FROZEN_OUTCOME_DEFINITION,
    LookaheadError,
    first_barrier_hit,
    forward_window,
    resolve_decision_outcome,
)

DECIDED_AT = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
ATR = 1.0


def _candles(closes, *, start=DECIDED_AT, freq="15min", highs=None, lows=None) -> pd.DataFrame:
    stamps = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": closes,
            "high": highs if highs is not None else [c + 0.05 for c in closes],
            "low": lows if lows is not None else [c - 0.05 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


def _decision(prediction="BEARISH", decision="REFUSE") -> dict:
    return {
        "event_type": "DECISION",
        "case_id": "BTCUSDT:2026-08-14T12:00:00+00:00",
        "symbol": "BTCUSDT",
        "decision_time": DECIDED_AT,
        "decision": decision,
        "shadow_prediction": prediction,
    }


# -- the boundary that matters ------------------------------------------------


def test_a_candle_opening_before_the_decision_is_refused_not_scored() -> None:
    """The exact leak this project has recorded before, as a hard failure."""
    early = _candles([100.0] * 20, start=DECIDED_AT - pd.Timedelta(minutes=15))
    with pytest.raises(LookaheadError, match="before the decision"):
        resolve_decision_outcome(_decision(), early, atr=ATR)


def test_a_candle_opening_exactly_at_the_decision_is_legitimate() -> None:
    """decision_time is the last close, so the next bar opens on it."""
    result = resolve_decision_outcome(_decision(), _candles([100.0] * 20), atr=ATR)
    assert result.state == "RESOLVED"


def test_forward_window_admits_from_the_decision_open_onward() -> None:
    frame = _candles([100.0] * 10, start=DECIDED_AT - pd.Timedelta(hours=1))
    window = forward_window(frame, decision_time=DECIDED_AT)
    assert len(window) == 6  # 5 bars before the cutoff are dropped
    assert pd.Timestamp(window["timestamp"].iloc[0]) == pd.Timestamp(DECIDED_AT)


def test_forward_window_respects_the_limit() -> None:
    frame = _candles([100.0] * 50)
    assert len(forward_window(frame, decision_time=DECIDED_AT, limit=20)) == 20


# -- refusing rather than guessing --------------------------------------------


def test_too_little_market_is_unresolved_not_scored() -> None:
    """Scoring a short window would quietly shorten the frozen horizon."""
    result = resolve_decision_outcome(_decision(), _candles([100.0] * 19), atr=ATR)
    assert result.state == "UNRESOLVED"
    assert result.shadow_prediction_correct is None


def test_missing_atr_is_a_data_failure_not_a_zero_barrier() -> None:
    for bad in (None, 0.0, -1.0):
        assert resolve_decision_outcome(_decision(), _candles([100.0] * 20), atr=bad).state == "DATA_FAILED"


def test_a_data_failed_decision_made_no_judgement_to_score() -> None:
    result = resolve_decision_outcome(_decision(decision="DATA_FAILED"), _candles([100.0] * 20), atr=ATR)
    assert result.state == "DATA_FAILED"


def test_a_decision_with_no_recorded_read_is_unresolved() -> None:
    payload = _decision()
    payload["shadow_prediction"] = None
    assert resolve_decision_outcome(payload, _candles([100.0] * 20), atr=ATR).state == "UNRESOLVED"


def test_empty_forward_data_is_unresolved() -> None:
    assert resolve_decision_outcome(_decision(), pd.DataFrame(), atr=ATR).state == "UNRESOLVED"


# -- the verdicts themselves --------------------------------------------------


def test_a_correct_bearish_refusal_is_recorded_as_a_missed_opportunity() -> None:
    """This is the number that tells the founder what caution costs."""
    falling = [100.0 - 0.2 * i for i in range(20)]
    result = resolve_decision_outcome(_decision("BEARISH"), _candles(falling), atr=ATR)
    assert result.state == "RESOLVED"
    assert result.shadow_prediction_correct is True
    assert result.favorable_opportunity is True
    assert result.outcome_return_bps > 0  # signed in the predicted direction


def test_a_wrong_bearish_read_is_neither_correct_nor_favorable() -> None:
    rising = [100.0 + 0.2 * i for i in range(20)]
    result = resolve_decision_outcome(_decision("BEARISH"), _candles(rising), atr=ATR)
    assert result.shadow_prediction_correct is False
    assert result.favorable_opportunity is False
    assert result.outcome_return_bps < 0


def test_bullish_mirrors_bearish() -> None:
    rising = [100.0 + 0.2 * i for i in range(20)]
    result = resolve_decision_outcome(_decision("BULLISH"), _candles(rising), atr=ATR)
    assert result.shadow_prediction_correct is True
    assert result.favorable_opportunity is True


def test_a_move_inside_the_neutral_band_does_not_verify_a_direction() -> None:
    """A drift of a fifth of an ATR is not evidence the read was right."""
    drifting = [100.0 - 0.01 * i for i in range(20)]
    result = resolve_decision_outcome(_decision("BEARISH"), _candles(drifting), atr=ATR)
    assert result.shadow_prediction_correct is False


def test_neutral_verifies_by_nothing_happening_and_offers_no_trade() -> None:
    result = resolve_decision_outcome(_decision("NEUTRAL"), _candles([100.0] * 20), atr=ATR)
    assert result.shadow_prediction_correct is True
    assert result.favorable_opportunity is False


def test_neutral_is_wrong_when_the_market_ran() -> None:
    running = [100.0 + 0.2 * i for i in range(20)]
    result = resolve_decision_outcome(_decision("NEUTRAL"), _candles(running), atr=ATR)
    assert result.shadow_prediction_correct is False


# -- barrier mechanics --------------------------------------------------------


def test_barrier_reports_whichever_side_price_reached_first() -> None:
    frame = _candles([100.0] * 5, highs=[100.1, 100.2, 101.5, 100.2, 100.1],
                     lows=[99.9, 99.8, 99.8, 98.5, 99.9])
    assert first_barrier_hit(frame, reference_price=100.0, barrier_distance=1.0) == "up"


def test_a_bar_spanning_both_barriers_resolves_to_none() -> None:
    """Intrabar order is unknowable; guessing it is how backtests flatter themselves."""
    frame = _candles([100.0], highs=[101.5], lows=[98.5])
    assert first_barrier_hit(frame, reference_price=100.0, barrier_distance=1.0) == "none"


def test_no_barrier_touched_is_none() -> None:
    frame = _candles([100.0] * 5)
    assert first_barrier_hit(frame, reference_price=100.0, barrier_distance=1.0) == "none"


def test_a_spanning_bar_makes_a_directional_read_unfavorable() -> None:
    """Ambiguity must not be resolved in the system's favour."""
    closes = [100.0] + [98.0] * 19
    highs = [101.5] + [98.05] * 19
    lows = [98.5] + [97.95] * 19
    result = resolve_decision_outcome(
        _decision("BEARISH"), _candles(closes, highs=highs, lows=lows), atr=ATR
    )
    assert result.favorable_opportunity is False  # barrier ambiguous...
    assert result.shadow_prediction_correct is True  # ...though the close verified


# -- provenance ---------------------------------------------------------------


def test_every_outcome_names_the_rule_that_produced_it() -> None:
    result = resolve_decision_outcome(_decision(), _candles([100.0] * 20), atr=ATR)
    assert result.outcome_definition == FROZEN_OUTCOME_DEFINITION
    assert "triple_barrier" in result.outcome_definition


def test_source_hashes_are_carried_through() -> None:
    result = resolve_decision_outcome(
        _decision(), _candles([100.0] * 20), atr=ATR, source_hashes={"candles_sha256": "abc"}
    )
    assert result.source_hashes == {"candles_sha256": "abc"}
