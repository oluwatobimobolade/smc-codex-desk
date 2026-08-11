from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.data.schemas import Candle
from smc_desk.data.ohlcv_contract import (
    data_quality_report,
    load_ohlcv_csv,
    normalize_ohlcv_timestamps,
)
from smc_desk.data.timeframe_reconstruction import resample_ohlcv


def _local_load_ohlcv_csv(path: str) -> pd.DataFrame:
    """Load OHLCV through the pure canonical data contract."""
    return load_ohlcv_csv(path)


TIMEFRAME_DURATIONS = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}


@dataclass(frozen=True)
class RunMarketContext:
    source_df: pd.DataFrame
    history_15m: pd.DataFrame
    timeframe_dfs: dict[str, pd.DataFrame]
    requested_decision_time: pd.Timestamp
    decision_candle_open: pd.Timestamp
    decision_available_at: pd.Timestamp
    source_quality: dict[str, Any]


def parse_decision_time(value: str | None, df: pd.DataFrame) -> pd.Timestamp:
    if value is None:
        # Timestamps are candle opens. Default to the scheduled close of the
        # latest row so a fully closed source file does not silently step back
        # one candle. Live callers should still pass actual fetched_at time.
        return pd.Timestamp(df["timestamp"].iloc[-1]) + TIMEFRAME_DURATIONS["15m"]
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.tz_convert("UTC").tz_localize(None)


def load_local_15m(path: Path) -> pd.DataFrame:
    df = normalize_ohlcv_timestamps(_local_load_ohlcv_csv(str(path)))
    if df.empty:
        raise ValueError(f"OHLCV source is empty: {path}")
    return df


