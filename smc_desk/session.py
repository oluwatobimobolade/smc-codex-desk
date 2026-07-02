from __future__ import annotations

import pandas as pd


def classify_session_hour(hour: int) -> str:
    if 0 <= hour < 7:
        return "Asia"
    if 7 <= hour < 13:
        return "London"
    if 13 <= hour < 21:
        return "New York"
    return "After Hours"


def summarize_session_context(df: pd.DataFrame) -> dict[str, float | int | str | None]:
    if df.empty:
        return {
            "current_session": None,
            "session_high": None,
            "session_low": None,
            "latest_close": None,
        }

    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    latest_timestamp = timestamps.iloc[-1]
    current_session = classify_session_hour(int(latest_timestamp.hour))
    latest_date = latest_timestamp.normalize()
    today_mask = timestamps.dt.normalize() == latest_date
    today_df = df.loc[today_mask]
    if not today_df.empty:
        today_timestamps = pd.to_datetime(today_df["timestamp"], utc=True)
        same_session_mask = today_timestamps.map(lambda value: classify_session_hour(int(value.hour)) == current_session)
        session_rows = today_df.loc[same_session_mask]
    else:
        session_rows = df.tail(min(16, len(df)))
    if session_rows.empty:
        session_rows = df.tail(min(16, len(df)))

    return {
        "current_session": current_session,
        "session_high": float(session_rows["high"].max()),
        "session_low": float(session_rows["low"].min()),
        "latest_close": float(df["close"].iloc[-1]),
        "bars_in_session_sample": int(len(session_rows)),
        "session_date": str(latest_date.date()),
    }
