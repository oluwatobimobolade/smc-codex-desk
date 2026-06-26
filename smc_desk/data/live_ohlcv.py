from __future__ import annotations

"""Verified live OHLCV acquisition for the Market Colleague.

The canonical live source is Binance USD-M Futures. TradingView/Kimi remains
external visual evidence and must not be used as the primary market-truth feed.

A candle is accepted as confirmed only when Binance's own kline close time is
strictly earlier than or equal to Binance server time. The currently forming
candle is always excluded.
"""

import csv
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode


BINANCE_FAPI_BASE = "https://fapi.binance.com"
WEBBRIDGE_URL = "http://127.0.0.1:10086/command"
INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


@dataclass
class RouteAttempt:
    route: str
    status: str
    started_at: str
    finished_at: str
    latency_ms: int
    error_type: str | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifiedClosedBatch:
    symbol: str
    interval: str
    venue: str
    market_type: str
    provider: str
    verification_method: str
    fetched_at: str
    server_time: str
    server_time_ms: int
    last_closed_candle_open: str
    last_closed_candle_close: str
    row_count: int
    staleness_ms: int
    source_csv: str
    source_manifest: str
    route_attempts: list[dict[str, Any]]


JsonGetter = Callable[[str, float], Any]
WebBridgeCaller = Callable[[str, dict[str, Any], str, float], dict[str, Any]]


