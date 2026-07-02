"""SMC watch-state decision layer.

This layer intentionally keeps final action observe-only. It improves the
language between "no trade" and "execute" so the colleague can say what a
professional trader would watch next.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from smc_desk.decision.poi_selection import build_poi_selection


WATCH_STATES = {
    "WATCH_BEARISH_RETRACE_TO_SUPPLY",
    "WATCH_BULLISH_RETRACE_TO_DEMAND",
    "POI_NOT_REACHED",
    "POI_TOUCHED_AWAIT_15M_CONFIRMATION",
    "AWAIT_15M_BEARISH_CONFIRMATION",
    "AWAIT_15M_BULLISH_CONFIRMATION",
    "NO_TRADE_INTERNAL_ONLY",
    "NO_TRADE_HTF_CONFLICT",
    "NO_VALID_ACTIVE_POI_IN_CURRENT_1H_RANGE",
    "WATCH_NEW_LOWER_SUPPLY_FORMATION",
    "WATCH_NEW_HIGHER_DEMAND_FORMATION",
    "REVIEW_REQUIRED_POI_OUTSIDE_PROTECTED_RANGE",
    "REVIEW_REQUIRED",
}


@dataclass(frozen=True)
class WatchStateDecision:
    final_state: str
    final_action: str
    signal_allowed: bool
    direction: str
    active_poi: dict[str, Any] | None
    poi_selection: dict[str, Any] | None
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_state": self.final_state,
            "final_action": self.final_action,
            "signal_allowed": self.signal_allowed,
            "direction": self.direction,
            "active_poi": self.active_poi,
            "poi_selection": self.poi_selection,
            "reasons": self.reasons,
        }


def evaluate_watch_state(
    *,
    hierarchy_by_tf: Mapping[str, Mapping[str, Any]],
    roles: Mapping[str, Any],
    pois_by_tf: Mapping[str, list[Mapping[str, Any]]],
) -> WatchStateDecision:
    h4 = hierarchy_by_tf.get("4h", {})
    h1 = hierarchy_by_tf.get("1h", {})
    bias_4h = _bias(h4)
    bias_1h = _bias(h1)
    reasons = list(roles.get("notes", [])) if isinstance(roles, Mapping) else []

    if bias_4h in {"bullish", "bearish"} and bias_1h in {"bullish", "bearish"} and bias_4h != bias_1h:
        return WatchStateDecision(
            final_state="NO_TRADE_HTF_CONFLICT",
            final_action="NO_SIGNAL",
            signal_allowed=False,
            direction="neutral",
            active_poi=None,
            poi_selection=None,
            reasons=reasons + [f"4h external bias {bias_4h} conflicts with 1h external bias {bias_1h}."],
        )

    direction = bias_4h or bias_1h or "neutral"
    if direction == "neutral":
        return WatchStateDecision(
            final_state="REVIEW_REQUIRED",
            final_action="NO_SIGNAL",
            signal_allowed=False,
            direction="neutral",
            active_poi=None,
            poi_selection=None,
            reasons=reasons + ["No usable external bias after hierarchy repair."],
        )

    poi_selection = build_poi_selection(pois_by_tf, direction=direction)
    poi = poi_selection.get("selected_active_poi")
    if poi is None:
        state = str(poi_selection.get("status") or "NO_VALID_ACTIVE_POI_IN_CURRENT_1H_RANGE")
        return WatchStateDecision(
            final_state=state,
            final_action="NO_SIGNAL",
            signal_allowed=False,
            direction=direction,
            active_poi=None,
            poi_selection=poi_selection,
            reasons=reasons + [
                f"{direction} external context exists, but no protected-range-valid active HTF POI is certified.",
                "Parent-scope or rejected POIs may be tracked as context only; they cannot drive the active setup.",
            ],
        )

    relation = str(poi.get("price_relation"))
    kind = str(poi.get("kind"))
    if direction == "bearish":
        if relation == "below_poi":
            state = "WATCH_BEARISH_RETRACE_TO_SUPPLY" if kind in {"supply", "order_block"} else "POI_NOT_REACHED"
            reason = "Price is below bearish POI; wait for retrace into supply and then 15m bearish confirmation."
        elif relation == "inside_poi":
            state = "POI_TOUCHED_AWAIT_15M_CONFIRMATION"
            reason = "Price is inside bearish POI; execution still requires 15m bearish confirmation."
        else:
            state = "REVIEW_REQUIRED"
            reason = f"Bearish POI relation is {relation}; review invalidation."
    else:
        if relation == "above_poi":
            state = "WATCH_BULLISH_RETRACE_TO_DEMAND" if kind in {"demand", "order_block"} else "POI_NOT_REACHED"
            reason = "Price is above bullish POI; wait for retrace into demand and then 15m bullish confirmation."
        elif relation == "inside_poi":
            state = "POI_TOUCHED_AWAIT_15M_CONFIRMATION"
            reason = "Price is inside bullish POI; execution still requires 15m bullish confirmation."
        else:
            state = "REVIEW_REQUIRED"
            reason = f"Bullish POI relation is {relation}; review invalidation."

    return WatchStateDecision(
        final_state=state,
        final_action="NO_SIGNAL",
        signal_allowed=False,
        direction=direction,
        active_poi=dict(poi),
        poi_selection=poi_selection,
        reasons=reasons + [reason, "Final action remains observe-only; no paper/live execution authority."],
    )


def _bias(hierarchy: Mapping[str, Any]) -> str | None:
    bias = str(hierarchy.get("external_bias", "neutral"))
    return bias if bias in {"bullish", "bearish"} else None
