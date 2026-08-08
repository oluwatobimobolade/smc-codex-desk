"""Deterministic break lifecycle for the V3 experimental perception path."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Sequence

Direction = Literal["bullish", "bearish"]
Scope = Literal["internal", "external"]


@dataclass(frozen=True)
class BreakLifecycleConfig:
    minimum_penetration_atr: float = 0.10
    minimum_body_to_range_ratio: float = 0.55
    minimum_close_beyond_structure_bps: float = 12.0
    minimum_displacement_score: float = 0.75
    early_confirmation_bars: int = 2
    final_confirmation_bars: int = 6
    wick_probe_timeout_bars: int = 6


@dataclass(frozen=True)
class BreakLevel:
    level_id: str
    price: float
    break_direction: Direction
    scope: Scope
    prior_direction: Direction | None
    invalidates_parent_narrative: bool = False


@dataclass(frozen=True)
class BreakLifecycleResult:
    schema: str = "experimental_break_lifecycle_v1"
    event_type: str = "UNRESOLVED"
    lifecycle_state: str = "UNRESOLVED"
    level_id: str = ""
    direction: Direction = "bullish"
    scope: Scope = "internal"
    interaction_time: str | None = None
    body_close_time: str | None = None
    confirmation_time: str | None = None
    displacement_score: float = 0.0
    normalized_penetration_atr: float = 0.0
    close_beyond_structure_bps: float = 0.0
    body_to_range_ratio: float = 0.0
    bars_observed_after_interaction: int = 0
    bars_observed_after_body_close: int = 0
    reasons: tuple[str, ...] = field(default_factory=tuple)
    authority_contract: Mapping[str, bool] = field(
        default_factory=lambda: {
            "canonical": False,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "reasons": list(self.reasons),
            "authority_contract": dict(self.authority_contract),
        }


class ExperimentalBreakLifecycleEngine:
    """Classify one certified-level interaction without future leakage."""

    def __init__(self, config: BreakLifecycleConfig | None = None) -> None:
        self.config = config or BreakLifecycleConfig()

    def classify(
        self,
        *,
        level: BreakLevel,
        candles: Sequence[Mapping[str, Any]],
        atr: float,
        decision_time: str | datetime,
    ) -> BreakLifecycleResult:
        if atr <= 0:
            raise ValueError("atr must be positive")
        cutoff = _time(decision_time)
        visible = sorted(
            (dict(candle) for candle in candles if _time(candle.get("close_time") or candle.get("timestamp")) <= cutoff),
            key=lambda candle: _time(candle.get("close_time") or candle.get("timestamp")),
        )
        if not visible:
            return self._result(level, reasons=("no_visible_closed_candles",))

        interaction_index: int | None = None
        body_index: int | None = None
        probe_expired = False
        for index, candle in enumerate(visible):
            if (
                interaction_index is not None
                and index - interaction_index > self.config.wick_probe_timeout_bars
            ):
                probe_expired = True
                break
            if not _wick_crossed(candle, level):
                continue
            if interaction_index is None:
                interaction_index = index
            if _body_closed_beyond(candle, level):
                body_index = index
                break

        if interaction_index is None:
            return self._result(level, reasons=("certified_level_not_interacted_with",))

        interaction_time = _iso(visible[interaction_index])
        if body_index is None:
            observed_after_interaction = max(0, len(visible) - interaction_index - 1)
            expired = probe_expired or observed_after_interaction >= self.config.wick_probe_timeout_bars
            return self._result(
                level,
                event_type="EXPIRED_WICK_PROBE" if expired else "WICK_PROBE",
                lifecycle_state="EXPIRED" if expired else "WICK_PROBE",
                interaction_time=interaction_time,
                bars_observed_after_interaction=observed_after_interaction,
                reasons=(
                    "wick_probe_expired_without_body_close"
                    if expired
                    else "wick_penetration_without_body_close",
                ),
            )

        body_candle = visible[body_index]
        metrics = _displacement_metrics(body_candle, level, atr, self.config)
        after = visible[body_index + 1 : body_index + 1 + self.config.final_confirmation_bars]
        observed = len(after)
        common = {
            "interaction_time": interaction_time,
            "body_close_time": _iso(body_candle),
            "displacement_score": metrics["score"],
            "normalized_penetration_atr": metrics["penetration_atr"],
            "close_beyond_structure_bps": metrics["penetration_bps"],
            "body_to_range_ratio": metrics["body_ratio"],
            "bars_observed_after_interaction": body_index - interaction_index,
            "bars_observed_after_body_close": observed,
        }
        interaction_valid = metrics["direction_consistent"] and metrics["started_on_origin_side"]
        displacement_passed = metrics["passed"] if level.scope == "external" else interaction_valid
        penetration_passed = metrics["penetration_atr"] >= self.config.minimum_penetration_atr

        if not interaction_valid or not penetration_passed or not displacement_passed:
            if observed < self.config.final_confirmation_bars:
                return self._result(
                    level,
                    event_type="BREAKOUT_CANDIDATE",
                    lifecycle_state="BREAKOUT_CANDIDATE",
                    reasons=tuple(metrics["failures"]) or ("awaiting_displacement_evidence",),
                    **common,
                )
            return self._result(
                level,
                event_type="FAILED_BREAKOUT",
                lifecycle_state="FAILED_BREAKOUT",
                reasons=tuple(metrics["failures"]) or ("displacement_requirement_failed",),
                **common,
            )

        accepted_index = _acceptance_index(after, level, atr, self.config)
        if accepted_index is None:
            if observed < self.config.final_confirmation_bars:
                return self._result(
                    level,
                    event_type="BREAKOUT_CANDIDATE",
                    lifecycle_state="BREAKOUT_CANDIDATE",
                    reasons=("awaiting_follow_through_or_valid_retest",),
                    **common,
                )
            return self._result(
                level,
                event_type="FAILED_BREAKOUT",
                lifecycle_state="FAILED_BREAKOUT",
                reasons=("confirmation_horizon_expired_without_acceptance",),
                **common,
            )

        confirmation = after[accepted_index]
        event_type = _accepted_event_type(level)
        lifecycle_state = (
            "ACCEPTED_BREAKOUT"
            if event_type not in {"EXTERNAL_MSS_CANDIDATE_BULLISH", "EXTERNAL_MSS_CANDIDATE_BEARISH"}
            else "EXTERNAL_MSS_CANDIDATE"
        )
        return self._result(
            level,
            event_type=event_type,
            lifecycle_state=lifecycle_state,
            confirmation_time=_iso(confirmation),
            reasons=("body_close_penetration_displacement_and_confirmation_passed",),
            **common,
        )

    @staticmethod
    def _result(level: BreakLevel, **changes: Any) -> BreakLifecycleResult:
        return BreakLifecycleResult(
            level_id=level.level_id,
            direction=level.break_direction,
            scope=level.scope,
            **changes,
        )


def _displacement_metrics(
    candle: Mapping[str, Any],
    level: BreakLevel,
    atr: float,
    config: BreakLifecycleConfig,
) -> dict[str, Any]:
    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])
    candle_range = max(high - low, 1e-12)
    body_ratio = abs(close - open_price) / candle_range
    penetration = close - level.price if level.break_direction == "bullish" else level.price - close
    penetration = max(penetration, 0.0)
    penetration_atr = penetration / atr
    penetration_bps = penetration / max(level.price, 1e-12) * 10_000.0
    direction_consistent = close > open_price if level.break_direction == "bullish" else close < open_price
    started_on_origin_side = (
        open_price <= level.price if level.break_direction == "bullish" else open_price >= level.price
    )
    body_component = min(body_ratio / 0.70, 1.0)
    bps_component = min(penetration_bps / 25.0, 1.0)
    atr_component = min(penetration_atr / 0.75, 1.0)
    score = body_component * 0.40 + bps_component * 0.35 + atr_component * 0.25
    failures: list[str] = []
    if not direction_consistent:
        failures.append("displacement_direction_mismatch")
    if not started_on_origin_side:
        failures.append("gap_open_requires_separate_interaction_policy")
    if body_ratio < config.minimum_body_to_range_ratio:
        failures.append("body_to_range_ratio_below_external_threshold")
    if penetration_bps < config.minimum_close_beyond_structure_bps:
        failures.append("close_beyond_structure_bps_below_external_threshold")
    if penetration_atr < config.minimum_penetration_atr:
        failures.append("normalized_penetration_below_threshold")
    if score < config.minimum_displacement_score:
        failures.append("displacement_score_below_external_threshold")
    return {
        "body_ratio": body_ratio,
        "penetration_atr": penetration_atr,
        "penetration_bps": penetration_bps,
        "score": score,
        "failures": failures,
        "passed": not failures,
        "direction_consistent": direction_consistent,
        "started_on_origin_side": started_on_origin_side,
    }


def _acceptance_index(
    after: Sequence[Mapping[str, Any]],
    level: BreakLevel,
    atr: float,
    config: BreakLifecycleConfig,
) -> int | None:
    for index, candle in enumerate(after):
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        holds = close > level.price if level.break_direction == "bullish" else close < level.price
        if not holds:
            return None
        follow_through = (
            close >= level.price + config.minimum_penetration_atr * atr
            if level.break_direction == "bullish"
            else close <= level.price - config.minimum_penetration_atr * atr
        )
        retested = (
            low <= level.price + config.minimum_penetration_atr * atr
            if level.break_direction == "bullish"
            else high >= level.price - config.minimum_penetration_atr * atr
        )
        if index + 1 >= config.early_confirmation_bars and (follow_through or retested):
            return index
    return None


def _accepted_event_type(level: BreakLevel) -> str:
    token = level.break_direction.upper()
    if level.prior_direction is None:
        return "INITIAL_DIRECTION_BREAK"
    if level.break_direction == level.prior_direction:
        return f"{level.scope.upper()}_BOS_{token}"
    if level.scope == "internal":
        return f"INTERNAL_CHOCH_{token}"
    if level.invalidates_parent_narrative:
        return f"EXTERNAL_MSS_CONFIRMED_{token}"
    return f"EXTERNAL_MSS_CANDIDATE_{token}"


def _wick_crossed(candle: Mapping[str, Any], level: BreakLevel) -> bool:
    return (
        float(candle["high"]) > level.price
        if level.break_direction == "bullish"
        else float(candle["low"]) < level.price
    )


def _body_closed_beyond(candle: Mapping[str, Any], level: BreakLevel) -> bool:
    return (
        float(candle["close"]) > level.price
        if level.break_direction == "bullish"
        else float(candle["close"]) < level.price
    )


def _time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _iso(candle: Mapping[str, Any]) -> str:
    return _time(candle.get("close_time") or candle.get("timestamp")).isoformat().replace("+00:00", "Z")


__all__ = [
    "BreakLifecycleConfig",
    "BreakLevel",
    "BreakLifecycleResult",
    "ExperimentalBreakLifecycleEngine",
]
