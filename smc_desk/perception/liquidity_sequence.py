"""Liquidity sequence summaries for SMC decision quality."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class LiquiditySequence:
    buy_side_liquidity_taken: bool
    sell_side_liquidity_taken: bool
    last_liquidity_event: str
    current_liquidity_draw: str
    next_likely_liquidity: str
    inducement_risk: str
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "buy_side_liquidity_taken": self.buy_side_liquidity_taken,
            "sell_side_liquidity_taken": self.sell_side_liquidity_taken,
            "last_liquidity_event": self.last_liquidity_event,
            "current_liquidity_draw": self.current_liquidity_draw,
            "next_likely_liquidity": self.next_likely_liquidity,
            "inducement_risk": self.inducement_risk,
            "evidence": list(self.evidence),
        }


def build_liquidity_sequence_by_timeframe(perception_by_tf: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        timeframe: summarize_liquidity_sequence(snapshot).to_dict()
        for timeframe, snapshot in perception_by_tf.items()
    }


def summarize_liquidity_sequence(snapshot: Mapping[str, Any]) -> LiquiditySequence:
    sweeps = list(snapshot.get("sweeps", []) or [])
    levels = list(snapshot.get("liquidity_levels", []) or [])
    evidence: list[dict[str, Any]] = []
    buy_taken = False
    sell_taken = False
    last_event = "none"
    sorted_sweeps = sorted(sweeps, key=lambda item: str(item.get("confirmed_at") or item.get("candidate_at") or ""))
    for sweep in sorted_sweeps:
        direction = _direction(sweep.get("direction"))
        side = _sweep_side(sweep)
        if side == "buy_side" or direction == "bearish":
            buy_taken = True
            event = "buy_side_sweep"
        elif side == "sell_side" or direction == "bullish":
            sell_taken = True
            event = "sell_side_sweep"
        else:
            event = "unknown_sweep"
        last_event = event
        evidence.append({
            "object_id": sweep.get("object_id"),
            "event": event,
            "direction": direction,
            "confirmed_at": sweep.get("confirmed_at"),
            "price_low": sweep.get("price_low"),
            "price_high": sweep.get("price_high"),
        })
    if buy_taken and not sell_taken:
        draw = "sell_side_liquidity"
        next_liq = _nearest_level(levels, side="sell_side") or "recent_lows"
        risk = "medium"
    elif sell_taken and not buy_taken:
        draw = "buy_side_liquidity"
        next_liq = _nearest_level(levels, side="buy_side") or "recent_highs"
        risk = "medium"
    elif buy_taken and sell_taken:
        draw = "two_sided_liquidity_taken"
        next_liq = "range_extreme_after_retest"
        risk = "high"
    else:
        draw = "unconfirmed_liquidity_draw"
        next_liq = "unknown"
        risk = "unknown"
    return LiquiditySequence(
        buy_side_liquidity_taken=buy_taken,
        sell_side_liquidity_taken=sell_taken,
        last_liquidity_event=last_event,
        current_liquidity_draw=draw,
        next_likely_liquidity=next_liq,
        inducement_risk=risk,
        evidence=evidence[-8:],
    )


def _sweep_side(sweep: Mapping[str, Any]) -> str:
    evidence = sweep.get("evidence") or {}
    side = evidence.get("liquidity_side") or evidence.get("side")
    if side in {"buy_side", "sell_side"}:
        return str(side)
    swept_level_id = str(evidence.get("swept_level_id") or "").lower()
    if "buy" in swept_level_id or "high" in swept_level_id:
        return "buy_side"
    if "sell" in swept_level_id or "low" in swept_level_id:
        return "sell_side"
    return ""


def _nearest_level(levels: list[Mapping[str, Any]], *, side: str) -> str | None:
    for level in reversed(levels):
        evidence = level.get("evidence") or {}
        if evidence.get("side") == side:
            price = level.get("price_high") if side == "buy_side" else level.get("price_low")
            return f"{side}@{price}"
    return None


def _direction(value: Any) -> str:
    return str(getattr(value, "value", value)).lower()
