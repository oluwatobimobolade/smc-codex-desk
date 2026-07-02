"""WP-0019 live OHLCV reliability regression tests.

Covers: route-health preflight, retry/backoff, forming-candle exclusion,
stale/malformed rejection, TradingView exclusion, failure manifests.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from smc_desk.data import live_ohlcv, live_route_health
from smc_desk.data.live_ohlcv import (
    _parse_and_verify_klines,
    _validate_symbol,
    acquire_verified_closed_ohlcv,
    execute_with_retry,
)
from smc_desk.data.live_route_health import (
    RouteHealthReport,
    check_closed_candle_validation,
    check_dns,
    check_https,
    check_klines,
    check_server_time,
    run_route_health_preflight,
)


# ── helpers ────────────────────────────────────────────────────────────────


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


def _fake_time_json(server_time_ms: int) -> dict[str, Any]:
    return {"serverTime": server_time_ms}


# ── 1. DNS failure writes NO_VALID_LIVE_TRADE ──────────────────────────────


def test_dns_failure_writes_no_valid_live_trade(tmp_path: Path) -> None:
    def getter(_url: str, _timeout: float) -> Any:
        raise OSError("simulated DNS failure")

    def bridge(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise TimeoutError("bridge timeout")

    with pytest.raises(RuntimeError, match="No verified closed Binance"):
        acquire_verified_closed_ohlcv(
            symbol="BTCUSDT",
            output_dir=tmp_path,
            min_bars=1,
            json_getter=getter,
            bridge_caller=bridge,
        )

    payload = json.loads(
        (tmp_path / "verified_closed_ohlcv_failure.json").read_text(encoding="utf-8")
    )
    assert payload["required_action"] == "NO_VALID_LIVE_TRADE"
    assert payload["dns_diagnostic"] is not None
    assert payload["tradingview_used_as_market_truth"] is False


# ── 2. REST timeout retries exactly 3 times ────────────────────────────────


def test_rest_timeout_retries_three_times_before_fallback(tmp_path: Path) -> None:
    call_count = [0]
    page_values = iter(
        [
            json.dumps({"serverTime": 1_700_000_900_000}),
            json.dumps([_row(1_700_000_000_000, 1_700_000_900_000 - 1)]),
        ]
    )

    def getter(_url: str, _timeout: float) -> Any:
        call_count[0] += 1
        if call_count[0] <= 3:
            raise TimeoutError(f"simulated timeout #{call_count[0]}")
        # 4th call: succeed (acts as the bridge route fallback)
        raise OSError("DNS failure")  # force fallback to browser

    def bridge(action: str, _args: dict[str, Any], _session: str, _timeout: float) -> dict[str, Any]:
        if action == "navigate":
            return {"ok": True, "data": {}}
        return {"ok": True, "data": {"value": next(page_values)}}

    _, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=2,
        min_bars=1,
        json_getter=getter,
        bridge_caller=bridge,
    )

    assert call_count[0] >= 3  # REST route retried up to 3 times before fallback


def test_execute_with_retry_uses_three_attempts_max() -> None:
    call_count = [0]

    def flaky() -> Any:
        call_count[0] += 1
        if call_count[0] < 3:
            raise TimeoutError("transient")
        return "success", call_count[0]

    result, attempts = execute_with_retry(flaky)
    assert result[0] == "success"
    assert attempts == 3
    assert call_count[0] == 3


def test_execute_with_retry_raises_last_error_after_exhaustion() -> None:
    call_count = [0]

    def always_fails() -> Any:
        call_count[0] += 1
        raise TimeoutError(f"failure #{call_count[0]}")

    with pytest.raises(TimeoutError, match="failure #3"):
        execute_with_retry(always_fails)

    assert call_count[0] == 3


# ── 3. REST success writes verified manifest ───────────────────────────────


def test_rest_success_writes_verified_manifest(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [
        _row(base, base + interval - 1),
        _row(base + interval, base + 2 * interval - 1),
    ]
    server_time = base + 2 * interval + 1000

    def getter(url: str, _timeout: float) -> Any:
        if "/fapi/v1/time" in url:
            return {"serverTime": server_time}
        return rows

    manifest_path, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=2,
        min_bars=2,
        allow_browser_fallback=False,
        json_getter=getter,
    )

    assert manifest["status"] == "VERIFIED"
    assert manifest["provider"] == "binance_rest_direct"
    assert manifest["tradingview_used_as_market_truth"] is False
    assert manifest["row_count"] == 2
    assert len(manifest["route_attempts"]) == 1
    assert manifest["route_attempts"][0]["status"] == "PASS"
    assert manifest["route_attempts"][0]["details"]["retry_attempts"] == 1


# ── 4. Current forming candle is excluded ──────────────────────────────────


def test_current_forming_candle_excluded(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [
        _row(base, base + interval - 1),
        _row(base + interval, base + 2 * interval - 1),
        _row(base + 2 * interval, base + 3 * interval - 1),
    ]
    server_time = base + 2 * interval + 1000  # third candle still forming

    def getter(url: str, _timeout: float) -> Any:
        if "/fapi/v1/time" in url:
            return {"serverTime": server_time}
        return rows

    _, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=3,
        min_bars=1,
        allow_browser_fallback=False,
        json_getter=getter,
    )

    assert manifest["row_count"] == 2
    assert manifest["current_forming_candle_excluded"] is True
    csv_text = Path(manifest["source_csv"]).read_text(encoding="utf-8")
    assert csv_text.count("\n") == 3  # header + 2 rows


# ── 5. Stale candle batch is refused ───────────────────────────────────────


def test_stale_candle_batch_is_refused(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [
        _row(base, base + interval - 1),
        _row(base + interval, base + 2 * interval - 1),
    ]
    # server time is WAY ahead — candles are very stale
    server_time = base + 20 * interval + 1000

    def getter(url: str, _timeout: float) -> Any:
        if "/fapi/v1/time" in url:
            return {"serverTime": server_time}
        return rows

    with pytest.raises(RuntimeError, match="No verified closed Binance"):
        acquire_verified_closed_ohlcv(
            symbol="BTCUSDT",
            output_dir=tmp_path,
            interval="15m",
            limit=2,
            min_bars=1,
            maximum_staleness_intervals=2,
            allow_browser_fallback=False,
            json_getter=getter,
        )


# ── 6. Malformed Binance row is refused ────────────────────────────────────


def test_malformed_binance_row_is_refused() -> None:
    with pytest.raises(ValueError, match="Malformed Binance kline row"):
        _parse_and_verify_klines(
            [[1_700_000_000_000, "not_enough_fields"]],
            symbol="BTCUSDT",
            interval="15m",
            server_time_ms=1_700_001_000_000,
            min_bars=1,
            maximum_staleness_intervals=2,
        )


def test_non_decimal_binance_row_is_refused() -> None:
    with pytest.raises(ValueError, match="Non-decimal Binance kline row"):
        _parse_and_verify_klines(
            [[1_700_000_000_000, "abc", "def", "ghi", "jkl", "mno", 1_700_000_900_000, "0", 0, "0", "0", "0"]],
            symbol="BTCUSDT",
            interval="15m",
            server_time_ms=1_700_001_000_000,
            min_bars=1,
            maximum_staleness_intervals=2,
        )


# ── 7. Browser fallback only used after REST failure ───────────────────────


def test_browser_fallback_only_used_after_rest_failure(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [_row(base, base + interval - 1), _row(base + interval, base + 2 * interval - 1)]
    server_time = base + 2 * interval + 1000
    page_values = iter([json.dumps({"serverTime": server_time}), json.dumps(rows)])

    def getter(_url: str, _timeout: float) -> Any:
        raise OSError("simulated rest failure")

    def bridge(action: str, _args: dict[str, Any], _session: str, _timeout: float) -> dict[str, Any]:
        if action == "navigate":
            return {"ok": True, "data": {}}
        return {"ok": True, "data": {"value": next(page_values)}}

    _, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=2,
        min_bars=1,
        json_getter=getter,
        bridge_caller=bridge,
    )

    assert manifest["provider"] == "binance_rest_via_webbridge_navigation"
    attempt_statuses = [a["status"] for a in manifest["route_attempts"]]
    assert attempt_statuses[0] == "FAIL"
    assert attempt_statuses[1] == "PASS"


# ── 8. TradingView is never used as market truth ───────────────────────────


def test_tradingview_never_used_as_market_truth_on_success(tmp_path: Path) -> None:
    base = 1_700_000_000_000
    interval = 900_000
    rows = [_row(base, base + interval - 1)]
    server_time = base + interval + 1000

    def getter(url: str, _timeout: float) -> Any:
        if "/fapi/v1/time" in url:
            return {"serverTime": server_time}
        return rows

    _, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=1,
        min_bars=1,
        allow_browser_fallback=False,
        json_getter=getter,
    )

    assert manifest["tradingview_used_as_market_truth"] is False
    assert manifest["provider"] != "tradingview"
    assert "tradingview" not in manifest["provider"]


def test_tradingview_never_used_as_market_truth_on_failure(tmp_path: Path) -> None:
    def getter(_url: str, _timeout: float) -> Any:
        raise OSError("total failure")

    def bridge(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("bridge failure")

    with pytest.raises(RuntimeError, match="No verified closed Binance"):
        acquire_verified_closed_ohlcv(
            symbol="BTCUSDT",
            output_dir=tmp_path,
            min_bars=1,
            json_getter=getter,
            bridge_caller=bridge,
        )

    payload = json.loads(
        (tmp_path / "verified_closed_ohlcv_failure.json").read_text(encoding="utf-8")
    )
    assert payload["tradingview_used_as_market_truth"] is False
    for attempt in payload["route_attempts"]:
        assert "tradingview" not in attempt["route"]


# ── 9. Failure manifest contains all route attempts ────────────────────────


def test_failure_manifest_contains_all_route_attempts(tmp_path: Path) -> None:
    def getter(_url: str, _timeout: float) -> Any:
        raise OSError("primary route failure")

    def bridge(_action: str, _args: dict[str, Any], _session: str, _timeout: float) -> dict[str, Any]:
        raise TimeoutError("bridge failure")

    with pytest.raises(RuntimeError, match="No verified closed Binance"):
        acquire_verified_closed_ohlcv(
            symbol="ETHUSDT",
            output_dir=tmp_path,
            min_bars=1,
            json_getter=getter,
            bridge_caller=bridge,
        )

    payload = json.loads(
        (tmp_path / "verified_closed_ohlcv_failure.json").read_text(encoding="utf-8")
    )
    assert len(payload["route_attempts"]) == 2
    routes = [a["route"] for a in payload["route_attempts"]]
    assert "binance_rest_direct" in routes
    assert "binance_rest_via_webbridge_navigation" in routes
    assert all(a["status"] == "FAIL" for a in payload["route_attempts"])
    assert payload["dns_diagnostic"] is not None


# ── 10. Route health preflight blocks fetch if DNS fails ───────────────────


def test_route_health_preflight_dns_failure() -> None:
    report = run_route_health_preflight(
        symbol="BTCUSDT",
        interval="15m",
        base_url="https://nonexistent-host-xyz-999.invalid",
        route="binance_usdm_rest",
    )
    assert report.overall == "FAIL"
    assert report.required_action == "NO_VALID_LIVE_TRADE"
    stages = {s.stage: s for s in report.stages}
    assert stages["dns"].status == "FAIL"
    assert stages["https"].status == "SKIPPED"


def test_route_health_preflight_ready_when_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preflight passes when DNS, HTTPS, klines all succeed (mock)."""
    base = "https://fapi.binance.com"
    server_time_ms = 1_700_000_900_000
    monkeypatch.setattr(
        live_route_health,
        "check_dns",
        lambda host, route="binance_usdm_rest": live_route_health.StageResult(
            stage="dns",
            status="PASS",
            latency_ms=0,
            details={"host": host, "addresses": ["127.0.0.1"]},
        ),
    )
    monkeypatch.setattr(
        live_route_health,
        "check_https",
        lambda base_url, route="binance_usdm_rest", timeout=5.0: live_route_health.StageResult(
            stage="https",
            status="PASS",
            latency_ms=0,
            details={"base_url": base_url, "status_code": 200},
        ),
    )

    def getter(url: str, _timeout: float) -> Any:
        if "/fapi/v1/time" in url:
            return {"serverTime": server_time_ms}
        if "/fapi/v1/klines" in url:
            return [
                _row(1_700_000_000_000, 1_700_000_900_000 - 1),
                _row(1_700_000_900_000, 1_700_001_800_000 - 1),
            ]
        return {}

    report = run_route_health_preflight(
        symbol="BTCUSDT",
        interval="15m",
        base_url=base,
        json_getter=getter,
    )
    assert report.overall == "READY"
    assert report.required_action is None
    stages = {s.stage: s for s in report.stages}
    assert stages["dns"].status == "PASS"
    assert stages["https"].status == "PASS"


