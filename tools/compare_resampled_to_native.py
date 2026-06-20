#!/usr/bin/env python3
"""Compare HTF candles resampled from 15m against native exchange HTF candles."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.derive_htf_from_15m import TARGETS, derive_htf


NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]
TIMESTAMP_COLUMNS = ["close_time"]


@dataclass
class ColumnComparison:
    column: str
    compared_rows: int
    mismatches: int
    max_abs_diff: float
    max_rel_diff: float
    first_mismatch_timestamp: str | None
    derived_value: Any
    native_value: Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stress-test resampled HTF candles against native exchange HTF candles.")
    parser.add_argument("--source-15m", required=True, help="Canonical 15m CSV.")
    parser.add_argument("--native", required=True, help="Native HTF CSV downloaded from the exchange/archive.")
    parser.add_argument("--target", choices=sorted(TARGETS), default="1h")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--price-tol", type=float, default=1e-9)
    parser.add_argument("--volume-tol", type=float, default=1e-6)
    parser.add_argument("--quote-tol", type=float, default=1e-3)
    parser.add_argument("--fail-on-mismatch", action="store_true")
    return parser.parse_args()


def _load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [column.strip().lower() for column in df.columns]
    if "timestamp" not in df.columns:
        raise ValueError(f"Missing timestamp column: {path}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return df.reset_index(drop=True)


def _tolerance(column: str, args: argparse.Namespace) -> float:
    if column in {"open", "high", "low", "close"}:
        return args.price_tol
    if column in {"quote_volume", "taker_buy_quote_volume"}:
        return args.quote_tol
    return args.volume_tol


def _compare_numeric(merged: pd.DataFrame, column: str, args: argparse.Namespace) -> ColumnComparison:
    left = pd.to_numeric(merged[f"{column}_derived"], errors="coerce")
    right = pd.to_numeric(merged[f"{column}_native"], errors="coerce")
    diff = (left - right).abs()
    denom = right.abs().where(right.abs() > 1e-12, 1.0)
    rel = diff / denom
    mismatched = diff > _tolerance(column, args)
    first = merged.loc[mismatched].head(1)
    return ColumnComparison(
        column=column,
        compared_rows=int(len(merged)),
        mismatches=int(mismatched.sum()),
        max_abs_diff=float(diff.max()) if len(diff) else 0.0,
        max_rel_diff=float(rel.max()) if len(rel) else 0.0,
        first_mismatch_timestamp=None if first.empty else pd.Timestamp(first.iloc[0]["timestamp"]).isoformat(),
        derived_value=None if first.empty else first.iloc[0][f"{column}_derived"].item() if hasattr(first.iloc[0][f"{column}_derived"], "item") else first.iloc[0][f"{column}_derived"],
        native_value=None if first.empty else first.iloc[0][f"{column}_native"].item() if hasattr(first.iloc[0][f"{column}_native"], "item") else first.iloc[0][f"{column}_native"],
    )


def _compare_timestamp(merged: pd.DataFrame, column: str) -> ColumnComparison:
    left = pd.to_datetime(merged[f"{column}_derived"], utc=True, errors="coerce")
    right = pd.to_datetime(merged[f"{column}_native"], utc=True, errors="coerce")
    mismatched = left != right
    first = merged.loc[mismatched].head(1)
    diffs = (left - right).abs().dt.total_seconds().fillna(0)
    return ColumnComparison(
        column=column,
        compared_rows=int(len(merged)),
        mismatches=int(mismatched.sum()),
        max_abs_diff=float(diffs.max()) if len(diffs) else 0.0,
        max_rel_diff=0.0,
        first_mismatch_timestamp=None if first.empty else pd.Timestamp(first.iloc[0]["timestamp"]).isoformat(),
        derived_value=None if first.empty else str(first.iloc[0][f"{column}_derived"]),
        native_value=None if first.empty else str(first.iloc[0][f"{column}_native"]),
    )


def _source_bucket_counts(source_15m: Path, target: str) -> dict[str, Any]:
    df = _load_csv(source_15m)
    rule = TARGETS[target]["rule"]
    expected = int(TARGETS[target]["bars"])
    counts = df.set_index("timestamp").resample(rule, label="left", closed="left")["close"].count()
    complete = counts[counts == expected]
    incomplete = counts[(counts > 0) & (counts != expected)]
    return {
        "expected_15m_bars_per_bucket": expected,
        "complete_buckets": int(len(complete)),
        "incomplete_non_empty_buckets": int(len(incomplete)),
        "first_incomplete_bucket": None if incomplete.empty else pd.Timestamp(incomplete.index[0]).isoformat(),
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# Resample vs Native Audit - {payload['symbol']} {payload['target']}",
        "",
        f"Generated at: {payload['generated_at']}",
        "",
        "## Verdict",
        f"- Status: **{payload['verdict']}**",
        f"- Matched candles: {payload['matched_rows']} / native {payload['native_rows']} / derived {payload['derived_rows']}",
        f"- Native-only timestamps: {payload['native_only_rows']}",
        f"- Derived-only timestamps: {payload['derived_only_rows']}",
        f"- Total field mismatches: {payload['total_field_mismatches']}",
        "",
        "## Source Bucket Integrity",
        f"- Expected 15m bars per {payload['target']}: {payload['bucket_counts']['expected_15m_bars_per_bucket']}",
        f"- Complete buckets: {payload['bucket_counts']['complete_buckets']}",
        f"- Incomplete non-empty buckets: {payload['bucket_counts']['incomplete_non_empty_buckets']}",
        f"- First incomplete bucket: {payload['bucket_counts']['first_incomplete_bucket']}",
        "",
        "## Column Comparison",
        "| Column | Rows | Mismatches | Max Abs Diff | Max Rel Diff | First Mismatch |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for item in payload["columns"]:
        lines.append(
            f"| {item['column']} | {item['compared_rows']} | {item['mismatches']} | "
            f"{item['max_abs_diff']:.12g} | {item['max_rel_diff']:.12g} | {item['first_mismatch_timestamp'] or ''} |"
        )
    lines.extend(
        [
            "",
            "## Inputs",
            f"- 15m source: `{payload['source_15m']}`",
            f"- native source: `{payload['native']}`",
            "",
            "## Interpretation",
            "- A clean audit means the 15m archive can reproduce native HTF candles exactly within numeric tolerances.",
            "- The engine should still resample HTF internally from visible 15m candles for no-future-leakage decisions.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    source_15m = Path(args.source_15m)
    native_path = Path(args.native)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    derived = derive_htf(source_15m, args.target)
    native = _load_csv(native_path)
    derived["timestamp"] = pd.to_datetime(derived["timestamp"], utc=True, errors="coerce")

    comparable = [column for column in NUMERIC_COLUMNS + TIMESTAMP_COLUMNS if column in derived.columns and column in native.columns]
    merged = derived.merge(native, on="timestamp", how="outer", suffixes=("_derived", "_native"), indicator=True)
    matched = merged.loc[merged["_merge"] == "both"].copy()
    native_only = merged.loc[merged["_merge"] == "right_only"].copy()
    derived_only = merged.loc[merged["_merge"] == "left_only"].copy()

    column_results: list[ColumnComparison] = []
    for column in comparable:
        if column in TIMESTAMP_COLUMNS:
            column_results.append(_compare_timestamp(matched, column))
        else:
            column_results.append(_compare_numeric(matched, column, args))

    mismatch_rows: list[pd.DataFrame] = []
    for result in column_results:
        column = result.column
        if result.mismatches == 0:
            continue
        if column in TIMESTAMP_COLUMNS:
            left = pd.to_datetime(matched[f"{column}_derived"], utc=True, errors="coerce")
            right = pd.to_datetime(matched[f"{column}_native"], utc=True, errors="coerce")
            bad = matched.loc[left != right, ["timestamp", f"{column}_derived", f"{column}_native"]].copy()
            bad["column"] = column
            bad["abs_diff"] = (left - right).abs().dt.total_seconds()
        else:
            left = pd.to_numeric(matched[f"{column}_derived"], errors="coerce")
            right = pd.to_numeric(matched[f"{column}_native"], errors="coerce")
            bad = matched.loc[(left - right).abs() > _tolerance(column, args), ["timestamp", f"{column}_derived", f"{column}_native"]].copy()
            bad["column"] = column
            bad["abs_diff"] = (left - right).abs()
        mismatch_rows.append(bad.head(50))

    total_mismatches = sum(result.mismatches for result in column_results)
    verdict = "PASS" if total_mismatches == 0 and len(native_only) == 0 and len(derived_only) == 0 else "FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": source_15m.parent.name,
        "target": args.target,
        "source_15m": str(source_15m.resolve()),
        "native": str(native_path.resolve()),
        "verdict": verdict,
        "derived_rows": int(len(derived)),
        "native_rows": int(len(native)),
        "matched_rows": int(len(matched)),
        "native_only_rows": int(len(native_only)),
        "derived_only_rows": int(len(derived_only)),
        "comparable_columns": comparable,
        "total_field_mismatches": int(total_mismatches),
        "bucket_counts": _source_bucket_counts(source_15m, args.target),
        "columns": [asdict(result) for result in column_results],
    }

    (out_dir / "resample_vs_native.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_markdown(out_dir / "resample_vs_native.md", payload)
    if mismatch_rows:
        pd.concat(mismatch_rows, ignore_index=True).to_csv(out_dir / "mismatches.csv", index=False)
    else:
        (out_dir / "mismatches.csv").write_text("timestamp,column,derived,native,abs_diff\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, default=str))
    if args.fail_on_mismatch and verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
