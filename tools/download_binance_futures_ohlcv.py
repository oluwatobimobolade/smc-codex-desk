#!/usr/bin/env python3
"""Download Binance USD-M futures OHLCV candles from public archives.

The SMC engine consumes one canonical CSV shape:

    timestamp, open, high, low, close, volume

Binance futures archives include more useful fields, so we preserve them as
extra columns while keeping the engine-required columns first. Historical
training should use the archive source because it is stable, fast, and avoids
REST pagination/geo-DNS flakiness. REST can be added later for same-day live
tail data; the archive normally provides complete daily files the next day.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um"
BINANCE_FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
}
CSV_FIELDS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "source",
]


@dataclass(frozen=True)
class ArchiveFile:
    cadence: str
    url: str
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Binance USD-M futures klines to engine-ready CSV.")
    parser.add_argument("--symbol", required=True, help="Binance futures symbol, e.g. BTCUSDT.")
    parser.add_argument("--interval", default="15m", choices=sorted(INTERVAL_SECONDS), help="Kline interval.")
    parser.add_argument("--start", required=True, help="UTC start date/time: YYYY-MM-DD or ISO timestamp.")
    parser.add_argument("--end", required=True, help="UTC end date/time: YYYY-MM-DD or ISO timestamp.")
    parser.add_argument("--output", help="Output CSV path. Defaults to data/ohlcv/binance_futures/<SYMBOL>/...")
    parser.add_argument("--source", choices=["archive", "rest"], default="archive", help="Historical source to use.")
    parser.add_argument("--sleep", type=float, default=0.05, help="Delay between archive downloads.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per archive file.")
    parser.add_argument("--retry-delay", type=float, default=1.5, help="Initial retry delay in seconds.")
    parser.add_argument(
        "--tail-rest",
        action="store_true",
        help="Fetch missing same-day candles from Binance USD-M Futures REST after archive data.",
    )
    parser.add_argument(
        "--require-rest-tail",
        action="store_true",
        help="Fail if --tail-rest cannot fetch the live REST tail. Default is to warn and keep archive data.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip missing archive files. Useful around listings/delistings or still-unpublished daily files.",
    )
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


def default_output_path(symbol: str, interval: str, start: datetime, end: datetime) -> Path:
    start_label = start.strftime("%Y%m%d")
    end_label = end.strftime("%Y%m%d")
    symbol = symbol.upper()
    return Path("data") / "ohlcv" / "binance_futures" / symbol / f"{symbol}_{interval}_{start_label}_{end_label}.csv"


def _month_iter(start_month: date, end_month: date) -> list[date]:
    months: list[date] = []
    current = start_month.replace(day=1)
    end_month = end_month.replace(day=1)
    while current <= end_month:
        months.append(current)
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = date(year, month, 1)
    return months


def _day_iter(start_day: date, end_day: date) -> list[date]:
    days: list[date] = []
    current = start_day
    while current <= end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


def archive_files(symbol: str, interval: str, start: datetime, end: datetime) -> list[ArchiveFile]:
    """Return monthly full files plus daily files for the final partial month.

    Binance publishes monthly files after a month has completed. For the
    current/final month, daily files are available earlier and keep training
    data close to current without relying on REST.
    """
    if end <= start:
        raise ValueError("--end must be later than --start")

    symbol = symbol.upper()
    start_day = start.date()
    # The end timestamp is exclusive for file selection at day granularity:
    # end=2026-06-20T00:00 should include daily files through 2026-06-19.
    end_inclusive_day = (end - timedelta(milliseconds=1)).date()
    final_month = end_inclusive_day.replace(day=1)
    first_month = start_day.replace(day=1)

    files: list[ArchiveFile] = []

    # Full/partial months before the final month can be fetched as monthly
    # files and filtered later. This is much faster than downloading 30 daily
    # files for every month.
    month_end = final_month - timedelta(days=1)
    if first_month <= month_end.replace(day=1):
        for month in _month_iter(first_month, month_end.replace(day=1)):
            label = f"{symbol}-{interval}-{month:%Y-%m}"
            url = f"{ARCHIVE_ROOT}/monthly/klines/{symbol}/{interval}/{label}.zip"
            files.append(ArchiveFile("monthly", url, label))

    # Final month uses daily files so we can include the newest completed days.
    daily_start = max(start_day, final_month)
    daily_end = end_inclusive_day
    if daily_start <= daily_end:
        for day in _day_iter(daily_start, daily_end):
            label = f"{symbol}-{interval}-{day:%Y-%m-%d}"
            url = f"{ARCHIVE_ROOT}/daily/klines/{symbol}/{interval}/{label}.zip"
            files.append(ArchiveFile("daily", url, label))

    return files


def _timestamp_ms(value: str | int | float) -> int:
    numeric = int(float(value))
    # Spot archive files use microseconds from 2025 onward. USD-M futures
    # currently use milliseconds, but this keeps the parser robust if Binance
    # ever harmonizes archive precision.
    if numeric > 10_000_000_000_000:
        numeric //= 1000
    return numeric


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _row_from_kline(raw: list[str | int | float], start_ms: int, end_ms: int, source: str) -> dict[str, str | float | int] | None:
    open_time = _timestamp_ms(raw[0])
    if open_time < start_ms or open_time >= end_ms:
        return None
    close_time = _timestamp_ms(raw[6])
    return {
        "timestamp": _iso_from_ms(open_time),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_time": _iso_from_ms(close_time),
        "quote_volume": float(raw[7]),
        "trade_count": int(float(raw[8])),
        "taker_buy_base_volume": float(raw[9]),
        "taker_buy_quote_volume": float(raw[10]),
        "source": source,
    }


def parse_kline_csv_bytes(data: bytes, start: datetime, end: datetime, source: str) -> list[dict[str, str | float | int]]:
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows: list[dict[str, str | float | int]] = []
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    for raw in reader:
        if not raw or len(raw) < 11:
            continue
        if raw[0].strip().lower() in {"open_time", "open time"}:
            continue
        row = _row_from_kline(raw, start_ms=start_ms, end_ms=end_ms, source=source)
        if row is not None:
            rows.append(row)
    return rows


def fetch_archive_zip(archive: ArchiveFile, retries: int = 3, retry_delay: float = 1.5) -> bytes:
    attempts = max(1, retries + 1)
    last_error: str | None = None
    for attempt in range(attempts):
        request = Request(archive.url, headers={"User-Agent": "smc-codex-desk/1.0"})
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(archive.url) from exc
            last_error = f"HTTP {exc.code}"
        except URLError as exc:
            last_error = str(exc.reason)
        except OSError as exc:
            last_error = str(exc)
        if attempt < attempts - 1:
            time.sleep(retry_delay * min(2**attempt, 8))
    raise RuntimeError(f"Could not download {archive.url}: {last_error or 'unknown error'}")


def parse_archive_zip(payload: bytes, archive: ArchiveFile, start: datetime, end: datetime) -> list[dict[str, str | float | int]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV found in {archive.label}.zip")
        with zf.open(csv_names[0]) as handle:
            return parse_kline_csv_bytes(handle.read(), start=start, end=end, source=archive.url)


def _rest_url(symbol: str, interval: str, start_ms: int, end_ms: int, limit: int = 1500) -> str:
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": start_ms,
        "endTime": max(start_ms, end_ms - 1),
        "limit": min(max(limit, 1), 1500),
    }
    return f"{BINANCE_FAPI_KLINES_URL}?{urlencode(params)}"


def fetch_rest_klines(url: str, retries: int = 3, retry_delay: float = 1.5) -> list[list[str | int | float]]:
    attempts = max(1, retries + 1)
    last_error: str | None = None
    for attempt in range(attempts):
        request = Request(url, headers={"User-Agent": "smc-codex-desk/1.0"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, list):
                raise RuntimeError(f"Unexpected Binance REST response: {payload!r}")
            return payload
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except URLError as exc:
            last_error = str(exc.reason)
        except OSError as exc:
            last_error = str(exc)
        if attempt < attempts - 1:
            time.sleep(retry_delay * min(2**attempt, 8))
    raise RuntimeError(f"Could not download Binance REST klines from {url}: {last_error or 'unknown error'}")


def parse_rest_klines(data: list[list[str | int | float]], start: datetime, end: datetime, source: str) -> list[dict[str, str | float | int]]:
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows: list[dict[str, str | float | int]] = []
    for raw in data:
        if len(raw) < 11:
            continue
        row = _row_from_kline(raw, start_ms=start_ms, end_ms=end_ms, source=source)
        if row is not None:
            rows.append(row)
    return rows


def download_rest_ohlcv(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    sleep_seconds: float = 0.05,
    retries: int = 3,
    retry_delay: float = 1.5,
) -> list[dict[str, str | float | int]]:
    interval_ms = INTERVAL_SECONDS[interval] * 1000
    end_ms = int(end.timestamp() * 1000)
    cursor_ms = int(start.timestamp() * 1000)
    rows_by_timestamp: dict[str, dict[str, str | float | int]] = {}

    while cursor_ms < end_ms:
        url = _rest_url(symbol=symbol, interval=interval, start_ms=cursor_ms, end_ms=end_ms)
        payload = fetch_rest_klines(url, retries=retries, retry_delay=retry_delay)
        if not payload:
            break
        page_start = datetime.fromtimestamp(cursor_ms / 1000, tz=timezone.utc)
        for row in parse_rest_klines(payload, start=page_start, end=end, source=BINANCE_FAPI_KLINES_URL):
            rows_by_timestamp[str(row["timestamp"])] = row

        last_open_ms = _timestamp_ms(payload[-1][0])
        next_cursor_ms = last_open_ms + interval_ms
        if next_cursor_ms <= cursor_ms:
            break
        cursor_ms = next_cursor_ms
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return sorted(rows_by_timestamp.values(), key=lambda row: str(row["timestamp"]))


def download_ohlcv(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    sleep_seconds: float = 0.05,
    retries: int = 3,
    retry_delay: float = 1.5,
    allow_missing: bool = False,
    tail_rest: bool = False,
    require_rest_tail: bool = False,
) -> list[dict[str, str | float | int]]:
    rows_by_timestamp: dict[str, dict[str, str | float | int]] = {}
    missing: list[str] = []
    for archive in archive_files(symbol=symbol, interval=interval, start=start, end=end):
        try:
            payload = fetch_archive_zip(archive, retries=retries, retry_delay=retry_delay)
        except FileNotFoundError:
            if allow_missing:
                missing.append(archive.label)
                continue
            raise
        for row in parse_archive_zip(payload, archive=archive, start=start, end=end):
            rows_by_timestamp[str(row["timestamp"])] = row
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    if tail_rest:
        interval_ms = INTERVAL_SECONDS[interval] * 1000
        if rows_by_timestamp:
            latest_timestamp = max(pd_timestamp_ms(timestamp) for timestamp in rows_by_timestamp)
            rest_start = datetime.fromtimestamp((latest_timestamp + interval_ms) / 1000, tz=timezone.utc)
        else:
            rest_start = start
        if rest_start < end:
            try:
                for row in download_rest_ohlcv(
                    symbol=symbol,
                    interval=interval,
                    start=rest_start,
                    end=end,
                    sleep_seconds=sleep_seconds,
                    retries=retries,
                    retry_delay=retry_delay,
                ):
                    rows_by_timestamp[str(row["timestamp"])] = row
            except Exception as exc:
                if require_rest_tail:
                    raise
                print(f"Warning: Binance REST tail unavailable; keeping archive rows only. Detail: {exc}")

    rows = sorted(rows_by_timestamp.values(), key=lambda row: str(row["timestamp"]))
    if missing:
        print(f"Skipped {len(missing)} missing archive files: {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}")
    return rows


def pd_timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper().replace("/", "").replace("-", "")
    start = parse_datetime(args.start)
    end = parse_datetime(args.end)
    output = Path(args.output) if args.output else default_output_path(symbol, args.interval, start, end)
    if args.source == "rest":
        rows = download_rest_ohlcv(
            symbol=symbol,
            interval=args.interval,
            start=start,
            end=end,
            sleep_seconds=args.sleep,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
    else:
        rows = download_ohlcv(
            symbol=symbol,
            interval=args.interval,
            start=start,
            end=end,
            sleep_seconds=args.sleep,
            retries=args.retries,
            retry_delay=args.retry_delay,
            allow_missing=args.allow_missing,
            tail_rest=args.tail_rest,
            require_rest_tail=args.require_rest_tail,
        )
    if not rows:
        raise SystemExit("No rows returned. Check symbol, dates, interval, and Binance archive availability.")
    write_csv(output, rows)
    print(f"Wrote {len(rows)} Binance USD-M futures candles to {output}")


if __name__ == "__main__":
    main()
