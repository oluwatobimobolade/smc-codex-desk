from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from PIL import Image

import smc_desk.colleague.wp0020_gauntlet as gauntlet
from smc_desk.case_library import file_sha256


def _write_png(path: str | Path, size: tuple[int, int]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(12, 16, 22)).save(path)


def _timeframe_df(bars: int, step: timedelta, start: datetime) -> pd.DataFrame:
    rows = []
    for index in range(bars):
        price = 10_000 + index * 3
        rows.append(
            {
                "timestamp": (start + index * step).isoformat(),
                "open": price,
                "high": price + 10,
                "low": price - 10,
                "close": price + 2,
                "volume": 100 + index,
            }
        )
    return pd.DataFrame(rows)


def _timeframes() -> dict[str, pd.DataFrame]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return {
        "15m": _timeframe_df(220, timedelta(minutes=15), start),
        "1h": _timeframe_df(220, timedelta(hours=1), start),
        "4h": _timeframe_df(220, timedelta(hours=4), start),
        "1d": _timeframe_df(220, timedelta(days=1), start),
    }


def test_clean_chart_rendering_manifest_is_deterministic_and_uses_verified_source(monkeypatch, tmp_path):
    monkeypatch.setattr(
        gauntlet,
        "render_raw_chart",
        lambda _df, symbol, timeframe, output_path: _write_png(output_path, (640, 360)),
    )
    monkeypatch.setattr(
        gauntlet,
        "render_mtf_mosaic",
        lambda _dfs, _analyses, output_path, title="": _write_png(output_path, (900, 620)),
    )
    source_manifest = {
        "status": "PASS",
        "verified_source_status": "VERIFIED_CSV_SOURCE",
        "source_15m": "verified/BTCUSDT_15m.csv",
    }

    first = gauntlet.render_clean_mtf_charts(
        timeframe_dfs=_timeframes(),
        symbol="BTCUSDT",
        output_dir=tmp_path / "charts",
        source_manifest=source_manifest,
    )
    first_hash = file_sha256(tmp_path / "charts" / "chart_render_manifest.json")
    second = gauntlet.render_clean_mtf_charts(
        timeframe_dfs=_timeframes(),
        symbol="BTCUSDT",
        output_dir=tmp_path / "charts",
        source_manifest=source_manifest,
    )
    second_hash = file_sha256(tmp_path / "charts" / "chart_render_manifest.json")

    assert first_hash == second_hash
    assert first["source_manifest_sha256"] == second["source_manifest_sha256"]
    assert first["tradingview_used_as_market_truth"] is False
    assert set(first["charts"]) == {"15m", "1h", "4h", "1d"}
    for timeframe, info in first["charts"].items():
        assert not Path(info["path"]).is_absolute()
        assert (tmp_path / info["path"]).exists()
        assert info["exists_at_write"] is True
        assert info["width"] == 640
        assert info["height"] == 360
        assert info["timeframe"] == timeframe
        assert info["candle_count"] == 180

    persisted = json.loads((tmp_path / "charts" / "chart_render_manifest.json").read_text(encoding="utf-8"))
    assert persisted["chart_type"] == "clean_engine_charts"
    assert persisted["mosaic"]["width"] == 900
