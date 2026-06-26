from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from smc_desk.data.live_ohlcv import acquire_verified_closed_ohlcv


def _row(open_ms: int, close_ms: int, close: str = "101") -> list[Any]:
    return [
        open_ms,
        "100",
        "102",
        "99",
        close,
        "10",
        close_ms,
        "1000",
        25,
        "5",
        "500",
        "0",
    ]


def test_direct_rest_excludes_current_forming_candle(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [
        _row(base, base + interval - 1),
        _row(base + interval, base + 2 * interval - 1),
        _row(base + 2 * interval, base + 3 * interval - 1),
    ]
    server_time = base + 2 * interval + 1000  # third candle is still forming

    def getter(url: str, _timeout: float) -> Any:
        if url.endswith("/fapi/v1/time"):
            return {"serverTime": server_time}
        return rows

    manifest_path, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=3,
        min_bars=2,
        allow_browser_fallback=False,
        json_getter=getter,
    )

    assert manifest["status"] == "VERIFIED"
    assert manifest["row_count"] == 2
    assert manifest["current_forming_candle_excluded"] is True
    csv_text = Path(manifest["source_csv"]).read_text(encoding="utf-8")
    assert csv_text.count("\n") == 3  # header plus two rows
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["provider"] == "binance_rest_direct"


def test_direct_failure_uses_browser_navigation_fallback(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [_row(base, base + interval - 1), _row(base + interval, base + 2 * interval - 1)]
    server_time = base + 2 * interval + 1000
    page_values = iter([json.dumps({"serverTime": server_time}), json.dumps(rows)])

    def getter(_url: str, _timeout: float) -> Any:
        raise OSError("simulated DNS failure")

    def bridge(action: str, _args: dict[str, Any], _session: str, _timeout: float) -> dict[str, Any]:
        if action == "navigate":
            return {"ok": True, "data": {}}
        return {"ok": True, "data": {"value": next(page_values)}}

    _, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=2,
        min_bars=2,
        json_getter=getter,
        bridge_caller=bridge,
    )

    assert manifest["provider"] == "binance_rest_via_webbridge_navigation"
    assert [attempt["status"] for attempt in manifest["route_attempts"]] == ["FAIL", "PASS"]


def test_all_routes_fail_writes_failure_manifest(tmp_path: Path) -> None:
    def getter(_url: str, _timeout: float) -> Any:
        raise OSError("DNS failure")

    def bridge(_action: str, _args: dict[str, Any], _session: str, _timeout: float) -> dict[str, Any]:
        raise TimeoutError("bridge timeout")

    with pytest.raises(RuntimeError, match="No verified closed Binance"):
        acquire_verified_closed_ohlcv(
            symbol="BTCUSDT",
            output_dir=tmp_path,
            min_bars=1,
            json_getter=getter,
            bridge_caller=bridge,
        )

    payload = json.loads((tmp_path / "verified_closed_ohlcv_failure.json").read_text(encoding="utf-8"))
    assert payload["required_action"] == "NO_VALID_LIVE_TRADE"
    assert len(payload["route_attempts"]) == 2
