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
        pending_parent_invalidation: dict[str, Any] | None = None
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
            source_confirmed_at = candidate.get("confirmed_at")
            body_close_time = event.get("body_close_time")
            source_binding_matches = bool(
                source_confirmed_at is not None
                and body_close_time is not None
                and _timestamp(source_confirmed_at) == _timestamp(body_close_time)
            )
            # The shadow must replay the source candidate, not merely find an
            # arbitrary earlier interaction with the same swing level.  A
            # source-confirmed object can inherit V3 acceptance only when the
            # replayed body-close belongs to that exact candidate.
            if (
                str(candidate.get("confirmation_status") or "") == "confirmed"
                and not source_binding_matches
            ):
                event["event_type"] = "SOURCE_BINDING_MISMATCH"
                event["lifecycle_state"] = "UNRESOLVED"
                event["confirmation_time"] = None
                event["reasons"] = [
                    *list(event.get("reasons") or []),
                    "replayed_body_close_does_not_match_source_confirmed_at",
                ]
            event.update(
                {
                    "source_break_object_id": str(candidate.get("object_id") or ""),
                    "source_break_type": str(candidate.get("break_type") or ""),
                    "source_confirmation_status": str(candidate.get("confirmation_status") or ""),
                    "broken_swing_id": broken_swing_id,
                    "broken_level_price": level_price,
                    "level_available_at": available_at.isoformat().replace("+00:00", "Z"),
                    "source_candidate_at": (
                        _timestamp(candidate.get("candidate_at")).isoformat().replace("+00:00", "Z")
                        if candidate.get("candidate_at") is not None
                        else None
                    ),
                    "source_confirmed_at": (
                        _timestamp(source_confirmed_at).isoformat().replace("+00:00", "Z")
                        if source_confirmed_at is not None
                        else None
                    ),
                    "source_binding_matches": source_binding_matches,
                    "timeframe": timeframe,
                    "atr_at_candidate": atr,
                }
            )
            if scope == "external":
                pending_parent_invalidation = _apply_parent_invalidation_chain(
                    event=event,
                    evidence=evidence,
                    direction=direction,
                    prior_direction=prior_direction[scope],
                    pending=pending_parent_invalidation,
                    candles=candles,
                    config=config,
                )
            event["accepted_for_shadow_story"] = _is_accepted_event(event.get("event_type"))
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


