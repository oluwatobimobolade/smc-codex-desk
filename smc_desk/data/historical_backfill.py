"""Historical OHLCV backfill and depth checks.

The live route can fetch a recent verified batch. This module handles deeper
closed-candle pagination for AI SMC context and records depth warnings when
HTF context is shallow.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.data.live_ohlcv import INTERVAL_MS


DEFAULT_MINIMUM_DEPTH = {
    "15m": 1500,
    "1h": 1000,
    "4h": 500,
    "1d": 365,
}

FOREX_MINIMUM_DEPTH = {
    "15m": 800,
    "1h": 500,
    "4h": 300,
    "1d": 200,
}

MINIMUM_CONTEXT_DEPTH = DEFAULT_MINIMUM_DEPTH


HistoricalPageFetcher = Callable[[str, str, int, int | None], tuple[list[Any], int]]


@dataclass(frozen=True)
class BackfillResult:
    symbol: str
    interval: str
    dataframe: pd.DataFrame
    manifest: dict[str, Any]


def fetch_historical_closed_ohlcv(
    *,
    symbol: str,
    interval: str,
    required_candles: int | None = None,
    fetcher: HistoricalPageFetcher,
    page_limit: int = 1500,
    cache_dir: str | Path | None = None,
) -> BackfillResult:
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")
    required = int(required_candles or MINIMUM_CONTEXT_DEPTH.get(interval, 1500))
    if required <= 0:
        raise ValueError("required_candles must be positive")
    page_limit = min(max(int(page_limit), 1), 1500)
    pages: list[list[Any]] = []
    all_rows: list[dict[str, Any]] = []
    end_time_ms: int | None = None
    server_time_ms: int | None = None
    page_count = 0
    seen_page_keys: set[int] = set()

    while len(all_rows) < required:
        raw_rows, server_time_ms = fetcher(symbol, interval, page_limit, end_time_ms)
        if not raw_rows:
            break
        parsed = [_parse_raw_kline(row, server_time_ms) for row in raw_rows]
        parsed = [row for row in parsed if row is not None]
        if not parsed:
            break
        first_open_ms = int(parsed[0]["open_ms"])
        if first_open_ms in seen_page_keys:
            break
        seen_page_keys.add(first_open_ms)
        pages.append(raw_rows)
        all_rows.extend(parsed)
        page_count += 1
        earliest_open_ms = min(int(row["open_ms"]) for row in parsed)
        end_time_ms = earliest_open_ms - 1
        if len(raw_rows) < page_limit:
            break

    df = _rows_to_frame(all_rows)
    if df.empty:
        raise ValueError("Backfill produced no closed candles")
    df = _deduplicate_and_sort(df)
    _verify_monotonic(df, interval)
    if len(df) > required:
        df = df.tail(required).reset_index(drop=True)
    depth = build_context_depth_report({interval: df})[interval]
    manifest = {
        "schema": "historical_backfill_manifest_v1",
        "symbol": symbol,
        "interval": interval,
        "provider": "injected_page_fetcher",
        "required_candles": required,
        "row_count": int(len(df)),
        "page_limit": page_limit,
        "page_count": page_count,
        "current_forming_candle_excluded": True,
        "server_time_ms": server_time_ms,
        "first_timestamp": str(df["timestamp"].iloc[0]),
        "last_timestamp": str(df["timestamp"].iloc[-1]),
        "data_sha256": _hash_df(df),
        "context_depth": depth,
    }
    if cache_dir is not None:
        cache_path = Path(cache_dir).expanduser().resolve()
        cache_path.mkdir(parents=True, exist_ok=True)
        csv_path = cache_path / f"{symbol}_{interval}_historical_backfill.csv"
        manifest_path = cache_path / f"{symbol}_{interval}_historical_backfill_manifest.json"
        df.to_csv(csv_path, index=False)
        import json

        manifest["cache_csv"] = str(csv_path)
        manifest["cache_manifest"] = str(manifest_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return BackfillResult(symbol=symbol, interval=interval, dataframe=df, manifest=manifest)


def build_context_depth_report(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    *,
    minimum_depths: Mapping[str, int] = MINIMUM_CONTEXT_DEPTH,
) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for timeframe, df in timeframe_dfs.items():
        required = int(minimum_depths.get(timeframe, 0))
        count = int(len(df))
        status = "PASS" if required == 0 or count >= required else "SHALLOW_CONTEXT"
        report[timeframe] = {
            "timeframe": timeframe,
            "row_count": count,
            "minimum_required": required,
            "status": status,
            "context_depth_warning": status == "SHALLOW_CONTEXT",
            "authority_adjustment": "normal" if status == "PASS" else "reduce_confidence_or_review_required",
        }
    return report


def assert_minimum_context_depth(timeframe_dfs: Mapping[str, pd.DataFrame]) -> None:
    report = build_context_depth_report(timeframe_dfs)
    shallow = [tf for tf, item in report.items() if item["context_depth_warning"]]
    if shallow:
        raise ValueError(f"Insufficient HTF context depth for: {', '.join(shallow)}")


def _parse_raw_kline(row: Any, server_time_ms: int) -> dict[str, Any] | None:
    if isinstance(row, Mapping):
        open_ms = _to_ms(row.get("open_time") or row.get("timestamp") or row.get("open_ms"))
        close_ms = _to_ms(row.get("close_time") or row.get("close_ms"))
        if close_ms is None and open_ms is not None:
            close_ms = open_ms
        values = {
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume", 0),
        }
    else:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError(f"Malformed kline row: {row!r}")
        open_ms = int(row[0])
        close_ms = int(row[6])
        values = {"open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
    if open_ms is None or close_ms is None:
        raise ValueError(f"Kline row missing timestamps: {row!r}")
    if close_ms > server_time_ms:
        return None
    high = float(values["high"])
    low = float(values["low"])
    open_px = float(values["open"])
    close_px = float(values["close"])
    if high < max(open_px, close_px, low) or low > min(open_px, close_px, high):
        raise ValueError(f"Invalid OHLC row: {row!r}")
    return {
        "open_ms": open_ms,
        "close_ms": close_ms,
        "timestamp": datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc),
        "open": open_px,
        "high": high,
        "low": low,
        "close": close_px,
        "volume": float(values["volume"]),
        "is_final": True,
    }


def _rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(rows)[["timestamp", "open", "high", "low", "close", "volume", "open_ms", "close_ms", "is_final"]]


def _deduplicate_and_sort(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def _verify_monotonic(df: pd.DataFrame, interval: str) -> None:
    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    if not timestamps.is_monotonic_increasing:
        raise ValueError("Backfill timestamps are not monotonic increasing")
    if timestamps.duplicated().any():
        raise ValueError("Backfill timestamps contain duplicates")
    interval_ms = INTERVAL_MS[interval]
    if "open_ms" in df.columns:
        opens = [int(value) for value in df["open_ms"].to_list()]
    else:
        opens = [int(timestamp.timestamp() * 1000) for timestamp in timestamps]
    gaps = [right - left for left, right in zip(opens, opens[1:]) if right - left != interval_ms]
    if gaps:
        raise ValueError("Backfill timestamps contain interval gaps")


def _to_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    timestamp = pd.to_datetime(value, utc=True)
    return int(timestamp.timestamp() * 1000)


def _hash_df(df: pd.DataFrame) -> str:
    payload = df[["timestamp", "open", "high", "low", "close", "volume"]].to_json(orient="records", date_format="iso")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
