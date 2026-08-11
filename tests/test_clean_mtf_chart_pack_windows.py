from __future__ import annotations

import pandas as pd

from smc_desk.rendering.clean_mtf_chart_pack import (
    DISPLAY_WINDOW_BARS,
    render_clean_mtf_chart_pack,
)


def _df(rows: int, frequency: str) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=rows, freq=frequency, tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [1000] * rows,
        }
    )


def test_clean_chart_pack_bounds_each_visual_window(tmp_path) -> None:
    frames = {
        "1d": _df(220, "1D"),
        "4h": _df(260, "4h"),
        "1h": _df(400, "1h"),
        "15m": _df(500, "15min"),
    }

    manifest = render_clean_mtf_chart_pack(frames, tmp_path, symbol="EURJPY")

    assert manifest["source_rows"] == {timeframe: len(df) for timeframe, df in frames.items()}
    assert manifest["displayed_rows"] == {
        timeframe: DISPLAY_WINDOW_BARS[timeframe] for timeframe in frames
    }
    assert all((tmp_path / f"EURJPY_{timeframe}_clean.png").exists() for timeframe in frames)
