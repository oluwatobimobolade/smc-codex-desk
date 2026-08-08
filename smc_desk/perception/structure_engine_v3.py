"""Observe-only Structure Engine V3 shadow adapter.

The canonical V2 detector remains the candidate generator. This module replays
each V2 structure candidate from the moment its broken swing became available
and applies the stricter break lifecycle from the proposed Constitution V2.

The adapter has one-way authority: it may challenge or downgrade V2 structure,
but it cannot create a signal, trade plan, or live execution authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from smc_desk.perception.experimental_break_engine import (
    BreakLevel,
    BreakLifecycleConfig,
    ExperimentalBreakLifecycleEngine,
)


TIMEFRAME_DELTAS = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "12h": pd.Timedelta(hours=12),
    "1d": pd.Timedelta(days=1),
}

ACCEPTED_EVENT_PREFIXES = (
    "INITIAL_DIRECTION_BREAK",
    "INTERNAL_BOS_",
    "EXTERNAL_BOS_",
    "INTERNAL_CHOCH_",
    "EXTERNAL_MSS_CONFIRMED_",
)


@dataclass(frozen=True)
class StructureEngineV3ShadowResult:
    symbol: str
    decision_time: str
    timeframes: Mapping[str, Any]
    schema: str = "structure_engine_v3_shadow_v1"
    engine: str = "StructureEngineV3Shadow"
    runtime_classification: str = "observe_only_downgrade_authority"
    canonical_candidate_source: str = "PerceptionEngineV2"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "authority_contract": {
                "canonical_candidate_source": self.canonical_candidate_source,
                "can_challenge_canonical_structure": True,
                "can_promote_trade_state": False,
                "signal_allowed": False,
                "paper_execution_allowed": False,
                "live_execution_allowed": False,
            },
        }


class StructureEngineV3Shadow:
    """Replay canonical candidates with strict, causal break semantics."""

    def analyze(
        self,
        *,
        symbol: str,
        detector_candidates: Mapping[str, Any],
        timeframe_dfs: Mapping[str, pd.DataFrame],
        decision_time: str | datetime | None = None,
    ) -> StructureEngineV3ShadowResult:
        cutoff = _decision_time(timeframe_dfs, decision_time)
        timeframe_results: dict[str, Any] = {}
        for timeframe, raw_payload in detector_candidates.items():
            df = timeframe_dfs.get(timeframe)
            if df is None or df.empty or timeframe not in TIMEFRAME_DELTAS:
                continue
            payload = _mapping(raw_payload)
            timeframe_results[timeframe] = self._analyze_timeframe(
                timeframe=timeframe,
                payload=payload,
                df=df,
                decision_time=cutoff,
            )
        return StructureEngineV3ShadowResult(
            symbol=symbol,
            decision_time=cutoff.isoformat().replace("+00:00", "Z"),
            timeframes=timeframe_results,
        )

    def _analyze_timeframe(
        self,
        *,
        timeframe: str,
        payload: Mapping[str, Any],
        df: pd.DataFrame,
        decision_time: pd.Timestamp,
    ) -> dict[str, Any]:
        candles, atr_by_close_time = _closed_candles_and_atr(df, timeframe)
        swings = {
            str(item.get("object_id")): item
            for raw in payload.get("swings", []) or []
            if isinstance((item := _mapping(raw)), Mapping) and item.get("object_id")
        }
        breaks = sorted(
            (
                _mapping(item)
                for item in payload.get("structure_breaks", []) or []
                if isinstance(item, Mapping) or hasattr(item, "model_dump")
            ),
            key=lambda item: _timestamp(item.get("candidate_at") or item.get("confirmed_at") or decision_time),
        )
        prior_direction: dict[str, str | None] = {"external": None, "internal": None}
        events: list[dict[str, Any]] = []
        config = _config_for_timeframe(timeframe)
        engine = ExperimentalBreakLifecycleEngine(config)

        for candidate in breaks:
            evidence = _mapping(candidate.get("evidence") or {})
            direction = _direction(candidate.get("direction"))
            scope = str(candidate.get("structure_scope") or evidence.get("structure_scope") or "external").lower()
            broken_swing_id = str(evidence.get("broken_swing_id") or "")
            level_price = _float(evidence.get("broken_price"))
            if direction is None or scope not in {"internal", "external"} or not broken_swing_id or level_price is None:
                events.append(_unresolved_event(candidate, "missing_break_level_identity"))
                continue
            swing = swings.get(broken_swing_id)
            if not isinstance(swing, Mapping):
                events.append(_unresolved_event(candidate, "broken_swing_not_found"))
                continue
            available_at_raw = swing.get("confirmed_at") or swing.get("candidate_at") or swing.get("pivot_time")
            if available_at_raw is None:
                events.append(_unresolved_event(candidate, "broken_swing_has_no_availability_time"))
                continue
            available_at = _timestamp(available_at_raw)
            visible_candles = [
                candle
                for candle in candles
                if _timestamp(candle["close_time"]) >= available_at
                and _timestamp(candle["close_time"]) <= decision_time
            ]
            if not visible_candles:
                events.append(_unresolved_event(candidate, "no_closed_candles_after_swing_confirmation"))
                continue
            candidate_time = _timestamp(candidate.get("confirmed_at") or candidate.get("candidate_at") or available_at)
            atr = _atr_at_or_before(atr_by_close_time, candidate_time)
            if atr is None or atr <= 0:
                events.append(_unresolved_event(candidate, "atr_unavailable_at_break_candidate"))
                continue
            lifecycle = engine.classify(
                level=BreakLevel(
                    level_id=broken_swing_id,
                    price=level_price,
                    break_direction=direction,
                    scope=scope,  # type: ignore[arg-type]
                    prior_direction=prior_direction[scope],  # type: ignore[arg-type]
                    invalidates_parent_narrative=bool(
                        scope == "external" and evidence.get("broke_protected_swing")
                    ),
                ),
                candles=visible_candles,
                atr=atr,
                decision_time=decision_time.to_pydatetime(),
            )
            event = lifecycle.to_dict()
            event.update(
                {
                    "source_break_object_id": str(candidate.get("object_id") or ""),
                    "source_break_type": str(candidate.get("break_type") or ""),
                    "source_confirmation_status": str(candidate.get("confirmation_status") or ""),
                    "broken_swing_id": broken_swing_id,
                    "broken_level_price": level_price,
                    "level_available_at": available_at.isoformat().replace("+00:00", "Z"),
                    "timeframe": timeframe,
                    "atr_at_candidate": atr,
                    "accepted_for_shadow_story": _is_accepted_event(event.get("event_type")),
                }
            )
            events.append(event)
            if event["accepted_for_shadow_story"]:
                prior_direction[scope] = direction

        accepted = [event for event in events if event.get("accepted_for_shadow_story")]
        challenged = [
            event
            for event in events
            if event.get("source_confirmation_status") == "confirmed"
            and not event.get("accepted_for_shadow_story")
        ]
        return {
            "timeframe": timeframe,
            "config": asdict(config),
            "events": events,
            "accepted_event_ids": [event.get("source_break_object_id") for event in accepted],
            "challenged_canonical_break_ids": [event.get("source_break_object_id") for event in challenged],
            "latest_accepted_external": _latest_event(accepted, "external"),
            "latest_accepted_internal": _latest_event(accepted, "internal"),
            "counts": {
                "candidate_breaks": len(events),
                "accepted": len(accepted),
                "challenged": len(challenged),
                "wick_probes": sum(event.get("event_type") == "WICK_PROBE" for event in events),
                "expired_wick_probes": sum(event.get("event_type") == "EXPIRED_WICK_PROBE" for event in events),
                "failed_breakouts": sum(event.get("event_type") == "FAILED_BREAKOUT" for event in events),
            },
        }


def _config_for_timeframe(timeframe: str) -> BreakLifecycleConfig:
    # Pre-registered shadow defaults. They are scale-normalized and may not be
    # tuned against the locked validation cohort.
    thresholds = {
        "5m": (0.06, 4.0, 0.50),
        "15m": (0.08, 4.0, 0.52),
        "1h": (0.10, 6.0, 0.55),
        "4h": (0.12, 8.0, 0.58),
        "12h": (0.14, 9.0, 0.60),
        "1d": (0.15, 10.0, 0.60),
    }
    penetration_atr, penetration_bps, body_ratio = thresholds.get(timeframe, thresholds["1h"])
    return BreakLifecycleConfig(
        minimum_penetration_atr=penetration_atr,
        minimum_body_to_range_ratio=body_ratio,
        minimum_close_beyond_structure_bps=penetration_bps,
        minimum_displacement_score=0.62,
        early_confirmation_bars=2,
        final_confirmation_bars=6,
        wick_probe_timeout_bars=6,
    )


def _closed_candles_and_atr(
    df: pd.DataFrame, timeframe: str
) -> tuple[list[dict[str, Any]], pd.Series]:
    normalized = df.copy()
    if "timestamp" not in normalized.columns:
        normalized = normalized.reset_index().rename(columns={"index": "timestamp"})
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized = normalized.sort_values("timestamp").reset_index(drop=True)
    close_times = normalized["timestamp"] + TIMEFRAME_DELTAS[timeframe]
    previous_close = normalized["close"].shift(1)
    true_range = pd.concat(
        [
            normalized["high"] - normalized["low"],
            (normalized["high"] - previous_close).abs(),
            (normalized["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14, min_periods=5).mean()
    atr.index = close_times
    candles = [
        {
            "timestamp": row.timestamp.isoformat(),
            "close_time": close_time.isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(getattr(row, "volume", 0.0) or 0.0),
        }
        for row, close_time in zip(normalized.itertuples(index=False), close_times, strict=True)
    ]
    return candles, atr.dropna()


def _atr_at_or_before(series: pd.Series, timestamp: pd.Timestamp) -> float | None:
    visible = series[series.index <= timestamp]
    if visible.empty:
        return None
    value = float(visible.iloc[-1])
    return value if pd.notna(value) else None


def _latest_event(events: Sequence[Mapping[str, Any]], scope: str) -> dict[str, Any] | None:
    candidates = [event for event in events if event.get("scope") == scope]
    if not candidates:
        return None
    return dict(max(candidates, key=lambda event: _timestamp(event.get("confirmation_time") or event.get("body_close_time"))))


def _is_accepted_event(event_type: Any) -> bool:
    token = str(event_type or "")
    return token == "INITIAL_DIRECTION_BREAK" or token.startswith(ACCEPTED_EVENT_PREFIXES[1:])


def _unresolved_event(candidate: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "schema": "experimental_break_lifecycle_v1",
        "event_type": "UNRESOLVED",
        "lifecycle_state": "UNRESOLVED",
        "source_break_object_id": str(candidate.get("object_id") or ""),
        "source_break_type": str(candidate.get("break_type") or ""),
        "source_confirmation_status": str(candidate.get("confirmation_status") or ""),
        "accepted_for_shadow_story": False,
        "reasons": [reason],
        "authority_contract": {
            "canonical": False,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return dict(value) if isinstance(value, Mapping) else {}


def _direction(value: Any) -> str | None:
    token = getattr(value, "value", value)
    token = str(token or "").lower()
    return token if token in {"bullish", "bearish"} else None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _decision_time(
    timeframe_dfs: Mapping[str, pd.DataFrame], value: str | datetime | None
) -> pd.Timestamp:
    if value is not None:
        return _timestamp(value)
    close_times: list[pd.Timestamp] = []
    for timeframe, df in timeframe_dfs.items():
        if timeframe not in TIMEFRAME_DELTAS or df.empty:
            continue
        timestamp = _timestamp(df["timestamp"].iloc[-1] if "timestamp" in df.columns else df.index[-1])
        close_times.append(timestamp + TIMEFRAME_DELTAS[timeframe])
    if not close_times:
        raise ValueError("Cannot derive Structure Engine V3 decision time from empty timeframe data.")
    return max(close_times)


__all__ = [
    "StructureEngineV3Shadow",
    "StructureEngineV3ShadowResult",
]
