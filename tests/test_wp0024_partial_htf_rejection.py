"""WP-0024 Stage E: partial-HTF candle rejection contract.

The MTF layer already drops in-progress HTF candles broadly (see
``tests/test_mtf.py::MtfLeakageTests``). This file locks the off-by-one
boundary and the forming-bucket-from-incomplete-15m case — the exact
silent-leakage failure mode where a half-formed HTF bucket could fold
not-yet-closed sub-candles into a decision.

These are refusal/integrity guarantees: a forming HTF candle must never
reach detector candidates, the formal structure graph, or the decision.
The perception and graph layers consume ``slice_precomputed_htf`` /
``resample_ohlcv`` output, so the contract they depend on is that every
returned HTF row has ``_close_visible_at <= decision_time`` and that no
partial bucket's OHLC is aggregated into an included row.
"""
from __future__ import annotations

import pandas as pd

from smc_desk.data.timeframe_reconstruction import (
    precompute_htf_series,
    resample_ohlcv,
    slice_precomputed_htf,
)
from tests.test_mtf import candles


def _close_times(frame: pd.DataFrame, duration: pd.Timedelta) -> pd.Series:
    if "_close_visible_at" in frame.columns:
        return pd.to_datetime(frame["_close_visible_at"])
    return pd.to_datetime(frame["timestamp"]) + duration


_DURATIONS = {"1h": pd.Timedelta("1h"), "4h": pd.Timedelta("4h"), "1d": pd.Timedelta("1D")}


def test_htf_candle_closing_exactly_at_decision_time_is_included() -> None:
    """A HTF candle whose close time equals decision_time is visible (<=)."""
    rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
    df = candles(rows, freq="15min")
    precomputed = precompute_htf_series(df)

    for tf, duration in _DURATIONS.items():
        # The 1h bucket opening at 00:00 closes at 01:00; the 4h bucket opening
        # at 00:00 closes at 04:00; the 1d bucket opening at 00:00 closes at 1D.
        bucket_open = pd.Timestamp("2026-01-01 00:00:00")
        decision_time = bucket_open + duration
        sliced = slice_precomputed_htf(precomputed[tf], tf, decision_time)
        assert bucket_open in set(pd.to_datetime(sliced["timestamp"])), f"{tf}: exactly-closed bucket should be visible"
        # The bucket that opens AT decision_time is still forming and must be excluded.
        assert decision_time not in set(pd.to_datetime(sliced["timestamp"])), f"{tf}: bucket opening at decision_time must be dropped"


def test_htf_candle_closing_one_tick_after_decision_time_is_excluded() -> None:
    """A HTF candle closing one 15m tick after decision_time is not visible."""
    rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
    df = candles(rows, freq="15min")
    precomputed = precompute_htf_series(df)
    tick = pd.Timedelta("15min")

    for tf, duration in _DURATIONS.items():
        bucket_open = pd.Timestamp("2026-01-01 00:00:00")
        bucket_close = bucket_open + duration
        decision_time = bucket_close - tick  # one tick before the bucket closes
        sliced = slice_precomputed_htf(precomputed[tf], tf, decision_time)
        timestamps = set(pd.to_datetime(sliced["timestamp"]))
        assert bucket_open not in timestamps, f"{tf}: bucket closing one tick after decision_time must be excluded"
        close_times = _close_times(sliced, duration)
        if not close_times.empty:
            assert (close_times <= decision_time).all(), f"{tf}: a visible HTF candle closes after decision_time"


def test_forming_1h_bucket_from_incomplete_15m_subcandles_is_dropped() -> None:
    """A 1h bucket only partially assembled at decision_time is not returned."""
    rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
    df = candles(rows, freq="15min")
    precomputed = precompute_htf_series(df)

    # decision_time 01:30 sits inside the 01:00 1h bucket (sub-candles 01:00, 01:15 closed;
    # 01:30, 01:45 still open). The 01:00 bucket is forming and must be dropped.
    decision_time = pd.Timestamp("2026-01-01 01:30:00")
    sliced = slice_precomputed_htf(precomputed["1h"], "1h", decision_time)
    timestamps = set(pd.to_datetime(sliced["timestamp"]))
    assert pd.Timestamp("2026-01-01 01:00:00") not in timestamps, "forming 1h bucket must be dropped"
    # The last fully-closed 1h bucket is the 00:00 one (closes at 01:00 <= 01:30).
    assert not sliced.empty
    assert pd.to_datetime(sliced["timestamp"].iloc[-1]) == pd.Timestamp("2026-01-01 00:00:00")


def test_forming_bucket_partial_ohlc_is_not_aggregated_into_included_rows() -> None:
    """An extreme price inside a forming HTF bucket must not inflate any included HTF candle."""
    rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(200)]
    df = candles(rows, freq="15min")
    # Inject an extreme high into a 15m sub-candle that belongs to the forming 01:00 1h bucket.
    # The 01:15 15m candle closes at 01:30 — closed, so it is legitimately visible at 15m — but it
    # must NOT be aggregated into a 1h bucket that is still forming at decision_time 01:30.
    df.loc[df["timestamp"] == pd.Timestamp("2026-01-01 01:15:00"), "high"] = 999.0
    precomputed = precompute_htf_series(df)

    decision_time = pd.Timestamp("2026-01-01 01:30:00")
    sliced = slice_precomputed_htf(precomputed["1h"], "1h", decision_time)
    assert not sliced.empty
    assert float(sliced["high"].max()) < 999.0, "forming-bucket extreme high leaked into an included 1h candle"
    assert pd.Timestamp("2026-01-01 01:00:00") not in set(pd.to_datetime(sliced["timestamp"]))


def test_sliced_frame_carries_no_future_close_times_for_all_htfs() -> None:
    """Contract the perception + graph layers depend on: every HTF row closes by decision_time."""
    rows = [(100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.1, 100 + i * 0.1) for i in range(300)]
    df = candles(rows, freq="15min")
    precomputed = precompute_htf_series(df)
    # decision_time deliberately mid-bucket for each HTF.
    decision_time = pd.Timestamp("2026-01-01 02:30:00")

    for tf, duration in _DURATIONS.items():
        sliced = slice_precomputed_htf(precomputed[tf], tf, decision_time)
        assert (_close_times(sliced, duration) <= decision_time).all(), f"{tf}: future close time present"
        # The two paths the pipeline uses must agree on row count and last timestamp.
        direct = resample_ohlcv(df, tf, decision_time)
        assert len(sliced) == len(direct), f"{tf}: slice vs direct resample disagree"
        if not sliced.empty:
            assert sliced["timestamp"].iloc[-1] == direct["timestamp"].iloc[-1], f"{tf}: last HTF timestamp differs"
