"""Clean-room executable oracle for deterministic chart geometry.

Independence is deliberate: this file must not import ``smc_desk.perception``,
``smc_desk.structure``, ``smc_desk.brain``, or ``smc_desk.decision``. It uses
only closed OHLCV and an explicit configuration passed by the caller.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

import pandas as pd

from smc_desk.data.hashing import dataframe_sha256, object_sha256


TIMEFRAME_DURATIONS = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "12h": pd.Timedelta(hours=12),
    "1d": pd.Timedelta(days=1),
}


@dataclass(frozen=True)
class OracleConfig:
    local_window: int = 1
    internal_window: int = 3
    external_window: int = 5
    fvg_minimum_gap_bps: float = 5.0
    break_minimum_penetration_bps: float = 4.0

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OracleConfig":
        return cls(
            local_window=int(payload.get("local_window", 1)),
            internal_window=int(payload.get("internal_window", 3)),
            external_window=int(payload.get("external_window", 5)),
            fvg_minimum_gap_bps=float(payload.get("fvg_minimum_gap_bps", 5.0)),
            break_minimum_penetration_bps=float(payload.get("break_minimum_penetration_bps", 4.0)),
        )


def run_reference_oracle(
    frame: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    decision_time: str | pd.Timestamp,
    config: OracleConfig | None = None,
    session_profile: str = "continuous",
    include_diagnostics: bool = True,
) -> dict[str, Any]:
    config = config or OracleConfig()
    normalized = _validated_closed_frame(
        frame,
        timeframe=timeframe,
        decision_time=decision_time,
        session_profile=session_profile,
    )
    swings = _detect_swings(normalized, timeframe=timeframe, config=config)
    fvgs = _detect_fvgs(normalized, timeframe=timeframe, config=config)
    interactions = (
        _detect_structural_level_interactions(
            normalized,
            timeframe=timeframe,
            swings=swings,
            config=config,
        )
        if include_diagnostics
        else []
    )
    result = {
        "schema": "smc_clean_room_reference_oracle_v1",
        "oracle_version": "1.0.0",
        "market": market,
        "timeframe": timeframe,
        "decision_time": _iso(pd.Timestamp(decision_time)),
        "config": asdict(config),
        "session_profile": session_profile,
        "diagnostic_contract": {
            "structural_level_interaction_evaluated": include_diagnostics,
            "structural_level_interaction_authority": "NOT_EVALUATED",
        },
        "data_sha256": dataframe_sha256(
            normalized,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        ),
        "claims": {
            "swing": swings,
            "fair_value_gap": fvgs,
            "structural_level_interaction": interactions,
        },
        "claim_counts": {
            "swing": len(swings),
            "fair_value_gap": len(fvgs),
            "structural_level_interaction": len(interactions),
        },
        "authority_contract": {
            "clean_room": True,
            "human_adjudication_used": False,
            "ai_used": False,
            "definition_conformance_only": True,
            "mechanism_authority": False,
            "forecast_authority": False,
            "signal_allowed": False,
        },
    }
    result["oracle_output_sha256"] = object_sha256(result)
    return result


def run_reference_robustness_profiles(
    frame: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    decision_time: str | pd.Timestamp,
    profiles: Mapping[str, Mapping[str, Any]],
    session_profile: str = "continuous",
) -> dict[str, dict[str, Any]]:
    return {
        name: run_reference_oracle(
            frame,
            market=market,
            timeframe=timeframe,
            decision_time=decision_time,
            config=OracleConfig.from_mapping(profile),
            session_profile=session_profile,
            include_diagnostics=False,
        )
        for name, profile in sorted(profiles.items())
    }


def _validated_closed_frame(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    decision_time: str | pd.Timestamp,
    session_profile: str,
) -> pd.DataFrame:
    duration = TIMEFRAME_DURATIONS.get(timeframe)
    if duration is None:
        raise ValueError(f"Unsupported timeframe for clean-room oracle: {timeframe}")
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Reference oracle missing OHLC columns: {missing}")
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    cutoff = pd.Timestamp(decision_time)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    if out["timestamp"].duplicated().any():
        raise ValueError("Reference oracle refuses duplicate candle timestamps.")
    if not out["timestamp"].is_monotonic_increasing:
        raise ValueError("Reference oracle refuses out-of-order candles.")
    out = out.loc[out["timestamp"] + duration <= cutoff].copy()
    if out.empty:
        raise ValueError("Reference oracle has no candles closed by decision time.")
    timestamps = out["timestamp"].tolist()
    for index in range(1, len(timestamps)):
        previous_close = pd.Timestamp(timestamps[index - 1]) + duration
        next_open = pd.Timestamp(timestamps[index])
        if next_open == previous_close:
            continue
        if _expected_session_closure(
            previous_close,
            next_open,
            session_profile=session_profile,
            timeframe=timeframe,
        ):
            continue
        raise ValueError(
            "Reference oracle refuses unexplained candle gap: "
            f"{previous_close.isoformat()} to {next_open.isoformat()}"
        )
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="raise")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out["volume"] = pd.to_numeric(out["volume"], errors="raise")
    invalid = (
        (out["high"] < out[["open", "close", "low"]].max(axis=1))
        | (out["low"] > out[["open", "close", "high"]].min(axis=1))
        | (out["volume"] < 0)
    )
    if invalid.any():
        raise ValueError("Reference oracle refuses impossible OHLCV geometry.")
    return out.reset_index(drop=True)


def _expected_session_closure(
    previous_close: pd.Timestamp,
    next_open: pd.Timestamp,
    *,
    session_profile: str,
    timeframe: str,
) -> bool:
    """Independent bounded session calendar; never excuses mid-week holes."""
    if session_profile != "forex_5d":
        return False
    hours = (next_open - previous_close).total_seconds() / 3600.0
    if timeframe == "1d":
        return -1.5 <= hours <= 120.0
    if not 24.0 <= hours <= 75.0:
        return False
    return previous_close.weekday() in {4, 5} and next_open.weekday() in {6, 0}


def _detect_swings(frame: pd.DataFrame, *, timeframe: str, config: OracleConfig) -> list[dict[str, Any]]:
    duration = TIMEFRAME_DURATIONS[timeframe]
    claims: list[dict[str, Any]] = []
    scales = (
        ("local", config.local_window),
        ("internal", config.internal_window),
        ("external", config.external_window),
    )
    for scope, window in scales:
        if window < 1:
            raise ValueError(f"Swing window must be positive: {scope}={window}")
        for index in range(window, len(frame) - window):
            pivot = frame.iloc[index]
            left = frame.iloc[index - window:index]
            right = frame.iloc[index + 1:index + window + 1]
            is_high = bool((pivot.high > left.high).all() and (pivot.high >= right.high).all())
            is_low = bool((pivot.low < left.low).all() and (pivot.low <= right.low).all())
            confirmed = frame.iloc[index + window].timestamp + duration
            base = {
                "label_family": "swing",
                "timeframe": timeframe,
                "scope": scope,
                "pivot_time": _iso(pivot.timestamp),
                "candidate_at": _iso(pivot.timestamp + duration),
                "confirmed_at": _iso(confirmed),
                "price_low": _number(pivot.low),
                "price_high": _number(pivot.high),
                "reference_time": "",
                "reference_price": "",
                "state": "CONFIRMED",
                "predicates": {
                    "strict_left": True,
                    "equal_right_allowed": True,
                    "first_equal_extreme_owns_pivot": True,
                    "confirmation_window": window,
                },
                "source_row_indices": list(range(index - window, index + window + 1)),
            }
            if is_low:
                claims.append({**base, "direction": "bullish"})
            if is_high:
                claims.append({**base, "direction": "bearish"})
    return _sort_claims(claims)


def _detect_fvgs(frame: pd.DataFrame, *, timeframe: str, config: OracleConfig) -> list[dict[str, Any]]:
    duration = TIMEFRAME_DURATIONS[timeframe]
    claims: list[dict[str, Any]] = []
    for index in range(1, len(frame) - 1):
        first = frame.iloc[index - 1]
        middle = frame.iloc[index]
        third = frame.iloc[index + 1]
        bullish = first.high < third.low
        bearish = first.low > third.high
        if not bullish and not bearish:
            continue
        direction = "bullish" if bullish else "bearish"
        lower = first.high if bullish else third.high
        upper = third.low if bullish else first.low
        gap_bps = float((Decimal(str(upper)) - Decimal(str(lower))) / Decimal(str(middle.close)) * Decimal("10000"))
        qualified = gap_bps >= config.fvg_minimum_gap_bps
        claims.append(
            {
                "label_family": "fair_value_gap",
                "timeframe": timeframe,
                "scope": "",
                "direction": direction,
                "pivot_time": _iso(middle.timestamp),
                "candidate_at": _iso(third.timestamp),
                "confirmed_at": _iso(third.timestamp + duration),
                "price_low": _number(lower),
                "price_high": _number(upper),
                "reference_time": "",
                "reference_price": "",
                "state": "QUALIFIED" if qualified else "RAW_UNQUALIFIED",
                "predicates": {
                    "three_candle_non_overlap": True,
                    "gap_size_bps": round(gap_bps, 8),
                    "minimum_gap_bps": config.fvg_minimum_gap_bps,
                },
                "source_row_indices": [index - 1, index, index + 1],
            }
        )
    return _sort_claims(claims)


def _detect_structural_level_interactions(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    swings: Sequence[Mapping[str, Any]],
    config: OracleConfig,
) -> list[dict[str, Any]]:
    """Record the first point-in-time interaction with each confirmed swing.

    This intentionally does not call the event BOS/CHoCH/MSS. Those labels need
    the still-contested protected-point and scope-ownership doctrine.
    """
    duration = TIMEFRAME_DURATIONS[timeframe]
    claims: list[dict[str, Any]] = []
    timestamp_to_index = { _iso(row.timestamp): index for index, row in frame.iterrows() }
    for swing in swings:
        confirmed_at = pd.Timestamp(str(swing["confirmed_at"]))
        direction = str(swing["direction"])
        level = Decimal(str(swing["price_high"] if direction == "bearish" else swing["price_low"]))
        pivot_index = timestamp_to_index.get(str(swing["pivot_time"]))
        if pivot_index is None:
            continue
        for index in range(pivot_index + 1, len(frame)):
            candle = frame.iloc[index]
            if candle.timestamp + duration < confirmed_at:
                continue
            candle_open = Decimal(str(candle.open))
            candle_high = Decimal(str(candle.high))
            candle_low = Decimal(str(candle.low))
            candle_close = Decimal(str(candle.close))
            break_direction = "bullish" if direction == "bearish" else "bearish"
            approached = candle_open <= level if break_direction == "bullish" else candle_open >= level
            crossed = candle_high > level if break_direction == "bullish" else candle_low < level
            if not approached or not crossed:
                continue
            penetration = candle_high - level if break_direction == "bullish" else level - candle_low
            minimum = abs(level) * Decimal(str(config.break_minimum_penetration_bps)) / Decimal("10000")
            if penetration < minimum:
                continue
            body_closed = candle_close > level if break_direction == "bullish" else candle_close < level
            claims.append(
                {
                    "label_family": "structural_level_interaction",
                    "timeframe": timeframe,
                    "scope": str(swing["scope"]),
                    "direction": break_direction,
                    "pivot_time": str(swing["pivot_time"]),
                    "candidate_at": _iso(candle.timestamp),
                    "confirmed_at": _iso(candle.timestamp + duration) if body_closed else "",
                    "price_low": _number(candle.low),
                    "price_high": _number(candle.high),
                    "reference_time": str(swing["pivot_time"]),
                    "reference_price": _number(level),
                    "state": "BODY_CLOSE_CONFIRMED" if body_closed else "WICK_PROBE",
                    "predicates": {
                        "target_available": True,
                        "approached_from_protected_side": True,
                        "minimum_penetration_bps": config.break_minimum_penetration_bps,
                        "body_closed_beyond": body_closed,
                    },
                    "source_row_indices": [index],
                }
            )
            break
    return _sort_claims(claims)


def _sort_claims(claims: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in sorted(
            claims,
            key=lambda item: (
                str(item.get("label_family")),
                str(item.get("scope")),
                str(item.get("pivot_time")),
                str(item.get("direction")),
                str(item.get("state")),
            ),
        )
    ]


def _number(value: Any) -> str:
    decimal = Decimal(str(value))
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _iso(value: Any) -> str:
    timestamp = pd.Timestamp(value)
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")


__all__ = [
    "OracleConfig",
    "run_reference_oracle",
    "run_reference_robustness_profiles",
]
