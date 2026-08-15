"""Adapt canonical PerceptionEngineV2 objects to autonomous claim signatures.

This is intentionally separate from the clean-room oracle. It may import the
production detector; the reference oracle may not import this module.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

import pandas as pd

from smc_desk.data.schemas import Candle
from smc_desk.perception.config import load_perception_config
from smc_desk.perception.engine_v2 import PerceptionEngineV2


_DURATIONS = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "12h": pd.Timedelta(hours=12),
    "1d": pd.Timedelta(days=1),
}


def run_production_claim_adapter(
    frame: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    decision_time: str | pd.Timestamp,
    session_profile: str = "continuous",
) -> dict[str, Any]:
    candles = _candles(
        frame,
        market=market,
        timeframe=timeframe,
        session_profile=session_profile,
    )
    cutoff = _timestamp(decision_time).to_pydatetime()
    snapshot = PerceptionEngineV2(
        expected_instrument=market,
        expected_timeframe=timeframe,
        config=load_perception_config(),
    ).analyze(candles, cutoff)

    swings = []
    swing_index: dict[str, Mapping[str, Any]] = {}
    for scope, objects in snapshot.swings.items():
        for obj in objects:
            payload = obj.model_dump(mode="python")
            swing_index[obj.object_id] = payload
            swings.append(
                {
                    "label_family": "swing",
                    "timeframe": obj.timeframe,
                    "scope": scope,
                    "direction": _value(obj.direction),
                    "pivot_time": _iso(obj.pivot_time),
                    "candidate_at": _iso(obj.candidate_at),
                    "confirmed_at": _iso(obj.confirmed_at),
                    "price_low": _number(obj.price_low),
                    "price_high": _number(obj.price_high),
                    "reference_time": "",
                    "reference_price": "",
                    "state": "CONFIRMED",
                    "production_object_id": obj.object_id,
                }
            )

    fvgs = []
    for obj in snapshot.fvgs:
        qualified = bool(obj.metadata.get("is_qualified", True))
        fvgs.append(
            {
                "label_family": "fair_value_gap",
                "timeframe": obj.timeframe,
                "scope": "",
                "direction": _value(obj.direction),
                "pivot_time": _iso(obj.pivot_time),
                "candidate_at": _iso(obj.candidate_at),
                "confirmed_at": _iso(obj.confirmed_at),
                "price_low": _number(obj.price_low),
                "price_high": _number(obj.price_high),
                "reference_time": "",
                "reference_price": "",
                "state": "QUALIFIED" if qualified else "RAW_UNQUALIFIED",
                "production_object_id": obj.object_id,
            }
        )

    interactions = []
    for obj in snapshot.structure_breaks:
        broken = swing_index.get(obj.evidence.broken_swing_id) or {}
        interactions.append(
            {
                "label_family": "structural_level_interaction",
                "timeframe": obj.timeframe,
                "scope": str(obj.structure_scope),
                "direction": _value(obj.direction),
                "pivot_time": _iso(obj.pivot_time),
                "candidate_at": _iso(obj.candidate_at),
                "confirmed_at": _iso(obj.confirmed_at) if obj.confirmed_at else "",
                "price_low": _number(obj.price_low),
                "price_high": _number(obj.price_high),
                "reference_time": _iso(broken.get("pivot_time")) if broken.get("pivot_time") else _iso(obj.pivot_time),
                "reference_price": _number(obj.evidence.broken_price),
                "state": "WICK_PROBE" if obj.evidence.is_unconfirmed_probe else "BODY_CLOSE_CONFIRMED",
                "production_object_id": obj.object_id,
            }
        )

    return {
        "schema": "smc_production_claim_adapter_v1",
        "production_engine": "PerceptionEngineV2",
        "market": market,
        "timeframe": timeframe,
        "decision_time": _iso(cutoff),
        "session_profile": session_profile,
        "claims": {
            "swing": _sort(swings),
            "fair_value_gap": _sort(fvgs),
            "structural_level_interaction": _sort(interactions),
        },
        "authority_contract": {
            "production_claims_are_self_certifying": False,
            "signal_allowed": False,
        },
    }


def _candles(
    frame: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    session_profile: str,
) -> list[Candle]:
    duration = _DURATIONS.get(timeframe)
    if duration is None:
        raise ValueError(f"Unsupported production adapter timeframe: {timeframe}")
    work = frame.copy()
    if "timestamp" not in work.columns:
        raise ValueError("Production claim adapter requires timestamp column.")
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    if "volume" not in work.columns:
        work["volume"] = 0.0
    result: list[Candle] = []
    previous_close: pd.Timestamp | None = None
    for row in work.itertuples(index=False):
        timestamp = _timestamp(getattr(row, "timestamp"))
        contains_gap = False
        if previous_close is not None and timestamp != previous_close:
            contains_gap = not _expected_session_closure(
                previous_close,
                timestamp,
                session_profile=session_profile,
                timeframe=timeframe,
            )
        result.append(
            Candle(
                venue=market.split(":", 1)[0] if ":" in market else "autonomous_conformance",
                instrument=market,
                timeframe=timeframe,
                open_time=timestamp.to_pydatetime(),
                close_time=(timestamp + duration).to_pydatetime(),
                open=Decimal(str(getattr(row, "open"))),
                high=Decimal(str(getattr(row, "high"))),
                low=Decimal(str(getattr(row, "low"))),
                close=Decimal(str(getattr(row, "close"))),
                volume=Decimal(str(getattr(row, "volume"))),
                trade_count=int(getattr(row, "trade_count", 0) or 0),
                is_closed=True,
                is_complete=True,
                contains_gap=contains_gap,
            )
        )
        previous_close = timestamp + duration
    return result


def _expected_session_closure(
    previous_close: pd.Timestamp,
    next_open: pd.Timestamp,
    *,
    session_profile: str,
    timeframe: str,
) -> bool:
    if session_profile != "forex_5d":
        return False
    hours = (next_open - previous_close).total_seconds() / 3600.0
    if timeframe == "1d":
        return -1.5 <= hours <= 120.0
    return (
        24.0 <= hours <= 75.0
        and previous_close.weekday() in {4, 5}
        and next_open.weekday() in {6, 0}
    )


def _sort(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item["label_family"], item["scope"], item["pivot_time"],
            item["direction"], item["state"],
        ),
    )


def _value(value: Any) -> str:
    return str(getattr(value, "value", value)).lower()


def _number(value: Any) -> str:
    decimal = Decimal(str(value))
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _iso(value: datetime | pd.Timestamp | Any) -> str:
    return _timestamp(value).isoformat().replace("+00:00", "Z")


__all__ = ["run_production_claim_adapter"]
