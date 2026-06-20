#!/usr/bin/env python3
"""Repair Binance futures 15m monthly-archive anomalies using daily archives."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.download_binance_futures_ohlcv import download_ohlcv, parse_datetime, write_csv


DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace suspect Binance 15m archive days with daily archive rows.")
    parser.add_argument("--data-root", default=str(ROOT / "data/ohlcv/binance_futures"))
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--tag", default="4year")
    parser.add_argument("--dates", nargs="*", help="UTC dates to repair. Defaults to flat zero-volume days per symbol.")
    parser.add_argument("--output-report", default=str(ROOT / "data/ohlcv/binance_futures/DAILY_REPAIR_REPORT.json"))
    parser.add_argument("--backup", action="store_true", default=True)
    parser.add_argument("--sleep", type=float, default=0.03)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    return parser.parse_args()


def _normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def _date(value: str) -> date:
    return datetime.fromisoformat(value.strip()).date()


def _flat_zero_volume_days(df: pd.DataFrame) -> list[date]:
    flat = (
        (pd.to_numeric(df["volume"], errors="coerce").fillna(0) == 0)
        & (pd.to_numeric(df["open"], errors="coerce") == pd.to_numeric(df["high"], errors="coerce"))
        & (pd.to_numeric(df["high"], errors="coerce") == pd.to_numeric(df["low"], errors="coerce"))
        & (pd.to_numeric(df["low"], errors="coerce") == pd.to_numeric(df["close"], errors="coerce"))
    )
    return sorted(pd.to_datetime(df.loc[flat, "timestamp"], utc=True).dt.date.unique().tolist())


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [column.strip().lower() for column in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def _rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    daily = pd.DataFrame(rows)
    daily["timestamp"] = pd.to_datetime(daily["timestamp"], utc=True, errors="coerce")
    return daily.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def repair_symbol(path: Path, symbol: str, repair_dates: list[date] | None, args: argparse.Namespace) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    original = _load(path)
    dates = repair_dates or _flat_zero_volume_days(original)
    report: dict[str, Any] = {
        "symbol": symbol,
        "path": str(path),
        "dates_requested": [item.isoformat() for item in dates],
        "dates_repaired": [],
        "rows_before": int(len(original)),
        "rows_after": None,
        "changed_rows": 0,
        "backup": None,
    }
    if not dates:
        report["rows_after"] = int(len(original))
        return report

    repaired = original.copy()
    changed_rows = 0
    for day in dates:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        rows = download_ohlcv(
            symbol=symbol,
            interval="15m",
            start=start,
            end=end,
            sleep_seconds=args.sleep,
            retries=args.retries,
            retry_delay=args.retry_delay,
            allow_missing=False,
        )
        daily = _rows_to_frame(rows)
        if len(daily) != 96:
            raise RuntimeError(f"{symbol} {day} daily archive returned {len(daily)} rows, expected 96.")
        mask = repaired["timestamp"].dt.date == day
        before = repaired.loc[mask].copy()
        changed = before.merge(daily, on="timestamp", how="outer", suffixes=("_before", "_daily"), indicator=True)
        value_cols = [column for column in ["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume"] if column in before.columns and column in daily.columns]
        row_changed = changed["_merge"] != "both"
        for column in value_cols:
            left = pd.to_numeric(changed.get(f"{column}_before"), errors="coerce")
            right = pd.to_numeric(changed.get(f"{column}_daily"), errors="coerce")
            row_changed = row_changed | ((left - right).abs().fillna(0) > 1e-9)
        changed_rows += int(row_changed.sum())

        repaired = repaired.loc[~mask].copy()
        repaired = pd.concat([repaired, daily], ignore_index=True, sort=False)
        repaired = repaired.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
        report["dates_repaired"].append(day.isoformat())

    if args.backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(f".pre_daily_repair_{stamp}.csv")
        shutil.copy2(path, backup)
        report["backup"] = str(backup)

    write_csv(path, repaired.to_dict("records"))
    report["rows_after"] = int(len(repaired))
    report["changed_rows"] = changed_rows
    return report


def main() -> None:
    args = parse_args()
    data_root = Path(args.data_root)
    requested_dates = [_date(value) for value in args.dates] if args.dates else None
    reports = []
    for raw_symbol in args.symbols:
        symbol = _normalize_symbol(raw_symbol)
        path = data_root / symbol / f"{symbol}_15m_{args.tag}.csv"
        reports.append(repair_symbol(path=path, symbol=symbol, repair_dates=requested_dates, args=args))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reports": reports,
    }
    output = Path(args.output_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
