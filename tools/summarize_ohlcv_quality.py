#!/usr/bin/env python3
"""Summarize OHLCV CSV quality across symbols and intervals."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


INTERVAL_DELTAS = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
DEFAULT_INTERVALS = ["15m", "1h", "4h", "1d"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write an OHLCV data quality summary.")
    parser.add_argument("--root", default="data/ohlcv/binance_futures")
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--intervals", nargs="*", default=DEFAULT_INTERVALS)
    parser.add_argument("--tag", default="4year")
    parser.add_argument("--output", default="data/ohlcv/binance_futures/DATA_QUALITY_SUMMARY.md")
    parser.add_argument("--json-output")
    return parser.parse_args()


def _normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def summarize_file(path: Path, interval: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "rows": 0,
            "start": None,
            "end": None,
            "gaps": None,
            "duplicates": None,
            "nan_ohlc": None,
            "zero_volume": None,
        }
    df = pd.read_csv(path)
    timestamps = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    expected = INTERVAL_DELTAS[interval]
    deltas = timestamps.sort_values().diff().dropna()
    core = df[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    volume = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    return {
        "path": str(path),
        "exists": True,
        "rows": int(len(df)),
        "start": pd.Timestamp(timestamps.min()).isoformat() if len(df) else None,
        "end": pd.Timestamp(timestamps.max()).isoformat() if len(df) else None,
        "gaps": int((deltas != expected).sum()),
        "duplicates": int(timestamps.duplicated().sum()),
        "nan_ohlc": int(core.isna().any(axis=1).sum()),
        "zero_volume": int((volume <= 0).sum()),
    }


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Binance Futures OHLCV Data Quality",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Symbol | Interval | Rows | Start | End | Gaps | Duplicates | NaN OHLC | Zero Volume |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {symbol} | {interval} | {rows} | {start} | {end} | {gaps} | {duplicates} | {nan_ohlc} | {zero_volume} |".format(
                symbol=row["symbol"],
                interval=row["interval"],
                rows=row["rows"],
                start=row["start"] or "missing",
                end=row["end"] or "missing",
                gaps="missing" if row["gaps"] is None else row["gaps"],
                duplicates="missing" if row["duplicates"] is None else row["duplicates"],
                nan_ohlc="missing" if row["nan_ohlc"] is None else row["nan_ohlc"],
                zero_volume="missing" if row["zero_volume"] is None else row["zero_volume"],
            )
        )
    lines.extend(
        [
            "",
            "Notes:",
            "- `15m` files are the canonical Binance archive pulls used for engine/training.",
            "- `1h`, `4h`, and `1d` files can be derived from the canonical 15m feed to keep HTF context source-aligned.",
            "- Gaps count timestamp jumps that do not match the expected interval.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    rows: list[dict[str, Any]] = []
    for raw_symbol in args.symbols:
        symbol = _normalize_symbol(raw_symbol)
        for interval in args.intervals:
            path = root / symbol / f"{symbol}_{interval}_{args.tag}.csv"
            summary = summarize_file(path, interval)
            summary.update({"symbol": symbol, "interval": interval})
            rows.append(summary)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(rows), encoding="utf-8")
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote quality summary to {output}")


if __name__ == "__main__":
    main()
