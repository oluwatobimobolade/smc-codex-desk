"""Decision-time candle and timeframe certification for perception research."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from smc_desk.data.hashing import dataframe_sha256, file_sha256, object_sha256
from smc_desk.data.ohlcv_contract import (
    OHLCV_COLUMNS,
    OHLCVContractError,
    as_utc_naive,
    data_quality_report,
    normalize_ohlcv,
    slice_closed_15m,
    validate_canonical_15m,
)


TIMEFRAME_SPEC: dict[str, tuple[pd.Timedelta, int, str]] = {
    "1h": (pd.Timedelta(hours=1), 4, "1h"),
    "4h": (pd.Timedelta(hours=4), 16, "4h"),
    "1d": (pd.Timedelta(days=1), 96, "1D"),
}


@dataclass(frozen=True)
class CertifiedMarketTruth:
    certificate: dict[str, Any]
    visible_15m: pd.DataFrame
    timeframe_dfs: dict[str, pd.DataFrame]


def certify_market_truth(
    source_df: pd.DataFrame,
    *,
    symbol: str,
    decision_time: str | pd.Timestamp,
    dataset_id: str,
    source_path: str | Path | None = None,
    observed_symbol: str | None = None,
) -> CertifiedMarketTruth:
    """Certify exact closed candles and their derived HTF lineage.

    Future rows may exist in ``source_df``; they are recorded but never enter
    the visible frame or any HTF bucket.  Source defects are fatal because a
    detector cannot repair market truth.
    """
    normalized = normalize_ohlcv(source_df, sort=False)
    quality = data_quality_report(normalized, expected_step_minutes=15)
    issues: list[dict[str, Any]] = []
    if quality["status"] != "PASS":
        issues.extend(
            {"code": code, "row_indices": rows}
            for code, rows in quality["issue_rows"].items()
            if rows
        )
    canonical_symbol = _normalize_symbol(symbol)
    if observed_symbol is not None and _normalize_symbol(observed_symbol) != canonical_symbol:
        issues.append(
            {
                "code": "source_symbol_mismatch",
                "expected": canonical_symbol,
                "observed": _normalize_symbol(observed_symbol),
            }
        )
    if issues:
        raise OHLCVContractError(issues)

    validated = validate_canonical_15m(normalized)
    decision = as_utc_naive(decision_time)
    visible = slice_closed_15m(validated, decision)
    future_rows = validated.loc[
        validated["timestamp"] + pd.Timedelta(minutes=15) > decision
    ]

    frames: dict[str, pd.DataFrame] = {"15m": visible.copy()}
    lineage: dict[str, list[dict[str, Any]]] = {}
    exclusions: dict[str, list[dict[str, Any]]] = {}
    for timeframe in ("1h", "4h", "1d"):
        frame, tf_lineage, tf_exclusions = reconstruct_certified_timeframe(
            visible,
            timeframe=timeframe,
            decision_time=decision,
        )
        frames[timeframe] = frame
        lineage[timeframe] = tf_lineage
        exclusions[timeframe] = tf_exclusions

    dataset_hash = dataframe_sha256(validated, columns=OHLCV_COLUMNS)
    source_file_hash = (
        file_sha256(source_path)
        if source_path is not None and Path(source_path).exists()
        else None
    )
    timeframe_hashes = {
        timeframe: dataframe_sha256(frame, columns=OHLCV_COLUMNS)
        for timeframe, frame in frames.items()
    }
    certificate: dict[str, Any] = {
        "schema": "market_truth_certificate_v1",
        "status": "PASS",
        "canonical_scope": {
            "venue": "BINANCE_USD_M",
            "instrument": canonical_symbol,
            "market_type": "perpetual_futures",
            "source_timeframe": "15m",
            "timezone": "UTC",
            "daily_boundary": "00:00_UTC",
        },
        "dataset_id": dataset_id,
        "dataset_sha256": dataset_hash,
        "source_file_sha256": source_file_hash,
        "decision_time": _iso(decision),
        "decision_contract": "candle_open_plus_duration_lte_decision_time",
        "source_quality": quality,
        "source_row_count": int(len(validated)),
        "visible_15m_row_count": int(len(visible)),
        "future_rows_excluded": int(len(future_rows)),
        "last_visible_15m_open": _iso(visible["timestamp"].iloc[-1]),
        "last_visible_15m_close": _iso(
            visible["timestamp"].iloc[-1] + pd.Timedelta(minutes=15)
        ),
        "timeframe_hashes": timeframe_hashes,
        "timeframe_rows": {key: int(len(value)) for key, value in frames.items()},
        "lineage": lineage,
        "excluded_incomplete_buckets": exclusions,
        "invariants": {
            "source_is_strictly_monotonic": True,
            "source_has_no_duplicates": True,
            "source_has_no_15m_gaps": True,
            "all_visible_rows_closed_by_decision": True,
            "partial_htf_candles_excluded": True,
            "every_htf_bar_has_exact_15m_lineage": True,
            "future_rows_have_no_authority": True,
        },
        "authority_contract": {
            "market_truth_authority": "canonical_closed_15m_plus_certified_derivation",
            "tradingview_authority": "visual_audit_only",
            "ai_may_modify_ohlcv": False,
            "signal_allowed": False,
            "paper_execution": "disabled",
            "live_execution": "disabled",
        },
    }
    certificate["certificate_sha256"] = object_sha256(certificate)
    return CertifiedMarketTruth(
        certificate=certificate,
        visible_15m=visible,
        timeframe_dfs=frames,
    )


def reconstruct_certified_timeframe(
    visible_15m: pd.DataFrame,
    *,
    timeframe: str,
    decision_time: str | pd.Timestamp,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    if timeframe not in TIMEFRAME_SPEC:
        raise ValueError(f"Unsupported certified timeframe: {timeframe}")
    duration, expected_count, floor_rule = TIMEFRAME_SPEC[timeframe]
    decision = as_utc_naive(decision_time)
    source = validate_canonical_15m(visible_15m)
    bucket_starts = source["timestamp"].dt.floor(floor_rule)
    rows: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    for bucket_start, group in source.groupby(bucket_starts, sort=True):
        bucket_start = pd.Timestamp(bucket_start)
        bucket_close = bucket_start + duration
        expected_timestamps = pd.date_range(
            start=bucket_start,
            periods=expected_count,
            freq="15min",
        )
        actual_timestamps = pd.DatetimeIndex(group["timestamp"])
        complete = (
            bucket_close <= decision
            and len(group) == expected_count
            and actual_timestamps.equals(expected_timestamps)
        )
        if not complete:
            reason = "bucket_not_closed_at_decision"
            if bucket_close <= decision:
                reason = "incomplete_source_rows_for_bucket"
            exclusions.append(
                {
                    "timeframe": timeframe,
                    "bucket_open": _iso(bucket_start),
                    "bucket_close": _iso(bucket_close),
                    "reason": reason,
                    "observed_source_count": int(len(group)),
                    "expected_source_count": expected_count,
                }
            )
            continue

        row = {
            "timestamp": bucket_start,
            "open": float(group["open"].iloc[0]),
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group["close"].iloc[-1]),
            "volume": float(group["volume"].sum()),
        }
        rows.append(row)
        source_hash = dataframe_sha256(group, columns=OHLCV_COLUMNS)
        lineage.append(
            {
                "timeframe": timeframe,
                "bar_open": _iso(bucket_start),
                "bar_close": _iso(bucket_close),
                "source_first_open": _iso(group["timestamp"].iloc[0]),
                "source_last_open": _iso(group["timestamp"].iloc[-1]),
                "source_count": expected_count,
                "source_rows_sha256": source_hash,
                "derived_ohlcv": {
                    key: row[key] for key in ("open", "high", "low", "close", "volume")
                },
            }
        )

    frame = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
    return frame, lineage, exclusions


def assert_future_append_invariant(
    original: CertifiedMarketTruth,
    appended: CertifiedMarketTruth,
) -> None:
    """Prove that rows after T did not change any perception-visible frame."""
    left = original.certificate
    right = appended.certificate
    if left["decision_time"] != right["decision_time"]:
        raise AssertionError("Decision times differ; future-append comparison is invalid.")
    if left["timeframe_hashes"] != right["timeframe_hashes"]:
        raise AssertionError("Future rows changed decision-time-visible timeframe hashes.")
    if left["visible_15m_row_count"] != right["visible_15m_row_count"]:
        raise AssertionError("Future rows changed the visible 15m row count.")


def _normalize_symbol(value: str) -> str:
    return value.upper().replace("/", "").replace("-", "").replace(".P", "")


def _iso(value: Any) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")