def slice_history(df: pd.DataFrame, requested_decision_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Return only candles whose scheduled close time is at or before the request.

    A 12:00 15m candle closes at 12:15. At 12:07, it is still forming and
    must be excluded — its OHLCV values are not finalized. Only candles that
    have fully closed by `requested_decision_time` enter confirmed history.
    """
    timestamps = pd.to_datetime(df["timestamp"], utc=False)
    close_times = timestamps + TIMEFRAME_DURATIONS["15m"]
    history = df.loc[close_times <= requested_decision_time].reset_index(drop=True)
    if history.empty:
        first_open = pd.Timestamp(df["timestamp"].iloc[0]).isoformat()
        first_close = pd.Timestamp(df["timestamp"].iloc[0]) + TIMEFRAME_DURATIONS["15m"]
        raise ValueError(
            f"Decision time {requested_decision_time.isoformat()} is before the first "
            f"fully closed candle ({first_open} closes at {first_close.isoformat()})."
        )
    decision_candle_open = pd.Timestamp(history["timestamp"].iloc[-1])
    return history, decision_candle_open


def build_timeframe_dfs(history_15m: pd.DataFrame, decision_available_at: pd.Timestamp) -> dict[str, pd.DataFrame]:
    return {
        "15m": history_15m.copy(),
        "1h": resample_ohlcv(history_15m, "1h", decision_available_at),
        "4h": resample_ohlcv(history_15m, "4h", decision_available_at),
        "1d": resample_ohlcv(history_15m, "1d", decision_available_at),
    }


def build_run_market_context(source_path: Path, decision_time: str | None) -> RunMarketContext:
    source_df = load_local_15m(source_path)
    requested = parse_decision_time(decision_time, source_df)
    history, candle_open = slice_history(source_df, requested)
    decision_available_at = candle_open + TIMEFRAME_DURATIONS["15m"]
    timeframe_dfs = build_timeframe_dfs(history, decision_available_at)
    return RunMarketContext(
        source_df=source_df,
        history_15m=history,
        timeframe_dfs=timeframe_dfs,
        requested_decision_time=requested,
        decision_candle_open=candle_open,
        decision_available_at=decision_available_at,
        source_quality=data_quality_report(source_df, expected_step_minutes=15),
    )


def _tz_aware(value: pd.Timestamp | datetime) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


SESSION_PROFILES = ("continuous", "forex_5d")

# Forex closes Friday ~21:00 UTC and reopens Sunday ~21:00 UTC. A wider window
# than the nominal 48 hours absorbs DST shifts and venue-specific open times
# without excusing a genuine mid-week hole.
_WEEKEND_MIN_HOURS = 24.0
_WEEKEND_MAX_HOURS = 75.0


def _is_expected_closure(
    previous_close: datetime,
    next_open: datetime,
    session_profile: str,
    *,
    timeframe: str | None = None,
) -> bool:
    """True when a timestamp discontinuity is a scheduled market closure.

    Only the weekend break qualifies, and only under a session-based profile.
    A missing candle inside an open session is still corruption and must still
    fail: this widens what counts as *expected*, never what counts as valid.
    """
    if session_profile != "forex_5d":
        return False
    hours = (next_open - previous_close).total_seconds() / 3600.0
    if timeframe == "1d":
        # Daily FX candles are session labels, not continuously traded 24-hour
        # buckets.  DST moves the UTC session boundary by one hour and bank
        # holidays can remove one or more whole daily labels.  Treat only this
        # bounded daily-session pattern as an expected closure; intraday holes
        # remain data defects.
        return -1.5 <= hours <= 120.0
    if not (_WEEKEND_MIN_HOURS <= hours <= _WEEKEND_MAX_HOURS):
        return False
    # The break must actually straddle the weekend: out on Friday or Saturday,
    # back on Sunday or Monday.
    return previous_close.weekday() in {4, 5} and next_open.weekday() in {6, 0}


def dataframe_to_candles(
    df: pd.DataFrame,
    *,
    venue: str,
    instrument: str,
    timeframe: str,
    reference_time: datetime | None = None,
    session_profile: str = "continuous",
) -> list[Candle]:
    """Convert historical DataFrame rows to Candle objects with quality metadata.

    Gap status is computed from actual timestamp continuity (not hardcoded as OK).
    Closure status is computed from the reference time (if provided) or marked as
    historical (closed, complete) when no reference is given.

    Args:
        df: Historical OHLCV DataFrame with timestamp column.
        venue: Exchange identifier.
        instrument: Symbol.
        timeframe: Bar duration key (e.g. "15m").
        reference_time: For live use, the wall-clock time at which closure status
            is evaluated. If None, all candles are treated as historical.
    """
    duration = TIMEFRAME_DURATIONS[timeframe]
    candles: list[Candle] = []
    prev_close_time: datetime | None = None

    for _, row in df.iterrows():
        open_time = _tz_aware(row["timestamp"])
        close_time = _tz_aware(pd.Timestamp(row["timestamp"]) + duration)

        # Compute gap status from actual timestamp continuity.
        has_gap = False
        if prev_close_time is not None:
            expected_open = prev_close_time
            if open_time != expected_open:
                # A discontinuity is only a data defect if the market was
                # actually open across it. Crypto trades continuously, so any
                # break is corruption. Forex closes each weekend, so the
                # Friday-to-Sunday gap is expected structure -- flagging it
                # made every forex instrument unanalysable, which is why the
                # session profile exists.
                has_gap = not _is_expected_closure(
                    prev_close_time,
                    open_time,
                    session_profile,
                    timeframe=timeframe,
                )
        prev_close_time = close_time

        # Compute closure status.
        if reference_time is not None:
            is_closed = close_time <= reference_time
            is_complete = is_closed
        else:
            # Historical data: all candles are treated as closed/complete unless
            # proven otherwise by the user via reference_time.
            is_closed = True
            is_complete = True

        candles.append(
            Candle(
                venue=venue,
                instrument=instrument,
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row.get("volume", 0.0))),
                trade_count=int(row.get("trade_count", 0) or 0),
                is_closed=is_closed,
                is_complete=is_complete,
                contains_gap=has_gap,
                source_event_start=open_time,
                source_event_end=close_time,
            )
        )
    return candles
