"""Multi-timeframe contradiction resolver.

The resolver converts mixed timeframe evidence into one conservative outcome.
It never returns "mixed". If the system cannot reconcile the map, it waits or
invalidates the setup instead of letting lower-timeframe noise speak loudly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


TIMEFRAME_WEIGHTS: dict[str, float] = {
    "5m": 1.0,
    "15m": 2.0,
    "1h": 3.0,
    "4h": 4.0,
    "1d": 5.0,
}

HTF_TIMEFRAMES = ("1d", "4h", "1h")


@dataclass(frozen=True)
class ContradictionResolution:
    outcome: str
    dominant_direction: str
    contradiction_score: float
    timeframe_weights: dict[str, float] = field(default_factory=dict)
    direction_weights: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def is_aligned(self) -> bool:
        return self.outcome == "ALIGN"

    @property
    def blocks_signal(self) -> bool:
        return self.outcome in {"WAIT", "INVALIDATE_ALL"}

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "dominant_direction": self.dominant_direction,
            "contradiction_score": round(self.contradiction_score, 4),
            "blocks_signal": self.blocks_signal,
            "timeframe_weights": self.timeframe_weights,
            "direction_weights": {k: round(v, 4) for k, v in self.direction_weights.items()},
            "reasons": list(self.reasons),
        }


def resolve_timeframe_contradictions(signals: Mapping[str, Any]) -> ContradictionResolution:
    """Resolve timeframe directions into ALIGN, WAIT, or INVALIDATE_ALL.

    Args:
        signals: Mapping of timeframe to either a direction string or a dict
            with `direction` and optional `confidence`.
    """
    normalized = {tf: _normalize_signal(raw) for tf, raw in signals.items()}
    active = {
        tf: signal
        for tf, signal in normalized.items()
        if signal["direction"] in {"bullish", "bearish"} and signal["confidence"] > 0
    }
    if not active:
        return ContradictionResolution(
            outcome="WAIT",
            dominant_direction="neutral",
            contradiction_score=0.0,
            timeframe_weights={},
            direction_weights={"bullish": 0.0, "bearish": 0.0},
            reasons=["no_directional_timeframes"],
        )

    direction_weights = {"bullish": 0.0, "bearish": 0.0}
    timeframe_weights: dict[str, float] = {}
    for timeframe, signal in active.items():
        weight = TIMEFRAME_WEIGHTS.get(timeframe, 1.0) * signal["confidence"]
        timeframe_weights[timeframe] = round(weight, 4)
        direction_weights[signal["direction"]] += weight

    bullish = direction_weights["bullish"]
    bearish = direction_weights["bearish"]
    total = bullish + bearish
    dominant_direction = "bullish" if bullish > bearish else "bearish"
    minority = min(bullish, bearish)
    contradiction_score = minority / total if total else 0.0

    reasons: list[str] = [
        f"weighted_{dominant_direction}_dominance:{max(bullish, bearish):.3f}/{total:.3f}",
    ]

    htf_directions = {
        tf: active[tf]["direction"]
        for tf in HTF_TIMEFRAMES
        if tf in active
    }
    unique_htf = set(htf_directions.values())
    if len(unique_htf) > 1:
        reasons.append(f"htf_conflict:{htf_directions}")
        return ContradictionResolution(
            outcome="INVALIDATE_ALL",
            dominant_direction=dominant_direction,
            contradiction_score=round(max(contradiction_score, 0.50), 4),
            timeframe_weights=timeframe_weights,
            direction_weights=direction_weights,
            reasons=reasons,
        )

    lower_tf_opposition = [
        tf for tf, signal in active.items()
        if tf not in HTF_TIMEFRAMES and signal["direction"] != dominant_direction
    ]
    if lower_tf_opposition:
        reasons.append(f"lower_timeframe_opposition:{','.join(sorted(lower_tf_opposition))}")
        return ContradictionResolution(
            outcome="WAIT",
            dominant_direction=dominant_direction,
            contradiction_score=round(max(contradiction_score, 0.25), 4),
            timeframe_weights=timeframe_weights,
            direction_weights=direction_weights,
            reasons=reasons,
        )

    if contradiction_score > 0:
        reasons.append("directional_weights_not_unanimous")
        return ContradictionResolution(
            outcome="WAIT",
            dominant_direction=dominant_direction,
            contradiction_score=round(contradiction_score, 4),
            timeframe_weights=timeframe_weights,
            direction_weights=direction_weights,
            reasons=reasons,
        )

    reasons.append("all_active_timeframes_aligned")
    return ContradictionResolution(
        outcome="ALIGN",
        dominant_direction=dominant_direction,
        contradiction_score=0.0,
        timeframe_weights=timeframe_weights,
        direction_weights=direction_weights,
        reasons=reasons,
    )


def extract_timeframe_signals_from_snapshots(snapshots: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract conservative timeframe directions from PEV2 snapshots."""
    signals: dict[str, dict[str, Any]] = {}
    for timeframe, snapshot in snapshots.items():
        if isinstance(snapshot, dict):
            structure_state = snapshot.get("structure_state", {}) or {}
            breaks = snapshot.get("structure_breaks", []) or []
        else:
            structure_state = getattr(snapshot, "structure_state", {}) or {}
            breaks = getattr(snapshot, "structure_breaks", []) or []
        direction = structure_state.get("current_direction", "neutral")
        if direction not in {"bullish", "bearish"}:
            direction = _latest_break_direction(breaks)
        confidence = 0.75 if direction in {"bullish", "bearish"} else 0.0
        if breaks:
            confidence = min(1.0, confidence + min(len(breaks), 4) * 0.04)
        signals[timeframe] = {
            "direction": direction if direction in {"bullish", "bearish"} else "neutral",
            "confidence": confidence,
        }
    return signals


def _latest_break_direction(breaks: Any) -> str:
    if not breaks:
        return "neutral"
    latest = breaks[-1]
    if isinstance(latest, dict):
        return str(latest.get("direction", "neutral"))
    return str(getattr(latest, "direction", "neutral"))


def _normalize_signal(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return {"direction": raw.lower(), "confidence": 1.0}
    if isinstance(raw, Mapping):
        return {
            "direction": str(raw.get("direction", "neutral")).lower(),
            "confidence": float(raw.get("confidence", 1.0)),
        }
    direction = str(getattr(raw, "direction", "neutral")).lower()
    confidence = float(getattr(raw, "confidence", 1.0))
    return {"direction": direction, "confidence": confidence}
