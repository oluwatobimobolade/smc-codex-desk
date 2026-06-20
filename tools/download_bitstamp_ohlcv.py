#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import http.client
import json
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


BITSTAMP_OHLC_URL = "https://www.bitstamp.net/api/v2/ohlc/{market}/"
BITSTAMP_OHLC_URLS = (
    "https://www.bitstamp.net/api/v2/ohlc/{market}/",
    "https://bitstamp.net/api/v2/ohlc/{market}/",
)
BITSTAMP_PINNED_RESOLVES = (
    ("www.bitstamp.net", "107.154.132.13"),
)
STEP_LABELS = {
    60: "1m",
    180: "3m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    7200: "2h",
    14400: "4h",
    21600: "6h",
    43200: "12h",
    86400: "1d",
    259200: "3d",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download public Bitstamp OHLCV candles to CSV.")
    parser.add_argument("--market", default="btcusd", help="Bitstamp market symbol, for example btcusd.")
    parser.add_argument("--step", type=int, default=900, choices=sorted(STEP_LABELS), help="Candle size in seconds.")
    parser.add_argument("--start", required=True, help="UTC start date/time: YYYY-MM-DD or ISO timestamp.")
    parser.add_argument("--end", required=True, help="UTC end date/time: YYYY-MM-DD or ISO timestamp.")
    parser.add_argument("--output", help="Output CSV path. Defaults to data/ohlcv/bitstamp/<SYMBOL>/...")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between paginated requests.")
    parser.add_argument("--retries", type=int, default=6, help="Retry attempts per page when DNS or the endpoint is flaky.")
    parser.add_argument("--retry-delay", type=float, default=1.5, help="Initial retry delay in seconds.")
    return parser.parse_args()


def parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if len(normalized) == 10:
        normalized = f"{normalized}T00:00:00+00:00"
    elif normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def default_output_path(market: str, step: int, start: datetime, end: datetime) -> Path:
    symbol = market.upper()
    timeframe = STEP_LABELS[step]
    start_label = start.strftime("%Y%m%d")
    end_label = end.strftime("%Y%m%d")
    return Path("data") / "ohlcv" / "bitstamp" / symbol / f"{symbol}_{timeframe}_{start_label}_{end_label}.csv"


def _ohlc_url(template: str, market: str, params: dict[str, str | int]) -> str:
    return f"{template.format(market=market)}?{urlencode(params)}"


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, ip_address: str, tls_host: str, timeout: float = 30.0) -> None:
        super().__init__(ip_address, timeout=timeout, context=ssl.create_default_context())
        self._tls_host = tls_host

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._tls_host)


def _fetch_pinned_json(url: str, tls_host: str, ip_address: str) -> dict:
    parsed = urlparse(url)
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"
    connection = _PinnedHTTPSConnection(ip_address=ip_address, tls_host=tls_host, timeout=30)
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": tls_host,
                "User-Agent": "smc-codex-desk/1.0",
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(body)
    finally:
        connection.close()


def fetch_ohlc_page(
    market: str,
    step: int,
    start_ts: int,
    end_ts: int,
    limit: int = 1000,
    retries: int = 6,
    retry_delay: float = 1.5,
) -> dict:
    params = {
        "step": step,
        "limit": limit,
        "start": start_ts,
        "end": end_ts,
        "exclude_current_candle": "true",
    }
    errors: list[str] = []
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        for template in BITSTAMP_OHLC_URLS:
            url = _ohlc_url(template, market, params)
            request = Request(url, headers={"User-Agent": "smc-codex-desk/1.0"})
            try:
                with urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if 500 <= exc.code < 600:
                    errors.append(f"{template}: HTTP {exc.code}")
                    continue
                raise RuntimeError(f"Bitstamp returned HTTP {exc.code} for {market} OHLC request.") from exc
            except URLError as exc:
                errors.append(f"{template}: {exc.reason}")
        for tls_host, ip_address in BITSTAMP_PINNED_RESOLVES:
            url = _ohlc_url(f"https://{tls_host}/api/v2/ohlc/{{market}}/", market, params)
            try:
                return _fetch_pinned_json(url, tls_host=tls_host, ip_address=ip_address)
            except (OSError, RuntimeError, json.JSONDecodeError, http.client.HTTPException) as exc:
                errors.append(f"{tls_host}@{ip_address}: {exc}")
        if attempt < attempts - 1:
            delay = retry_delay * min(2 ** attempt, 8)
            time.sleep(delay)
    detail = "; ".join(errors[-6:]) if errors else "unknown error"
    raise RuntimeError(f"Could not reach Bitstamp OHLC endpoint after {attempts} attempts: {detail}")


def parse_ohlc_rows(payload: dict) -> list[dict[str, str | float]]:
    rows: list[dict[str, str | float]] = []
    for item in payload.get("data", {}).get("ohlc", []):
        timestamp = datetime.fromtimestamp(int(item["timestamp"]), tz=timezone.utc)
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0.0)),
            }
        )
    return rows


def download_ohlcv(
    market: str,
    step: int,
    start: datetime,
    end: datetime,
    sleep_seconds: float = 0.2,
    retries: int = 6,
    retry_delay: float = 1.5,
) -> list[dict[str, str | float]]:
    if end <= start:
        raise ValueError("--end must be later than --start")

    start_ts = int(start.timestamp())
    final_ts = int(end.timestamp())
    current_ts = start_ts
    rows_by_timestamp: dict[str, dict[str, str | float]] = {}
    page_seconds = step * 999

    while current_ts <= final_ts:
        page_end = min(current_ts + page_seconds, final_ts)
        payload = fetch_ohlc_page(
            market=market,
            step=step,
            start_ts=current_ts,
            end_ts=page_end,
            retries=retries,
            retry_delay=retry_delay,
        )
        raw_rows = parse_ohlc_rows(payload)
        page_rows = []
        for row in raw_rows:
            row_ts = int(parse_datetime(str(row["timestamp"])).timestamp())
            if current_ts <= row_ts <= page_end and start_ts <= row_ts <= final_ts:
                page_rows.append(row)
        for row in page_rows:
            rows_by_timestamp[str(row["timestamp"])] = row
        if not page_rows:
            current_ts = page_end + step
        else:
            last_ts = int(parse_datetime(str(page_rows[-1]["timestamp"])).timestamp())
            current_ts = max(last_ts + step, page_end + step)
        if current_ts <= final_ts and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return sorted(rows_by_timestamp.values(), key=lambda row: str(row["timestamp"]))


def write_csv(path: Path, rows: list[dict[str, str | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    market = args.market.lower().replace("/", "").replace("-", "")
    start = parse_datetime(args.start)
    end = parse_datetime(args.end)
    output = Path(args.output) if args.output else default_output_path(market, args.step, start, end)

    try:
        rows = download_ohlcv(
            market=market,
            step=args.step,
            start=start,
            end=end,
            sleep_seconds=args.sleep,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if not rows:
        raise SystemExit("No rows returned. Check market, dates, and Bitstamp availability.")

    write_csv(output, rows)
    print(f"Wrote {len(rows)} candles to {output}")


if __name__ == "__main__":
    main()
