"""Live market-truth route-health preflight.

Validates the route before fetching live candles:

    DNS → TCP/TLS → Binance server time → Binance klines → candle validation

A failed preflight blocks the fetch entirely with ``ROUTE_UNAVAILABLE``.
"""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


BINANCE_FAPI_BASE = "https://fapi.binance.com"

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 20.0


# ── Health check result types ──────────────────────────────────────────────


@dataclass
class StageResult:
    stage: str
    status: str  # PASS, FAIL, SKIPPED
    latency_ms: int
    error_type: str | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteHealthReport:
    route: str
    overall: str  # READY or FAIL
    stages: list[StageResult]
    created_at: str
    required_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "overall": self.overall,
            "stages": [asdict(s) for s in self.stages],
            "created_at": self.created_at,
            "required_action": self.required_action,
        }


# ── HTTP helper ────────────────────────────────────────────────────────────


def _http_json_raw(url: str, timeout: float) -> Any:
    import json

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "smc-codex-desk/route-health/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Stage checks ───────────────────────────────────────────────────────────


def check_dns(host: str, *, route: str = "binance_usdm_rest") -> StageResult:
    started = time.monotonic()
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({r[4][0] for r in rows})
        return StageResult(
            stage="dns",
            status="PASS",
            latency_ms=int((time.monotonic() - started) * 1000),
            details={"host": host, "addresses": addresses},
        )
    except OSError as exc:
        return StageResult(
            stage="dns",
            status="FAIL",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            error=str(exc),
        )


def check_https(
    base_url: str,
    *,
    route: str = "binance_usdm_rest",
    timeout: float = CONNECT_TIMEOUT,
) -> StageResult:
    started = time.monotonic()
    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/fapi/v1/ping",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return StageResult(
                stage="https",
                status="PASS" if resp.status == 200 else "FAIL",
                latency_ms=int((time.monotonic() - started) * 1000),
                details={"base_url": base_url, "status_code": resp.status},
            )
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return StageResult(
            stage="https",
            status="FAIL",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            error=str(exc),
        )


def check_server_time(
    base_url: str,
    *,
    route: str = "binance_usdm_rest",
    timeout: float = READ_TIMEOUT,
    json_getter: Callable[[str, float], Any] | None = None,
) -> StageResult:
    started = time.monotonic()
    getter = json_getter or _http_json_raw
    try:
        url = f"{base_url.rstrip('/')}/fapi/v1/time"
        payload = getter(url, timeout)
        if not isinstance(payload, dict) or "serverTime" not in payload:
            raise ValueError(f"Invalid server-time response: {payload!r}")
        return StageResult(
            stage="server_time",
            status="PASS",
            latency_ms=int((time.monotonic() - started) * 1000),
            details={"server_time_ms": payload["serverTime"]},
        )
    except Exception as exc:
        return StageResult(
            stage="server_time",
            status="FAIL",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            error=str(exc),
        )


def check_klines(
    base_url: str,
    symbol: str,
    interval: str,
    *,
    limit: int = 10,
    route: str = "binance_usdm_rest",
    timeout: float = READ_TIMEOUT,
    json_getter: Callable[[str, float], Any] | None = None,
) -> StageResult:
    started = time.monotonic()
    getter = json_getter or _http_json_raw
    try:
        from urllib.parse import urlencode

        query = urlencode({
            "symbol": symbol,
            "interval": interval,
            "limit": min(max(limit, 1), 1500),
        })
        url = f"{base_url.rstrip('/')}/fapi/v1/klines?{query}"
        rows = getter(url, timeout)
        if not isinstance(rows, list) or len(rows) < 1:
            raise ValueError(f"Empty or invalid klines response: {rows!r}")
        return StageResult(
            stage="klines",
            status="PASS",
            latency_ms=int((time.monotonic() - started) * 1000),
            details={"row_count": len(rows)},
        )
    except Exception as exc:
        return StageResult(
            stage="klines",
            status="FAIL",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            error=str(exc),
        )


def check_closed_candle_validation(
    symbol: str,
    interval: str,
    raw_rows: list[list],
    server_time_ms: int,
    *,
    route: str = "binance_usdm_rest",
    min_bars: int = 1,
) -> StageResult:
    """Validate a batch of Binance kline rows for closed-candle correctness."""
    started = time.monotonic()
    # Import here to avoid top-level circular dependency with live_ohlcv
    from smc_desk.data.live_ohlcv import _parse_and_verify_klines

    try:
        parsed, verification = _parse_and_verify_klines(
            raw_rows,
            symbol=symbol,
            interval=interval,
            server_time_ms=server_time_ms,
            min_bars=min_bars,
            maximum_staleness_intervals=6,
        )
        return StageResult(
            stage="closed_candle_validation",
            status="PASS",
            latency_ms=int((time.monotonic() - started) * 1000),
            details={
                "closed_count": len(parsed),
                "staleness_ms": verification.get("staleness_ms", 0),
                "current_forming_excluded": verification.get(
                    "current_forming_candle_excluded", False
                ),
            },
        )
    except Exception as exc:
        return StageResult(
            stage="closed_candle_validation",
            status="FAIL",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            error=str(exc),
        )