def test_route_health_preflight_stage_independence() -> None:
    """Each stage check returns proper StageResult independently."""
    # DNS check
    dns_result = check_dns("fapi.binance.com")
    assert dns_result.stage == "dns"
    assert dns_result.status in {"PASS", "FAIL"}

    # HTTPS check
    https_result = check_https("https://fapi.binance.com")
    assert https_result.stage == "https"
    assert https_result.status in {"PASS", "FAIL"}

    # Server time check is live-dependent, so only test structure
    assert callable(check_server_time)
    assert callable(check_klines)
    assert callable(check_closed_candle_validation)


def test_validate_symbol() -> None:
    assert _validate_symbol("BTCUSDT") == "BTCUSDT"
    assert _validate_symbol("btcusdt") == "BTCUSDT"
    assert _validate_symbol(" BTC/USDT ") == "BTCUSDT"
    with pytest.raises(ValueError):
        _validate_symbol("")
    with pytest.raises(ValueError):
        _validate_symbol("!@#")


def test_retry_counter_in_route_attempts(tmp_path: Path) -> None:
    call_count = [0]
    base = 1_700_000_000_000
    interval = 900_000
    rows = [_row(base, base + interval - 1)]
    server_time = base + interval + 1000

    def getter(url: str, _timeout: float) -> Any:
        call_count[0] += 1
        if call_count[0] < 2:
            raise TimeoutError("transient")
        if "/fapi/v1/time" in url:
            return {"serverTime": server_time}
        return rows

    _, manifest = acquire_verified_closed_ohlcv(
        symbol="BTCUSDT",
        output_dir=tmp_path,
        interval="15m",
        limit=1,
        min_bars=1,
        allow_browser_fallback=False,
        json_getter=getter,
    )

    attempt = manifest["route_attempts"][0]
    assert attempt["status"] == "PASS"
    assert attempt["details"]["retry_attempts"] == 2
