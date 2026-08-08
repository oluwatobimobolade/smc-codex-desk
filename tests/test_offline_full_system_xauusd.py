from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.run_offline_full_system_xauusd import load_local_timeframes


def _write_xau_15m(path: Path, *, periods: int = 120) -> Path:
    timestamps = pd.date_range("2026-07-07 00:00", periods=periods, freq="15min", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [3300.0 + idx * 0.1 for idx in range(periods)],
            "high": [3300.4 + idx * 0.1 for idx in range(periods)],
            "low": [3299.8 + idx * 0.1 for idx in range(periods)],
            "close": [3300.2 + idx * 0.1 for idx in range(periods)],
            "volume": [1000.0 + idx for idx in range(periods)],
        }
    )
    output = path / "XAUUSD_15m.csv"
    frame.to_csv(output, index=False)
    return output


def test_offline_xau_uses_cutoff_and_derives_only_completed_htf_buckets(tmp_path: Path) -> None:
    _write_xau_15m(tmp_path)

    frames, manifest = load_local_timeframes(tmp_path, "2026-07-07T06:30:00Z", "XAUUSD")

    assert pd.Timestamp(frames["15m"]["timestamp"].iloc[-1]) == pd.Timestamp("2026-07-07T06:15:00")
    assert pd.Timestamp(frames["1h"]["timestamp"].iloc[-1]) == pd.Timestamp("2026-07-07T05:00:00")
    assert pd.Timestamp("2026-07-07T06:00:00") not in set(pd.to_datetime(frames["1h"]["timestamp"]))
    assert manifest["live_read"] is False
    assert manifest["network_fetch_attempted"] is False
    assert manifest["htf_policy"] == "derived_from_15m_completed_buckets_only"
    assert all(item["canonical_timeframe"] == "15m" for item in manifest["timeframes"].values())


def test_offline_xau_rejects_cutoff_before_any_candle_closes(tmp_path: Path) -> None:
    _write_xau_15m(tmp_path)

    with pytest.raises(ValueError, match="no fully closed 15m candles"):
        load_local_timeframes(tmp_path, "2026-07-07T00:10:00Z", "XAUUSD")


def test_offline_xau_rejects_invalid_ohlc_geometry(tmp_path: Path) -> None:
    path = _write_xau_15m(tmp_path)
    frame = pd.read_csv(path)
    frame.loc[0, "high"] = frame.loc[0, "low"] - 1.0
    frame.to_csv(path, index=False)

    with pytest.raises(ValueError, match="invalid OHLC geometry"):
        load_local_timeframes(tmp_path, "2026-07-07T06:30:00Z", "XAUUSD")