# ── Complete route-health preflight ────────────────────────────────────────


def _skipped_stage(stage: str, reason: str) -> StageResult:
    return StageResult(
        stage=stage,
        status="SKIPPED",
        latency_ms=0,
        details={"reason": reason},
    )


def run_route_health_preflight(
    symbol: str,
    interval: str = "15m",
    *,
    base_url: str = BINANCE_FAPI_BASE,
    route: str = "binance_usdm_rest",
    timeout: float = READ_TIMEOUT,
    json_getter: Callable[[str, float], Any] | None = None,
) -> RouteHealthReport:
    """Run all route-health stages in order.  DNS failure stops everything."""

    symbol_stripped = symbol.strip().upper().replace("/", "").replace("-", "")
    host = base_url.split("//", 1)[-1].split("/", 1)[0]
    stages: list[StageResult] = []

    # Stage 1: DNS
    stage_dns = check_dns(host, route=route)
    stages.append(stage_dns)
    if stage_dns.status != "PASS":
        stages.extend([_skipped_stage("https", "dns_failed"), _skipped_stage("server_time", "dns_failed"),
                       _skipped_stage("klines", "dns_failed"), _skipped_stage("closed_candle_validation", "dns_failed")])
        return RouteHealthReport(
            route=route,
            overall="FAIL",
            stages=stages,
            created_at=datetime.now(timezone.utc).isoformat(),
            required_action="NO_VALID_LIVE_TRADE",
        )

    # Stage 2: HTTPS
    stage_https = check_https(base_url, route=route)
    stages.append(stage_https)
    if stage_https.status != "PASS":
        stages.extend([_skipped_stage("server_time", "https_failed"),
                       _skipped_stage("klines", "https_failed"),
                       _skipped_stage("closed_candle_validation", "https_failed")])
        return RouteHealthReport(
            route=route,
            overall="FAIL",
            stages=stages,
            created_at=datetime.now(timezone.utc).isoformat(),
            required_action="NO_VALID_LIVE_TRADE",
        )

    # Stage 3: Server time
    stage_time = check_server_time(base_url, route=route, timeout=timeout, json_getter=json_getter)
    stages.append(stage_time)
    if stage_time.status != "PASS":
        stages.extend([_skipped_stage("klines", "server_time_failed"),
                       _skipped_stage("closed_candle_validation", "server_time_failed")])
        return RouteHealthReport(
            route=route,
            overall="FAIL",
            stages=stages,
            created_at=datetime.now(timezone.utc).isoformat(),
            required_action="NO_VALID_LIVE_TRADE",
        )

    # Stage 4: Klines
    stage_klines = check_klines(
        base_url, symbol_stripped, interval, limit=10, route=route, timeout=timeout, json_getter=json_getter
    )
    stages.append(stage_klines)
    if stage_klines.status != "PASS":
        stages.append(_skipped_stage("closed_candle_validation", "klines_failed"))
        return RouteHealthReport(
            route=route,
            overall="FAIL",
            stages=stages,
            created_at=datetime.now(timezone.utc).isoformat(),
            required_action="NO_VALID_LIVE_TRADE",
        )

    # Stage 5: Closed candle validation
    server_time_ms = int(stage_time.details["server_time_ms"])
    # For preflight we re-fetch klines with a larger limit to have actual rows
    try:
        from urllib.parse import urlencode

        getter = json_getter or _http_json_raw
        query = urlencode({"symbol": symbol_stripped, "interval": interval, "limit": min(500, 100)})
        klines_url = f"{base_url.rstrip('/')}/fapi/v1/klines?{query}"
        raw_rows = getter(klines_url, timeout)
        stage_validation = check_closed_candle_validation(
            symbol_stripped, interval, raw_rows, server_time_ms, route=route, min_bars=1
        )
    except Exception as exc:
        stage_validation = StageResult(
            stage="closed_candle_validation",
            status="FAIL",
            latency_ms=0,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    stages.append(stage_validation)

    all_ok = all(s.status == "PASS" for s in stages)
    return RouteHealthReport(
        route=route,
        overall="READY" if all_ok else "FAIL",
        stages=stages,
        created_at=datetime.now(timezone.utc).isoformat(),
        required_action=None if all_ok else "NO_VALID_LIVE_TRADE",
    )
