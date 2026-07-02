from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from PIL import Image

import smc_desk.colleague.wp0020_gauntlet as gauntlet
from smc_desk.models import AnalysisResult, StructureEvent, TradePlan, Zone
from smc_desk.rules import RuleConfig


def _write_png(path: str | Path, size: tuple[int, int] = (800, 420)) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(16, 18, 24)).save(path)


def _df(bars: int = 80) -> pd.DataFrame:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(bars):
        price = 1000 + index * 2
        rows.append(
            {
                "timestamp": (start + timedelta(minutes=15 * index)).isoformat(),
                "open": price,
                "high": price + 6,
                "low": price - 4,
                "close": price + 1,
                "volume": 100,
            }
        )
    return pd.DataFrame(rows)


def _analysis(symbol: str, timeframe: str) -> AnalysisResult:
    return AnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        input_type="ohlcv",
        generated_at="2026-06-27T00:00:00+00:00",
        metrics={},
        session_context={},
        events=[
            StructureEvent(
                label="BOS",
                direction="bullish",
                index=10,
                timestamp="2026-06-01T02:30:00+00:00",
                price=1021.0,
                reason="unit test structure break",
            ),
            StructureEvent(
                label="Liquidity Sweep",
                direction="bearish",
                index=12,
                timestamp="2026-06-01T03:00:00+00:00",
                price=1030.0,
                reason="unit test sweep",
            ),
        ],
        zones=[
            Zone(
                label="Bullish FVG",
                kind="fvg",
                direction="bullish",
                low=1015.0,
                high=1024.0,
                start_index=8,
                end_index=9,
                status="fresh",
                reason="unit test fvg zone",
            )
        ],
        trade_plan=TradePlan(direction="neutral", verdict="Pass", thesis="annotation provenance test"),
    )


def test_smc_annotations_have_event_ids_candle_timestamps_and_prices(monkeypatch, tmp_path):
    monkeypatch.setattr(
        gauntlet,
        "run_legacy_annotation_analysis",
        lambda df, symbol, timeframe, config, notes, **_kwargs: (_analysis(symbol, timeframe), df),
    )
    monkeypatch.setattr(
        gauntlet,
        "render_smc_annotated",
        lambda _df, _analysis, output_path, min_conf="medium", title=None: _write_png(output_path),
    )
    monkeypatch.setattr(
        gauntlet,
        "render_mtf_mosaic",
        lambda _dfs, _analyses, output_path, title="": _write_png(output_path, (900, 620)),
    )

    timeframe_dfs = {tf: _df() for tf in gauntlet.TIMEFRAMES}
    manifest, analyses = gauntlet.render_smc_annotations(
        timeframe_dfs=timeframe_dfs,
        symbol="BTCUSDT",
        output_dir=tmp_path / "annotated",
        config=RuleConfig(),
    )

    assert manifest["status"] == "PASS"
    assert manifest["annotation_count"] == 12
    assert set(analyses) == {"15m", "1h", "4h", "1d"}
    assert not Path(manifest["mosaic"]["path"]).is_absolute()
    assert (tmp_path / manifest["mosaic"]["path"]).exists()

    for timeframe, info in manifest["charts"].items():
        assert not Path(info["path"]).is_absolute()
        assert (tmp_path / info["path"]).exists()
        assert info["exists_at_write"] is True
        assert info["timeframe"] == timeframe
        assert info["width"] == 800

    for annotation in manifest["annotations"]:
        assert annotation["event_id"]
        assert annotation["timeframe"] in gauntlet.TIMEFRAMES
        assert isinstance(annotation["candle_index"], int)
        assert annotation["timestamp"]
        has_point_price = annotation.get("price") is not None
        has_zone_price = annotation.get("price_low") is not None and annotation.get("price_high") is not None
        assert has_point_price or has_zone_price

    zone_events = [item for item in manifest["annotations"] if item["source"] == "engine_analysis_zone"]
    assert zone_events
    assert {item["lifecycle_status"] for item in zone_events} == {"fresh"}
