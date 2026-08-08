from __future__ import annotations

import pandas as pd

from tools.run_live_ai_smc_full_system import resample_ohlcv


def _hourly(periods: int) -> pd.DataFrame:
    timestamps = pd.date_range("2026-07-13 00:00", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index for index in range(periods)],
            "high": [101.0 + index for index in range(periods)],
            "low": [99.0 + index for index in range(periods)],
            "close": [100.5 + index for index in range(periods)],
            "volume": [10.0] * periods,
        }
    )


def test_resample_excludes_forming_four_hour_bucket() -> None:
    # Closed source candles run through 10:00-11:00. The 08:00-12:00
    # four-hour bucket is still forming at the 11:00 decision cutoff.
    result = resample_ohlcv(_hourly(11), "4h", decision_time="2026-07-13T11:00:00Z")

    assert list(result["timestamp"]) == [
        pd.Timestamp("2026-07-13T00:00:00Z"),
        pd.Timestamp("2026-07-13T04:00:00Z"),
    ]


def test_resample_includes_bucket_closing_exactly_at_cutoff() -> None:
    result = resample_ohlcv(_hourly(12), "4h", decision_time="2026-07-13T12:00:00Z")

    assert pd.Timestamp("2026-07-13T08:00:00Z") in set(result["timestamp"])
    assert (pd.to_datetime(result["timestamp"]) + pd.Timedelta("4h") <= pd.Timestamp("2026-07-13T12:00:00Z")).all()
