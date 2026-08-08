"""Point-in-time sweep versus accepted-breakout lifecycle."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


def classify_sweep_lifecycle(
    *,
    sweep: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]],
    structure_breaks: Sequence[Mapping[str, Any]],
    decision_time: str,
    consequence_horizon_bars: int = 6,
) -> dict[str, Any]:
    evidence = sweep.get("evidence") if isinstance(sweep.get("evidence"), Mapping) else {}
    level = _number(evidence.get("swept_price"))
    direction = str(sweep.get("direction") or "").lower()
    interaction_time = sweep.get("candidate_at") or sweep.get("pivot_time") or sweep.get("confirmed_at")
    if level is None or direction not in {"bullish", "bearish"} or interaction_time is None:
        return _result("INSUFFICIENT_EVIDENCE", False, ["missing_level_direction_or_interaction"])
    cutoff = _timestamp(decision_time)
    visible = sorted(
        (dict(candle) for candle in candles if _timestamp(_candle_time(candle)) <= cutoff),
        key=lambda candle: _timestamp(_candle_time(candle)),
    )
    if not visible:
        return _result("INSUFFICIENT_EVIDENCE", False, ["no_visible_candles"])
    interaction_index = _nearest_index(visible, interaction_time)
    if interaction_index is None:
        return _result("INSUFFICIENT_EVIDENCE", False, ["interaction_outside_visible_window"])
    interaction = visible[interaction_index]
    reclaimed = _reclaimed(interaction, level, direction)
    penetrated = _penetrated(interaction, level, direction)
    if not penetrated:
        return _result("NO_PENETRATION", False, ["level_not_penetrated"])
    if not reclaimed:
        return _result("PENETRATION_ACCEPTANCE_CANDIDATE", False, ["penetrated_without_reclaim"])

    after = visible[interaction_index + 1 : interaction_index + 1 + consequence_horizon_bars]
    acceptance_count = 0
    for candle in after:
        if _accepted_beyond(candle, level, direction):
            acceptance_count += 1
            if acceptance_count >= 2:
                return _result(
                    "ACCEPTED_BREAKOUT",
                    False,
                    ["two_closes_accepted_beyond_liquidity"],
                    bars_observed=len(after),
                )
        else:
            acceptance_count = 0

    structural_break_id = _opposing_structural_consequence(
        structure_breaks,
        direction=direction,
        interaction_time=_timestamp(interaction_time),
        horizon_end=_timestamp(_candle_time(after[-1])) if after else cutoff,
    )
    if structural_break_id:
        return _result(
            "CONFIRMED_STRUCTURAL_SWEEP",
            True,
            ["reclaim_followed_by_opposing_structural_consequence"],
            bars_observed=len(after),
            structural_consequence_id=structural_break_id,
        )
    if len(after) < consequence_horizon_bars:
        return _result("RECLAIM_CANDIDATE", False, ["awaiting_structural_consequence"], bars_observed=len(after))
    return _result("LOCAL_REJECTION_NO_STRUCTURAL_CONSEQUENCE", False, ["reclaim_horizon_expired_without_structure_break"], bars_observed=len(after))


def enrich_sweep_lifecycles(
    detector_candidates: Mapping[str, Any],
    timeframe_dfs: Mapping[str, pd.DataFrame],
    *,
    decision_time: str,
) -> dict[str, Any]:
    enriched = {timeframe: dict(payload) for timeframe, payload in detector_candidates.items() if isinstance(payload, Mapping)}
    for timeframe, payload in enriched.items():
        df = timeframe_dfs.get(timeframe)
        if df is None or df.empty:
            continue
        normalized = df.copy()
        if "timestamp" not in normalized.columns:
            normalized = normalized.reset_index().rename(columns={"index": "timestamp"})
        candles = normalized[[column for column in ("timestamp", "open", "high", "low", "close") if column in normalized.columns]].to_dict(orient="records")
        breaks = [dict(item) for item in payload.get("structure_breaks", []) or [] if isinstance(item, Mapping)]
        sweeps: list[dict[str, Any]] = []
        for raw in payload.get("sweeps", []) or []:
            if not isinstance(raw, Mapping):
                continue
            sweep = dict(raw)
            lifecycle = classify_sweep_lifecycle(
                sweep=sweep,
                candles=candles,
                structure_breaks=breaks,
                decision_time=decision_time,
            )
            sweep["sweep_lifecycle"] = lifecycle
            sweep["confirmation_status"] = "confirmed" if lifecycle["structural_sweep_confirmed"] else "provisional"
            sweep["truth_status"] = lifecycle["state"].lower()
            sweeps.append(sweep)
        payload["sweeps"] = sweeps
    return enriched


def _opposing_structural_consequence(
    breaks: Sequence[Mapping[str, Any]], *, direction: str, interaction_time: pd.Timestamp, horizon_end: pd.Timestamp,
) -> str | None:
    for item in breaks:
        if str(item.get("direction") or "").lower() != direction:
            continue
        if str(item.get("confirmation_status") or "").lower() != "confirmed":
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
        if evidence.get("is_unconfirmed_probe") or item.get("is_wick_only_probe"):
            continue
        event_time = item.get("confirmed_at") or item.get("candidate_at")
        if event_time is None:
            continue
        timestamp = _timestamp(event_time)
        if interaction_time < timestamp <= horizon_end:
            return str(item.get("object_id") or "") or None
    return None


def _result(
    state: str,
    confirmed: bool,
    reasons: list[str],
    *,
    bars_observed: int = 0,
    structural_consequence_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": "sweep_lifecycle_v1",
        "state": state,
        "structural_sweep_confirmed": confirmed,
        "bars_observed_after_reclaim": bars_observed,
        "structural_consequence_id": structural_consequence_id,
        "reasons": reasons,
        "certainty_definition": "point_in_time_sweep_state_not_future_prediction",
    }


def _penetrated(candle: Mapping[str, Any], level: float, direction: str) -> bool:
    value = _number(candle.get("low" if direction == "bullish" else "high"))
    return False if value is None else value < level if direction == "bullish" else value > level


def _reclaimed(candle: Mapping[str, Any], level: float, direction: str) -> bool:
    close = _number(candle.get("close"))
    return False if close is None else close > level if direction == "bullish" else close < level


def _accepted_beyond(candle: Mapping[str, Any], level: float, direction: str) -> bool:
    close = _number(candle.get("close"))
    return False if close is None else close < level if direction == "bullish" else close > level


def _nearest_index(candles: Sequence[Mapping[str, Any]], value: Any) -> int | None:
    target = _timestamp(value)
    candidates = [(abs((_timestamp(_candle_time(candle)) - target).total_seconds()), index) for index, candle in enumerate(candles)]
    return min(candidates)[1] if candidates else None


def _candle_time(candle: Mapping[str, Any]) -> Any:
    value = candle.get("timestamp") or candle.get("open_time") or candle.get("close_time")
    if value is None:
        raise ValueError("candle timestamp required")
    return value


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


__all__ = ["classify_sweep_lifecycle", "enrich_sweep_lifecycles"]
