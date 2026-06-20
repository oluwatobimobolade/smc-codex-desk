#!/usr/bin/env python3
"""Derive 1H/4H/1D OHLCV files from canonical 15m candles.

For the SMC engine, this is often better than mixing separately downloaded HTF
files: every higher-timeframe candle is built from the same execution feed used
for entries, and incomplete HTF buckets are dropped.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import load_ohlcv_csv


TARGETS = {
    "1h": {"rule": "1h", "bars": 4},
    "4h": {"rule": "4h", "bars": 16},
    "1d": {"rule": "1D", "bars": 96},
}
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
OPTIONAL_AGGREGATIONS = {
    "close_time": "last",
    "quote_volume": "sum",
    "trade_count": "sum",
    "taker_buy_base_volume": "sum",
    "taker_buy_quote_volume": "sum",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive HTF OHLCV from Binance futures 15m CSV files.")
    parser.add_argument("--data-root", default=str(ROOT / "data/ohlcv/binance_futures"))
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--targets", nargs="*", choices=sorted(TARGETS), default=["1h", "4h", "1d"])
    parser.add_argument("--tag", default="4year", help="Filename tag, e.g. 4year.")
    return parser.parse_args()


def _normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def derive_htf(source: Path, target: str) -> pd.DataFrame:
    if target not in TARGETS:
        raise ValueError(f"Unsupported target: {target}")
    df = load_ohlcv_csv(str(source))
    indexed = df.assign(_ts=pd.to_datetime(df["timestamp"], utc=True)).set_index("_ts")
    rule = TARGETS[target]["rule"]
    expected_bars = int(TARGETS[target]["bars"])

    aggregations = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    for column, aggregation in OPTIONAL_AGGREGATIONS.items():
        if column in indexed.columns:
            aggregations[column] = aggregation

    grouped = indexed.resample(rule, label="left", closed="left")
    ohlcv = grouped.agg(aggregations)
    counts = grouped["close"].count()
    ohlcv = ohlcv.loc[counts == expected_bars].dropna(subset=["open", "high", "low", "close"]).copy()
    if "trade_count" in ohlcv.columns:
        ohlcv["trade_count"] = ohlcv["trade_count"].round().astype("int64")
    ohlcv.insert(0, "timestamp", [pd.Timestamp(ts).isoformat() for ts in ohlcv.index])
    ohlcv["source"] = f"derived_from_15m:{source.name}"
    return ohlcv.reset_index(drop=True)


def main() -> None:
    args = parse_args()
    data_root = Path(args.data_root)
    for raw_symbol in args.symbols:
        symbol = _normalize_symbol(raw_symbol)
        source = data_root / symbol / f"{symbol}_15m_{args.tag}.csv"
        if not source.exists():
            raise SystemExit(f"Missing canonical 15m file for {symbol}: {source}")
        for target in args.targets:
            output = data_root / symbol / f"{symbol}_{target}_{args.tag}.csv"
            derived = derive_htf(source, target)
            output.parent.mkdir(parents=True, exist_ok=True)
            derived.to_csv(output, index=False)
            print(f"Wrote {len(derived)} {symbol} {target} candles -> {output}")


if __name__ == "__main__":
    main()