def _apply_parent_invalidation_chain(
    *,
    event: dict[str, Any],
    evidence: Mapping[str, Any],
    direction: str,
    prior_direction: str | None,
    pending: dict[str, Any] | None,
    candles: Sequence[Mapping[str, Any]],
    config: BreakLifecycleConfig,
) -> dict[str, Any] | None:
    """Confirm a two-stage external MSS without weakening break thresholds.

    Sometimes the first body close through the protected point is decisive in
    location but not strong enough to pass the external displacement gate. If
    price then *holds* beyond that protected point and a later external level
    breaks with full displacement/follow-through, the pair is one causal MSS
    sequence. The first event remains rejected as a standalone break; only the
    later, independently strong external event can complete the chain.
    """
    event["parent_invalidation_probe"] = False
    event["parent_invalidation_chain"] = None

    # A pending probe expires causally on a body-close reclaim. There is no
    # wall-clock timeout and no future data: state survives exactly while the
    # protected level remains invalidated on closed candles.
    if pending is not None and not _closed_candles_hold_beyond(
        candles=candles,
        direction=str(pending["direction"]),
        level=float(pending["protected_level"]),
        start_time=str(pending["body_close_time"]),
        end_time=str(event.get("body_close_time") or event.get("source_confirmed_at") or ""),
    ):
        pending = None

    if (
        pending is not None
        and direction == pending.get("direction")
        and str(event.get("event_type") or "").startswith("EXTERNAL_MSS_CANDIDATE_")
        and event.get("source_binding_matches") is True
        and event.get("confirmation_time") is not None
        and _closed_candles_hold_beyond(
            candles=candles,
            direction=direction,
            level=float(pending["protected_level"]),
            start_time=str(pending["body_close_time"]),
            end_time=str(event["confirmation_time"]),
        )
    ):
        event["event_type"] = f"EXTERNAL_MSS_CONFIRMED_{direction.upper()}"
        event["lifecycle_state"] = "ACCEPTED_BREAKOUT"
        event["parent_invalidation_chain"] = {
            "schema": "held_protected_break_plus_external_displacement_v1",
            "protected_break_event_id": pending["source_break_object_id"],
            "protected_swing_id": pending["protected_swing_id"],
            "protected_level": pending["protected_level"],
            "protected_break_body_close_time": pending["body_close_time"],
            "confirming_external_event_id": event.get("source_break_object_id"),
            "confirming_external_time": event.get("confirmation_time"),
            "held_without_body_close_reclaim": True,
        }
        event["reasons"] = [
            *list(event.get("reasons") or []),
            "held_protected_break_confirmed_by_later_external_displacement",
        ]
        return None

    direct_protected_break = bool(evidence.get("broke_protected_swing"))
    if (
        direct_protected_break
        and prior_direction in {"bullish", "bearish"}
        and direction != prior_direction
        and _qualifies_as_parent_invalidation_probe(event, config)
    ):
        pending = {
            "direction": direction,
            "source_break_object_id": event.get("source_break_object_id"),
            "protected_swing_id": evidence.get("protected_swing_id")
            or evidence.get("broken_swing_id"),
            "protected_level": event.get("broken_level_price"),
            "body_close_time": event.get("body_close_time"),
        }
        event["parent_invalidation_probe"] = True
        event["parent_invalidation_chain"] = {
            "schema": "held_protected_break_plus_external_displacement_v1",
            "status": "AWAITING_STRONG_EXTERNAL_FOLLOWUP",
            **pending,
        }

    # A directly accepted protected break already owns the MSS label; no
    # deferred chain remains necessary.
    if direct_protected_break and _is_accepted_event(event.get("event_type")):
        return None
    return pending


def _qualifies_as_parent_invalidation_probe(
    event: Mapping[str, Any],
    config: BreakLifecycleConfig,
) -> bool:
    if event.get("source_binding_matches") is not True:
        return False
    if str(event.get("source_confirmation_status") or "") != "confirmed":
        return False
    if event.get("body_close_time") is None or event.get("broken_level_price") is None:
        return False
    try:
        penetration_atr = float(event.get("normalized_penetration_atr"))
        penetration_bps = float(event.get("close_beyond_structure_bps"))
    except (TypeError, ValueError):
        return False
    if penetration_atr < config.minimum_penetration_atr:
        return False
    if penetration_bps < config.minimum_close_beyond_structure_bps:
        return False
    reasons = set(str(reason) for reason in event.get("reasons") or [])
    return not reasons.intersection(
        {
            "displacement_direction_mismatch",
            "gap_open_requires_separate_interaction_policy",
            "replayed_body_close_does_not_match_source_confirmed_at",
        }
    )


def _closed_candles_hold_beyond(
    *,
    candles: Sequence[Mapping[str, Any]],
    direction: str,
    level: float,
    start_time: str,
    end_time: str,
) -> bool:
    if not start_time or not end_time:
        return False
    start = _timestamp(start_time)
    end = _timestamp(end_time)
    if end < start:
        return False
    observed = 0
    tolerance = max(abs(level) * 1e-9, 1e-12)
    for candle in candles:
        close_time = _timestamp(candle.get("close_time") or candle.get("timestamp"))
        if close_time < start or close_time > end:
            continue
        observed += 1
        close = float(candle["close"])
        if direction == "bullish" and close <= level + tolerance:
            return False
        if direction == "bearish" and close >= level - tolerance:
            return False
    return observed > 0


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
