"""Doctrine-level SMC setup classifier.

The classifier chooses the active market model before target, stop, or RR logic
runs. It consumes already-detected objects; it does not discover new ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


NO_CLEAR_MODEL = "NO_CLEAR_MODEL"

SETUP_TYPES = {
    "HTF_SUPPLY_REACTION_SHORT",
    "HTF_DEMAND_REACTION_LONG",
    "BREAKER_RETEST_SHORT",
    "BREAKER_RETEST_LONG",
    "IFVG_RETEST_SHORT",
    "IFVG_RETEST_LONG",
    "LIQUIDITY_SWEEP_REVERSAL_SHORT",
    "LIQUIDITY_SWEEP_REVERSAL_LONG",
    "CONTINUATION_RETRACE_SHORT",
    "CONTINUATION_RETRACE_LONG",
    "RANGE_LIQUIDITY_RUN_SHORT",
    "RANGE_LIQUIDITY_RUN_LONG",
    NO_CLEAR_MODEL,
}


@dataclass(frozen=True)
class SetupClassification:
    setup_type: str
    direction: str
    setup_timeframe: str | None
    confidence: float
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_type": self.setup_type,
            "direction": self.direction,
            "setup_timeframe": self.setup_timeframe,
            "confidence": round(self.confidence, 4),
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
        }


def classify_setup_model(
    *,
    cognitive_result: Mapping[str, Any] | None = None,
    official_bias: str | None = None,
    active_poi: Mapping[str, Any] | None = None,
    structure_hierarchy: Mapping[str, Any] | None = None,
    liquidity_sequence: Mapping[str, Any] | None = None,
    inducement_continuation: Mapping[str, Any] | None = None,
) -> SetupClassification:
    cognitive_result = _mapping(cognitive_result)
    watch = _mapping(cognitive_result.get("watch_state"))
    active_poi = _mapping(active_poi) or _mapping(watch.get("active_poi"))
    structure_hierarchy = _mapping(structure_hierarchy) or _mapping(cognitive_result.get("structure_hierarchy"))
    liquidity_sequence = _mapping(liquidity_sequence) or _mapping(cognitive_result.get("liquidity_sequence"))
    inducement_continuation = _mapping(inducement_continuation) or _mapping(cognitive_result.get("inducement_continuation"))

    direction = _direction(official_bias or watch.get("direction") or active_poi.get("direction"))
    setup_timeframe = str(active_poi.get("timeframe") or _dominant_timeframe(structure_hierarchy) or "")
    if direction not in {"bullish", "bearish"}:
        return SetupClassification(NO_CLEAR_MODEL, "neutral", setup_timeframe or None, 0.1, ["No directional HTF/1H model."])
    if not active_poi:
        return SetupClassification(NO_CLEAR_MODEL, direction, setup_timeframe or None, 0.18, ["No certified active POI for the model."])

    kind = _normalise_kind(active_poi.get("kind") or active_poi.get("type"))
    relation = str(active_poi.get("price_relation") or "")
    move_state = str(inducement_continuation.get("state") or "")
    swept = _directional_sweep(direction, liquidity_sequence)
    suffix = "SHORT" if direction == "bearish" else "LONG"

    if "breaker" in kind:
        return SetupClassification(
            f"BREAKER_RETEST_{suffix}",
            direction,
            setup_timeframe or None,
            0.82,
            ["Active POI is a breaker/retest model."],
            {"poi_kind": kind, "price_relation": relation, "directional_liquidity_sweep": swept},
        )
    if "ifvg" in kind or "inverse_fvg" in kind:
        return SetupClassification(
            f"IFVG_RETEST_{suffix}",
            direction,
            setup_timeframe or None,
            0.76,
            ["Active POI is an inverse-FVG retest model."],
            {"poi_kind": kind, "price_relation": relation, "directional_liquidity_sweep": swept},
        )
    if swept and move_state in {"EARLY_CONTINUATION_CONFIRMATION", "CONTINUATION_CONFIRMED", "MOVE_STARTED_NOT_CHASEABLE"}:
        return SetupClassification(
            f"CONTINUATION_RETRACE_{suffix}",
            direction,
            setup_timeframe or None,
            0.74,
            ["Liquidity was taken and displacement created a continuation-retrace model."],
            {"poi_kind": kind, "move_state": move_state, "directional_liquidity_sweep": swept},
        )
    if kind in {"supply", "order_block"} and direction == "bearish":
        return SetupClassification(
            "HTF_SUPPLY_REACTION_SHORT",
            direction,
            setup_timeframe or None,
            0.68,
            ["Bearish HTF/1H supply reaction model."],
            {"poi_kind": kind, "price_relation": relation},
        )
    if kind in {"demand", "order_block"} and direction == "bullish":
        return SetupClassification(
            "HTF_DEMAND_REACTION_LONG",
            direction,
            setup_timeframe or None,
            0.68,
            ["Bullish HTF/1H demand reaction model."],
            {"poi_kind": kind, "price_relation": relation},
        )
    if swept:
        return SetupClassification(
            f"LIQUIDITY_SWEEP_REVERSAL_{suffix}",
            direction,
            setup_timeframe or None,
            0.54,
            ["Directional liquidity sweep exists, but the POI type is less specific."],
            {"poi_kind": kind, "directional_liquidity_sweep": swept},
        )
    return SetupClassification(
        NO_CLEAR_MODEL,
        direction,
        setup_timeframe or None,
        0.25,
        ["The active objects do not form a clean doctrine-approved setup model."],
        {"poi_kind": kind, "price_relation": relation},
    )


def _directional_sweep(direction: str, liquidity_sequence: Mapping[str, Any]) -> bool:
    for tf in ("15m", "1h", "4h", "1d"):
        sequence = _mapping(liquidity_sequence.get(tf))
        if direction == "bearish" and sequence.get("buy_side_liquidity_taken"):
            return True
        if direction == "bullish" and sequence.get("sell_side_liquidity_taken"):
            return True
    return False


def _dominant_timeframe(hierarchy: Mapping[str, Any]) -> str | None:
    for tf in ("1h", "4h", "15m", "1d"):
        item = _mapping(hierarchy.get(tf))
        if item.get("external_bias") in {"bullish", "bearish"}:
            return tf
    return None


def _normalise_kind(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _direction(value: Any) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