def _utc_iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_json(url: str, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "smc-codex-desk/verified-live-ohlcv/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _webbridge_call(
    action: str,
    args: dict[str, Any],
    session: str,
    timeout: float = 45.0,
) -> dict[str, Any]:
    payload = json.dumps({"action": action, "args": args, "session": session}).encode("utf-8")
    request = urllib.request.Request(
        WEBBRIDGE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _bridge_value(response: dict[str, Any], action: str) -> Any:
    if response.get("ok") is False:
        raise RuntimeError(f"Kimi WebBridge {action} failed: {response}")
    try:
        return response["data"]["value"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Kimi WebBridge {action} returned no value: {response}") from exc


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper().replace("/", "").replace("-", "")
    if not normalized or not normalized.isalnum():
        raise ValueError(f"Invalid Binance symbol: {symbol!r}")
    return normalized


def _dns_diagnostic(host: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({row[4][0] for row in rows})
        return {
            "status": "PASS",
            "host": host,
            "addresses": addresses,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except OSError as exc:
        return {
            "status": "FAIL",
            "host": host,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


def _parse_and_verify_klines(
    raw_rows: Any,
    *,
    symbol: str,
    interval: str,
    server_time_ms: int,
    min_bars: int,
    maximum_staleness_intervals: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")
    if not isinstance(raw_rows, list):
        raise ValueError(f"Unexpected Binance kline response: {raw_rows!r}")

    interval_ms = INTERVAL_MS[interval]
    parsed: list[dict[str, Any]] = []
    previous_open: int | None = None
    seen: set[int] = set()

    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < 11:
            raise ValueError(f"Malformed Binance kline row: {raw!r}")
        open_ms = int(raw[0])
        close_ms = int(raw[6])
        if open_ms in seen:
            raise ValueError(f"Duplicate Binance kline open time: {open_ms}")
        seen.add(open_ms)
        if previous_open is not None and open_ms <= previous_open:
            raise ValueError("Binance kline timestamps are not strictly increasing")
        previous_open = open_ms

        try:
            open_px = Decimal(str(raw[1]))
            high_px = Decimal(str(raw[2]))
            low_px = Decimal(str(raw[3]))
            close_px = Decimal(str(raw[4]))
            volume = Decimal(str(raw[5]))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Non-decimal Binance kline row: {raw!r}") from exc

        if min(open_px, high_px, low_px, close_px) <= 0 or volume < 0:
            raise ValueError(f"Invalid Binance kline values: {raw!r}")
        if high_px < max(open_px, close_px, low_px) or low_px > min(open_px, close_px, high_px):
            raise ValueError(f"Binance kline violates OHLC range consistency: {raw!r}")

        # REST includes the currently forming kline. It is verified closed only
        # after Binance server time has passed the exchange-reported close time.
        if close_ms > server_time_ms:
            continue

        parsed.append(
            {
                "timestamp": _utc_iso_from_ms(open_ms),
                "open": str(open_px),
                "high": str(high_px),
                "low": str(low_px),
                "close": str(close_px),
                "volume": str(volume),
                "close_time": _utc_iso_from_ms(close_ms),
                "trade_count": int(raw[8]),
                "quote_volume": str(raw[7]),
                "taker_buy_base_volume": str(raw[9]),
                "taker_buy_quote_volume": str(raw[10]),
                "source": "binance_usdm_rest",
                "is_final": True,
                "is_complete": True,
            }
        )

    if len(parsed) < min_bars:
        raise ValueError(f"Only {len(parsed)} verified closed candles returned; minimum required is {min_bars}")

    # Verify the closed sequence has no missing interval inside the accepted batch.
    opens = [int(datetime.fromisoformat(row["timestamp"]).timestamp() * 1000) for row in parsed]
    gaps: list[dict[str, int]] = []
    for left, right in zip(opens, opens[1:]):
        if right - left != interval_ms:
            gaps.append({"left_open_ms": left, "right_open_ms": right, "observed_step_ms": right - left})
    if gaps:
        raise ValueError(f"Verified Binance candle batch contains interval gaps: {gaps[:5]}")

    last_close_ms = int(datetime.fromisoformat(parsed[-1]["close_time"]).timestamp() * 1000)
    staleness_ms = max(0, server_time_ms - last_close_ms)
    maximum_staleness_ms = interval_ms * maximum_staleness_intervals
    if staleness_ms > maximum_staleness_ms:
        raise ValueError(
            f"Latest verified closed {interval} candle is stale by {staleness_ms}ms; "
            f"maximum allowed is {maximum_staleness_ms}ms"
        )

    return parsed, {
        "last_close_ms": last_close_ms,
        "staleness_ms": staleness_ms,
        "interval_ms": interval_ms,
        "current_forming_candle_excluded": len(parsed) < len(raw_rows),
    }


def _rest_urls(base_url: str, symbol: str, interval: str, limit: int) -> tuple[str, str]:
    base = base_url.rstrip("/")
    time_url = f"{base}/fapi/v1/time"
    query = urlencode({"symbol": symbol, "interval": interval, "limit": min(max(limit, 1), 1500)})
    klines_url = f"{base}/fapi/v1/klines?{query}"
    return time_url, klines_url


def _fetch_direct_rest(
    *,
    symbol: str,
    interval: str,
    limit: int,
    timeout: float,
    base_url: str,
    json_getter: JsonGetter,
) -> tuple[Any, int, dict[str, Any]]:
    time_url, klines_url = _rest_urls(base_url, symbol, interval, limit)
    server_payload = json_getter(time_url, timeout)
    if not isinstance(server_payload, dict) or "serverTime" not in server_payload:
        raise RuntimeError(f"Binance server-time response is invalid: {server_payload!r}")
    server_time_ms = int(server_payload["serverTime"])
    rows = json_getter(klines_url, timeout)
    return rows, server_time_ms, {"time_url": time_url, "klines_url": klines_url}


def _fetch_browser_rest(
    *,
    symbol: str,
    interval: str,
    limit: int,
    timeout: float,
    base_url: str,
    session: str,
    bridge_caller: WebBridgeCaller,
) -> tuple[Any, int, dict[str, Any]]:
    """Use direct browser navigation, not cross-origin fetch from TradingView.

    Navigating the tab directly to Binance avoids the CORS failure that occurs
    when ``fetch()`` is executed from a TradingView page.
    """

    time_url, klines_url = _rest_urls(base_url, symbol, interval, limit)

    bridge_caller("navigate", {"url": time_url, "newTab": True}, session, timeout)
    time_response = bridge_caller(
        "evaluate",
        {"code": "document.body ? document.body.innerText : ''"},
        session,
        timeout,
    )
    server_payload = json.loads(str(_bridge_value(time_response, "evaluate server time")))
    if not isinstance(server_payload, dict) or "serverTime" not in server_payload:
        raise RuntimeError(f"Browser Binance server-time response is invalid: {server_payload!r}")

    bridge_caller("navigate", {"url": klines_url, "newTab": False}, session, timeout)
    kline_response = bridge_caller(
        "evaluate",
        {"code": "document.body ? document.body.innerText : ''"},
        session,
        timeout,
    )
    rows = json.loads(str(_bridge_value(kline_response, "evaluate klines")))
    return rows, int(server_payload["serverTime"]), {"time_url": time_url, "klines_url": klines_url}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "trade_count",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "source",
        "is_final",
        "is_complete",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def acquire_verified_closed_ohlcv(
    *,
    symbol: str,
    output_dir: Path,
    interval: str = "15m",
    limit: int = 500,
    min_bars: int = 100,
    timeout: float = 20.0,
    base_url: str = BINANCE_FAPI_BASE,
    webbridge_session: str = "smc-binance-market-truth",
    allow_browser_fallback: bool = True,
    maximum_staleness_intervals: int = 2,
    json_getter: JsonGetter = _http_json,
    bridge_caller: WebBridgeCaller = _webbridge_call,
) -> tuple[Path, dict[str, Any]]:
    """Acquire a verified batch of closed Binance USD-M candles.

    Route order:
      1. Direct Binance REST from Python.
      2. Direct browser navigation to the same Binance REST endpoints.

    TradingView is deliberately excluded from the market-truth route.
    """

    symbol = _validate_symbol(symbol)
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[RouteAttempt] = []
    dns = _dns_diagnostic(base_url.split("//", 1)[-1].split("/", 1)[0])
    routes: list[tuple[str, Callable[[], tuple[Any, int, dict[str, Any]]]]] = [
        (
            "binance_rest_direct",
            lambda: _fetch_direct_rest(
                symbol=symbol,
                interval=interval,
                limit=limit,
                timeout=timeout,
                base_url=base_url,
                json_getter=json_getter,
            ),
        )
    ]
    if allow_browser_fallback:
        routes.append(
            (
                "binance_rest_via_webbridge_navigation",
                lambda: _fetch_browser_rest(
                    symbol=symbol,
                    interval=interval,
                    limit=limit,
                    timeout=max(timeout, 30.0),
                    base_url=base_url,
                    session=webbridge_session,
                    bridge_caller=bridge_caller,
                ),
            )
        )

    final_error: Exception | None = None
    for route_name, route in routes:
        started_dt = datetime.now(timezone.utc)
        started = time.monotonic()
        try:
            raw_rows, server_time_ms, route_details = route()
            rows, verification = _parse_and_verify_klines(
                raw_rows,
                symbol=symbol,
                interval=interval,
                server_time_ms=server_time_ms,
                min_bars=min_bars,
                maximum_staleness_intervals=maximum_staleness_intervals,
            )
            finished_dt = datetime.now(timezone.utc)
            attempts.append(
                RouteAttempt(
                    route=route_name,
                    status="PASS",
                    started_at=started_dt.isoformat(),
                    finished_at=finished_dt.isoformat(),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    details={**route_details, **verification, "dns": dns},
                )
            )

            csv_path = output_dir / f"{symbol}_{interval}_verified_closed.csv"
            _write_csv(csv_path, rows)
            fetched_at = finished_dt.isoformat()
            manifest_path = output_dir / "verified_closed_ohlcv_manifest.json"
            manifest = {
                "status": "VERIFIED",
                "authority": "canonical_market_truth",
                "venue": "BINANCE",
                "market_type": "USD-M perpetual futures",
                "symbol": symbol,
                "interval": interval,
                "provider": route_name,
                "verification_method": "binance_server_time_and_exchange_close_time",
                "fetched_at": fetched_at,
                "server_time": _utc_iso_from_ms(server_time_ms),
                "server_time_ms": server_time_ms,
                "last_closed_candle_open": rows[-1]["timestamp"],
                "last_closed_candle_close": rows[-1]["close_time"],
                "row_count": len(rows),
                "staleness_ms": verification["staleness_ms"],
                "current_forming_candle_excluded": verification["current_forming_candle_excluded"],
                "source_csv": str(csv_path.resolve()),
                "route_attempts": [asdict(item) for item in attempts],
                "dns_diagnostic": dns,
                "tradingview_used_as_market_truth": False,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            manifest["source_manifest"] = str(manifest_path.resolve())
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return manifest_path, manifest
        except Exception as exc:  # route isolation is intentional
            final_error = exc
            finished_dt = datetime.now(timezone.utc)
            attempts.append(
                RouteAttempt(
                    route=route_name,
                    status="FAIL",
                    started_at=started_dt.isoformat(),
                    finished_at=finished_dt.isoformat(),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    error_type=type(exc).__name__,
                    error=str(exc),
                    details={"dns": dns},
                )
            )

    failure_manifest = {
        "status": "FAILED",
        "authority": "no_market_truth_available",
        "venue": "BINANCE",
        "market_type": "USD-M perpetual futures",
        "symbol": symbol,
        "interval": interval,
        "created_at": _now_iso(),
        "route_attempts": [asdict(item) for item in attempts],
        "dns_diagnostic": dns,
        "tradingview_used_as_market_truth": False,
        "required_action": "NO_VALID_LIVE_TRADE",
    }
    failure_path = output_dir / "verified_closed_ohlcv_failure.json"
    failure_path.write_text(json.dumps(failure_manifest, indent=2), encoding="utf-8")
    raise RuntimeError(
        f"No verified closed Binance {interval} candles were acquired for {symbol}. "
        f"See {failure_path}. Last error: {final_error}"
    ) from final_error
