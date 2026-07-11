"""Canonical local OHLCV contract used before perception is allowed to run."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
PRICE_COLUMNS = ("open", "high", "low", "close")
CANONICAL_STEP = pd.Timedelta(minutes=15)


class OHLCVContractError(ValueError):
    """Raised when market-source rows cannot satisfy the canonical contract."""

    def __init__(self, issues: Iterable[dict[str, Any]]):
        self.issues = list(issues)
        codes = ", ".join(str(issue.get("code")) for issue in self.issues)
        super().__init__(f"OHLCV contract failed: {codes}")


def load_ohlcv_csv(path: str | Path) -> pd.DataFrame:
    """Load a CSV without silently sorting or deleting invalid market rows."""
    frame = pd.read_csv(Path(path))
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if "date" in frame.columns and "timestamp" not in frame.columns:
        frame = frame.rename(columns={"date": "timestamp"})
    missing = set(OHLCV_COLUMNS[:-1]).difference(frame.columns)
    if missing:
        raise OHLCVContractError(
            [{"code": "missing_columns", "columns": sorted(missing)}]
        )
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    return normalize_ohlcv(frame, sort=False)


def normalize_ohlcv_timestamps(
    frame: pd.DataFrame,
    *,
    sort: bool = True,
) -> pd.DataFrame:
    """Compatibility normalizer with explicit sorting behavior."""
    return normalize_ohlcv(frame, sort=sort)


def normalize_ohlcv(frame: pd.DataFrame, *, sort: bool = False) -> pd.DataFrame:
    normalized = frame.copy()
    if "timestamp" not in normalized.columns:
        raise OHLCVContractError([{"code": "missing_columns", "columns": ["timestamp"]}])
    parsed = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
    normalized["timestamp"] = parsed.dt.tz_convert(None)
    for column in (*PRICE_COLUMNS, "volume"):
        if column not in normalized.columns:
            if column == "volume":
                normalized[column] = 0.0
                continue
            raise OHLCVContractError([{"code": "missing_columns", "columns": [column]}])
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if sort:
        normalized = normalized.sort_values("timestamp", kind="stable")
    return normalized.reset_index(drop=True)


def data_quality_report(
    frame: pd.DataFrame,
    *,
    expected_step_minutes: int = 15,
) -> dict[str, Any]:
    """Report source truth defects without mutating or reordering the rows."""
    normalized = normalize_ohlcv(frame, sort=False)
    timestamps = pd.to_datetime(normalized["timestamp"], utc=False)
    expected = pd.Timedelta(minutes=expected_step_minutes)
    duplicate_mask = timestamps.duplicated(keep=False)
    deltas = timestamps.diff()
    out_of_order = deltas < pd.Timedelta(0)
    forward_gaps = deltas > expected
    irregular_positive = (deltas > pd.Timedelta(0)) & (deltas != expected)
    nan_timestamp = timestamps.isna()
    nan_ohlc = normalized[list(PRICE_COLUMNS)].isna().any(axis=1)
    finite_ohlc = normalized[list(PRICE_COLUMNS)].apply(
        lambda column: column.map(lambda value: _is_finite(value))
    ).all(axis=1)
    invalid_bounds = _invalid_ohlc_bounds(normalized)
    volume = normalized["volume"]
    invalid_volume = volume.isna() | ~volume.map(_is_finite) | (volume < 0)
    issue_rows = {
        "invalid_timestamp": _indices(nan_timestamp),
        "duplicate_timestamp": _indices(duplicate_mask),
        "out_of_order": _indices(out_of_order),
        "missing_15m_candle": _indices(forward_gaps),
        "irregular_interval": _indices(irregular_positive),
        "invalid_ohlc_numeric": _indices(nan_ohlc | ~finite_ohlc),
        "invalid_ohlc_bounds": _indices(invalid_bounds),
        "invalid_volume": _indices(invalid_volume),
    }
    return {
        "schema": "canonical_ohlcv_quality_v1",
        "rows": int(len(normalized)),
        "start": _iso_or_none(timestamps.iloc[0]) if len(normalized) else None,
        "end": _iso_or_none(timestamps.iloc[-1]) if len(normalized) else None,
        "expected_step_minutes": expected_step_minutes,
        "duplicate_timestamps": int(duplicate_mask.sum()),
        "out_of_order_rows": int(out_of_order.sum()),
        "gap_count": int(forward_gaps.sum()),
        "irregular_interval_count": int(irregular_positive.sum()),
        "nan_ohlc_rows": int(nan_ohlc.sum()),
        "invalid_ohlc_bounds_rows": int(invalid_bounds.sum()),
        "invalid_volume_rows": int(invalid_volume.sum()),
        "issue_rows": issue_rows,
        "status": "FAIL" if any(issue_rows.values()) else "PASS",
    }


def validate_canonical_15m(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_ohlcv(frame, sort=False)
    report = data_quality_report(normalized, expected_step_minutes=15)
    issues = [
        {"code": code, "row_indices": rows}
        for code, rows in report["issue_rows"].items()
        if rows
    ]
    if not len(normalized):
        issues.append({"code": "empty_source", "row_indices": []})
    if issues:
        raise OHLCVContractError(issues)
    return normalized


def slice_closed_15m(
    frame: pd.DataFrame,
    decision_time: str | pd.Timestamp,
) -> pd.DataFrame:
    """Return rows whose scheduled 15m close is at or before decision time."""
    normalized = validate_canonical_15m(frame)
    decision = as_utc_naive(decision_time)
    close_times = normalized["timestamp"] + CANONICAL_STEP
    visible = normalized.loc[close_times <= decision].reset_index(drop=True)
    if visible.empty:
        raise OHLCVContractError([{"code": "no_closed_rows_at_decision"}])
    return visible


def as_utc_naive(value: str | pd.Timestamp) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.tz_convert("UTC").tz_localize(None)


def _invalid_ohlc_bounds(frame: pd.DataFrame) -> pd.Series:
    high_floor = frame[["open", "low", "close"]].max(axis=1)
    low_ceiling = frame[["open", "high", "close"]].min(axis=1)
    return (frame["high"] < high_floor) | (frame["low"] > low_ceiling)


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _indices(mask: pd.Series) -> list[int]:
    return [int(index) for index in mask[mask].index]


def _iso_or_none(value: Any) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()
