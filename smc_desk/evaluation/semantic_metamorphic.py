"""Deterministic OHLCV metamorphic transformations for SMC evaluation.

Presentation perturbations test visual robustness.  These transformations test
semantic robustness by changing market data in controlled, auditable ways.
Every result carries an exact mutation contract; no transformation supplies the
expected SMC answer, which remains independently adjudicated.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


PRICE_COLUMNS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class SweepCandidate:
    index: int
    direction: str
    level: float
    lookback: int


def vertical_mirror(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = _validated(frame)
    axis = (float(work["high"].max()) + float(work["low"].min())) / 2.0
    result = work.copy()
    result["open"] = 2.0 * axis - work["open"]
    result["close"] = 2.0 * axis - work["close"]
    result["high"] = 2.0 * axis - work["low"]
    result["low"] = 2.0 * axis - work["high"]
    contract = _contract(
        "vertical_mirror",
        work,
        result,
        parameters={"axis": axis},
        expected_invariants=[
            "timestamps_and_volume_unchanged",
            "event_order_unchanged",
            "bullish_and_bearish_semantics_swap",
            "high_low_and_premium_discount_semantics_swap",
        ],
        expected_changes=["all_ohlc_prices", "directional_semantics"],
    )
    return result, contract


def decimal_rescale(frame: pd.DataFrame, factor: float = 0.0001) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError("factor must be finite and positive")
    work = _validated(frame)
    result = work.copy()
    result.loc[:, list(PRICE_COLUMNS)] = work.loc[:, list(PRICE_COLUMNS)] * float(factor)
    contract = _contract(
        "decimal_rescale",
        work,
        result,
        parameters={"factor": float(factor)},
        expected_invariants=[
            "timestamps_volume_and_event_order_unchanged",
            "direction_scope_lifecycle_and_object_count_unchanged",
            "all_price_coordinates_scale_by_factor",
        ],
        expected_changes=["ohlc_price_magnitude_only"],
    )
    return result, contract


def one_candle_rollback(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = _validated(frame)
    if len(work) < 2:
        raise ValueError("at least two candles are required")
    result = work.iloc[:-1].reset_index(drop=True)
    removed = work.iloc[-1]
    contract = _contract(
        "one_candle_rollback",
        work,
        result,
        parameters={
            "removed_index": len(work) - 1,
            "removed_timestamp": _iso(removed["timestamp"]),
        },
        expected_invariants=["all_prior_candles_unchanged", "no_retroactive_relabeling"],
        expected_changes=["claims_first_knowable_on_removed_candle_must_downgrade_or_disappear"],
    )
    return result, contract


def truncate_origin_history(frame: pd.DataFrame, keep_bars: int = 60) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = _validated(frame)
    if keep_bars < 20 or keep_bars >= len(work):
        raise ValueError("keep_bars must retain at least 20 candles and remove history")
    removed_count = len(work) - keep_bars
    result = work.tail(keep_bars).reset_index(drop=True)
    contract = _contract(
        "origin_history_truncation",
        work,
        result,
        parameters={
            "removed_candle_count": removed_count,
            "first_visible_timestamp": _iso(result.iloc[0]["timestamp"]),
        },
        expected_invariants=["retained_candles_unchanged", "latest_decision_candle_unchanged"],
        expected_changes=[
            "origins_before_first_visible_timestamp_become_unobservable",
            "system_must_abstain_from_unseen_origin_claims",
        ],
    )
    return result, contract


def find_sweep_candidate(frame: pd.DataFrame, *, lookback: int = 12) -> SweepCandidate | None:
    work = _validated(frame)
    if lookback < 3 or len(work) <= lookback:
        return None
    for index in range(len(work) - 1, lookback - 1, -1):
        prior = work.iloc[index - lookback:index]
        row = work.iloc[index]
        prior_high = float(prior["high"].max())
        prior_low = float(prior["low"].min())
        body_high = max(float(row["open"]), float(row["close"]))
        body_low = min(float(row["open"]), float(row["close"]))
        if float(row["high"]) > prior_high and body_high <= prior_high:
            return SweepCandidate(index=index, direction="buyside", level=prior_high, lookback=lookback)
        if float(row["low"]) < prior_low and body_low >= prior_low:
            return SweepCandidate(index=index, direction="sellside", level=prior_low, lookback=lookback)
    return None


def remove_sweep_wick(
    frame: pd.DataFrame, candidate: SweepCandidate | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = _validated(frame)
    selected = candidate or find_sweep_candidate(work)
    if selected is None:
        raise ValueError("no wick-only sweep candidate is available")
    if not 0 <= selected.index < len(work):
        raise ValueError("sweep index is outside the frame")
    result = work.copy()
    row = work.iloc[selected.index]
    epsilon = max(abs(selected.level) * 1e-10, 1e-12)
    if selected.direction == "buyside":
        if max(float(row["open"]), float(row["close"])) > selected.level:
            raise ValueError("buyside candidate body is already accepted beyond the level")
        original = float(row["high"])
        mutated = max(float(row["open"]), float(row["close"]), selected.level - epsilon)
        result.at[selected.index, "high"] = mutated
        field = "high"
    elif selected.direction == "sellside":
        if min(float(row["open"]), float(row["close"])) < selected.level:
            raise ValueError("sellside candidate body is already accepted beyond the level")
        original = float(row["low"])
        mutated = min(float(row["open"]), float(row["close"]), selected.level + epsilon)
        result.at[selected.index, "low"] = mutated
        field = "low"
    else:
        raise ValueError("sweep direction must be buyside or sellside")
    contract = _contract(
        "sweep_wick_removal_twin",
        work,
        result,
        parameters={
            "candle_index": selected.index,
            "timestamp": _iso(row["timestamp"]),
            "direction": selected.direction,
            "level": selected.level,
            "changed_field": field,
            "original_value": original,
            "mutated_value": mutated,
            "lookback": selected.lookback,
        },
        expected_invariants=[
            "exactly_one_ohlc_field_changed",
            "all_non_sweep_dependent_claims_remain_equal",
        ],
        expected_changes=[
            "sweep_claim_removed",
            "sweep_dependent_break_quality_and_poi_causality_may_downgrade",
        ],
    )
    return result, contract


def inject_flash_wick(
    frame: pd.DataFrame, *, index: int | None = None, direction: str = "buyside", magnitude: float = 8.0
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = _validated(frame)
    chosen = len(work) - 2 if index is None else int(index)
    if not 0 <= chosen < len(work):
        raise ValueError("flash-wick index is outside the frame")
    if not np.isfinite(magnitude) or magnitude <= 1.0:
        raise ValueError("magnitude must be finite and greater than one")
    ranges = (work["high"] - work["low"]).replace(0.0, np.nan).dropna()
    typical_range = float(ranges.median()) if not ranges.empty else max(abs(float(work.iloc[chosen]["close"])) * 0.001, 1e-9)
    result = work.copy()
    row = work.iloc[chosen]
    if direction == "buyside":
        field = "high"
        original = float(row["high"])
        mutated = max(original, max(float(row["open"]), float(row["close"])) + typical_range * magnitude)
        result.at[chosen, field] = mutated
    elif direction == "sellside":
        field = "low"
        original = float(row["low"])
        mutated = min(original, min(float(row["open"]), float(row["close"])) - typical_range * magnitude)
        result.at[chosen, field] = mutated
    else:
        raise ValueError("direction must be buyside or sellside")
    contract = _contract(
        "flash_wick_injection",
        work,
        result,
        parameters={
            "candle_index": chosen,
            "timestamp": _iso(row["timestamp"]),
            "direction": direction,
            "changed_field": field,
            "original_value": original,
            "mutated_value": mutated,
            "typical_range": typical_range,
            "magnitude": float(magnitude),
        },
        expected_invariants=[
            "exactly_one_ohlc_field_changed",
            "candle_body_and_close_unchanged",
            "no_confirmed_bos_from_wick_alone",
        ],
        expected_changes=["wick_probe_or_anomaly_evidence_only"],
    )
    return result, contract


def build_semantic_metamorphic_frames(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    work = _validated(frame)
    variants: dict[str, dict[str, Any]] = {}
    builders = {
        "vertical_mirror": lambda: vertical_mirror(work),
        "decimal_rescale": lambda: decimal_rescale(work),
        "one_candle_rollback": lambda: one_candle_rollback(work),
        "origin_history_truncation": lambda: truncate_origin_history(work, keep_bars=max(20, min(60, len(work) - 1))),
        "flash_wick_injection": lambda: inject_flash_wick(work),
    }
    for name, builder in builders.items():
        transformed, contract = builder()
        variants[name] = {"frame": transformed, "contract": contract}
    candidate = find_sweep_candidate(work)
    if candidate is None:
        variants["sweep_wick_removal_twin"] = {
            "frame": None,
            "contract": {
                "schema": "smc_semantic_metamorphic_contract_v1",
                "transformation": "sweep_wick_removal_twin",
                "status": "NOT_APPLICABLE_NO_WICK_ONLY_SWEEP_IN_WINDOW",
                "source_sha256": _frame_hash(work),
                "authority_contract": {"expected_answer_supplied": False, "signal_allowed": False},
            },
        }
    else:
        transformed, contract = remove_sweep_wick(work, candidate)
        variants["sweep_wick_removal_twin"] = {"frame": transformed, "contract": contract}
    return variants


def verify_transformation(source: pd.DataFrame, transformed: pd.DataFrame, contract: Mapping[str, Any]) -> list[str]:
    base = _validated(source)
    result = _validated(transformed)
    issues: list[str] = []
    if contract.get("source_sha256") != _frame_hash(base):
        issues.append("source_hash_mismatch")
    if contract.get("result_sha256") != _frame_hash(result):
        issues.append("result_hash_mismatch")
    transformation = str(contract.get("transformation") or "")
    parameters = contract.get("parameters") if isinstance(contract.get("parameters"), Mapping) else {}
    if transformation in {"sweep_wick_removal_twin", "flash_wick_injection"}:
        changed = _cell_differences(base, result)
        expected = (int(parameters.get("candle_index", -1)), str(parameters.get("changed_field") or ""))
        if changed != [expected]:
            issues.append("single_field_mutation_contract_failed")
    elif transformation == "one_candle_rollback":
        if len(result) != len(base) - 1 or _frame_hash(result) != _frame_hash(base.iloc[:-1].reset_index(drop=True)):
            issues.append("rollback_contract_failed")
    elif transformation == "origin_history_truncation":
        if result.empty or _frame_hash(result) != _frame_hash(base.tail(len(result)).reset_index(drop=True)):
            issues.append("truncation_contract_failed")
    elif transformation == "decimal_rescale":
        factor = float(parameters.get("factor") or 0.0)
        if not np.allclose(result[list(PRICE_COLUMNS)], base[list(PRICE_COLUMNS)] * factor):
            issues.append("rescale_contract_failed")
    elif transformation == "vertical_mirror":
        axis = float(parameters.get("axis"))
        if not np.allclose(result["open"], 2 * axis - base["open"]):
            issues.append("mirror_open_contract_failed")
        if not np.allclose(result["high"], 2 * axis - base["low"]):
            issues.append("mirror_high_low_contract_failed")
    return issues


def _validated(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"OHLCV missing required columns: {missing}")
    work = frame.copy().reset_index(drop=True)
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    for column in (*PRICE_COLUMNS, "volume"):
        work[column] = pd.to_numeric(work[column], errors="raise")
    if work.empty:
        raise ValueError("OHLCV frame is empty")
    if not work["timestamp"].is_monotonic_increasing or work["timestamp"].duplicated().any():
        raise ValueError("timestamps must be unique and monotonic")
    if (work["high"] < work[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("invalid OHLC high")
    if (work["low"] > work[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("invalid OHLC low")
    return work


def _contract(
    name: str,
    source: pd.DataFrame,
    result: pd.DataFrame,
    *,
    parameters: Mapping[str, Any],
    expected_invariants: list[str],
    expected_changes: list[str],
) -> dict[str, Any]:
    return {
        "schema": "smc_semantic_metamorphic_contract_v1",
        "transformation": name,
        "status": "READY_FOR_BLIND_RESPONSE",
        "parameters": dict(parameters),
        "source_sha256": _frame_hash(source),
        "result_sha256": _frame_hash(result),
        "expected_invariants": expected_invariants,
        "expected_changes": expected_changes,
        "authority_contract": {
            "expected_answer_supplied": False,
            "independent_adjudication_required": True,
            "signal_allowed": False,
        },
    }


def _cell_differences(left: pd.DataFrame, right: pd.DataFrame) -> list[tuple[int, str]]:
    if len(left) != len(right):
        return [(-1, "row_count")]
    differences: list[tuple[int, str]] = []
    for index in range(len(left)):
        for column in PRICE_COLUMNS:
            if not np.isclose(float(left.at[index, column]), float(right.at[index, column]), rtol=0.0, atol=0.0):
                differences.append((index, column))
    return differences


def _frame_hash(frame: pd.DataFrame) -> str:
    work = frame.reset_index(drop=True)
    rows = [
        {
            "timestamp": _iso(row["timestamp"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in work.iterrows()
    ]
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


__all__ = [
    "SweepCandidate",
    "build_semantic_metamorphic_frames",
    "decimal_rescale",
    "find_sweep_candidate",
    "inject_flash_wick",
    "one_candle_rollback",
    "remove_sweep_wick",
    "truncate_origin_history",
    "vertical_mirror",
    "verify_transformation",
]
