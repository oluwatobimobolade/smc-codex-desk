"""Pure 15m-to-HTF reconstruction utilities.

Unlike ``smc_desk.mtf``, this module has no strategy, detector, or legacy
engine imports.  It is therefore safe for canonical market-context building.
Strict source-row certification lives in ``market_truth_certificate``; these
helpers preserve the existing general/sessioned-market resampling interface.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd


TimeframeKey = Literal["1h", "4h", "1d"]

TF_TO_PANDAS_RULE: dict[TimeframeKey, str] = {
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}

TF_TO_DURATION: dict[str, pd.Timedelta] = {
    "15m": pd.Timedelta("15min"),
    "1h": pd.Timedelta("1h"),
    "4h": pd.Timedelta("4h"),
    "1d": pd.Timedelta("1D"),
}


def resample_to_ny_close_daily(df_15m: pd.DataFrame) -> pd.DataFrame:
    if df_15m.empty:
        return df_15m.copy()

    frame = df_15m.copy()
    frame["_ts"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["_ts_eastern"] = frame["_ts"].dt.tz_convert("US/Eastern")
    frame["_ts_shifted"] = frame["_ts_eastern"] - pd.Timedelta(hours=17)
    indexed = frame.set_index("_ts_shifted")
    resampled = indexed.resample("1D", label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    unshifted_index = resampled.index + pd.Timedelta(hours=17)
    resampled["timestamp"] = unshifted_index.tz_convert("UTC").tz_localize(None)
    resampled = resampled.reset_index(drop=True)
    resampled["_close_visible_at"] = resampled["timestamp"] + pd.Timedelta("1D")
    return resampled


def precompute_htf_series(
    df_15m: pd.DataFrame,
    daily_session_profile: str = "exchange_daily_utc",
) -> dict[TimeframeKey, pd.DataFrame]:
    if df_15m.empty:
        return {tf: df_15m.copy() for tf in TF_TO_PANDAS_RULE}

    timestamps = pd.to_datetime(df_15m["timestamp"], utc=True).dt.tz_convert(None)
    indexed = df_15m.assign(_ts=timestamps).set_index("_ts")
    result: dict[TimeframeKey, pd.DataFrame] = {}
    for timeframe, rule in TF_TO_PANDAS_RULE.items():
        if timeframe == "1d" and daily_session_profile == "new_york_close_daily":
            result[timeframe] = resample_to_ny_close_daily(df_15m)
            continue
        resampled = indexed.resample(rule, label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        resampled = resampled.reset_index().rename(columns={"_ts": "timestamp"})
        resampled["_close_visible_at"] = (
            pd.to_datetime(resampled["timestamp"], utc=False)
            + TF_TO_DURATION[timeframe]
        )
        result[timeframe] = resampled
    return result


def slice_precomputed_htf(
    htf_df: pd.DataFrame,
    target_tf: TimeframeKey,
    decision_time: pd.Timestamp,
) -> pd.DataFrame:
    if htf_df.empty:
        return htf_df.copy()
    decision = _utc_naive(decision_time)
    if "_close_visible_at" in htf_df.columns:
        close_times = pd.to_datetime(htf_df["_close_visible_at"], utc=True).dt.tz_convert(None)
    else:
        close_times = (
            pd.to_datetime(htf_df["timestamp"], utc=True).dt.tz_convert(None)
            + TF_TO_DURATION[target_tf]
        )
    return htf_df.loc[close_times <= decision].reset_index(drop=True)


def resample_ohlcv(
    df: pd.DataFrame,
    target_tf: TimeframeKey,
    decision_time: pd.Timestamp,
    daily_session_profile: str = "exchange_daily_utc",
) -> pd.DataFrame:
    if target_tf not in TF_TO_PANDAS_RULE:
        raise ValueError(f"Unsupported target timeframe: {target_tf}")
    if df.empty:
        return df.copy()
    precomputed = precompute_htf_series(
        df,
        daily_session_profile=daily_session_profile,
    )
    return slice_precomputed_htf(precomputed[target_tf], target_tf, decision_time)


def _utc_naive(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.tz_convert("UTC").tz_localize(None)
