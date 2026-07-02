"""Observe-only execution-readiness staging for SMC decisions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionReadiness:
    state: str
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "confidence": round(self.confidence, 4),
            "reasons": list(self.reasons),
            "observe_only": True,
            "signal_allowed": False,
            "paper_execution": "disabled",
            "live_execution": "disabled",
            "capital_risk": 0,
        }


def evaluate_execution_readiness(
    *,
    watch_state: Mapping[str, Any] | None,
    inducement_continuation: Mapping[str, Any] | None,
) -> ExecutionReadiness:
    watch_state = watch_state or {}
    inducement_continuation = inducement_continuation or {}
    watch = str(watch_state.get("final_state") or "")
    move_state = str(inducement_continuation.get("state") or "")
    active_poi = watch_state.get("active_poi")
    reasons = [f"watch_state={watch or 'unknown'}", f"move_state={move_state or 'unknown'}"]

    if not watch or watch in {"REVIEW_REQUIRED", "NO_TRADE_HTF_CONFLICT"}:
        return ExecutionReadiness("NO_MODEL", 0.2, reasons + ["No clean HTF model."])
    if move_state == "MOVE_STARTED_NOT_CHASEABLE":
        return ExecutionReadiness("MOVE_STARTED_NOT_CHASEABLE", 0.68, reasons + ["Displacement already ran into target-side liquidity; do not chase."])
    if move_state == "EARLY_CONTINUATION_CONFIRMATION":
        zone = _active_poi_phrase(active_poi) or "the new LTF zone"
        return ExecutionReadiness("WAIT_FOR_RETRACE_TO_LTF_SUPPLY", 0.62, reasons + [f"Continuation shift exists; wait for retest/rejection from {zone}."])
    if move_state in {"POSSIBLE_INDUCEMENT", "INDUCEMENT_CONFIRMED"}:
        return ExecutionReadiness("INDUCEMENT_RISK_HIGH", 0.48, reasons + ["Reclaim/inducement risk remains unresolved."])
    if active_poi and watch == "POI_TOUCHED_AWAIT_15M_CONFIRMATION":
        return ExecutionReadiness("POI_REACHED_AWAIT_CONFIRMATION", 0.58, reasons + ["POI touched; 15M confirmation still required."])
    if active_poi and watch.startswith("WATCH_"):
        return ExecutionReadiness("POI_NOT_REACHED", 0.52, reasons + ["Valid POI exists, but price has not confirmed entry timing."])
    if watch in {"NO_VALID_ACTIVE_POI_IN_CURRENT_1H_RANGE", "WATCH_NEW_LOWER_SUPPLY_FORMATION", "WATCH_NEW_HIGHER_DEMAND_FORMATION"}:
        return ExecutionReadiness("HTF_MODEL_FORMING", 0.42, reasons + ["HTF direction exists, but active setup POI is not certified."])
    return ExecutionReadiness("EARLY_CONFIRMATION_FORMING", 0.45, reasons + ["Decision state is observe-only and still forming."])


def _active_poi_phrase(active_poi: Any) -> str | None:
    if not isinstance(active_poi, Mapping):
        return None
    low = active_poi.get("price_low")
    high = active_poi.get("price_high")
    if low in {None, ""} or high in {None, ""}:
        return None
    timeframe = str(active_poi.get("timeframe") or "").strip()
    kind = str(active_poi.get("kind") or "POI").strip()
    prefix = f"active {timeframe} " if timeframe else "active "
    return f"{prefix}{kind} {low}-{high}"
