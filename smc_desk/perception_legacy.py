"""Object-level SMC perception contracts and matching helpers.

Synthetic fixtures are useful detector regression tests, but real perception
quality must be measured against independently reviewed chart objects.  This
module defines the annotation payload stored in a case and provides strict,
explainable matching for engine-versus-gold evaluation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Primitive = Literal[
    "bos",
    "choch",
    "liquidity_sweep",
    "fvg",
    "order_block",
    "equal_highs",
    "equal_lows",
    "inducement",
    "supply",
    "demand",
]

EVENT_PRIMITIVES = {"bos", "choch", "liquidity_sweep", "inducement"}
ZONE_PRIMITIVES = {"fvg", "order_block", "equal_highs", "equal_lows", "supply", "demand"}


class PerceptionAnnotation(BaseModel):
    """One human- or engine-labelled SMC object on a chart."""

    annotation_id: str
    primitive: Primitive
    timeframe: str = "15m"
    direction: Literal["bullish", "bearish", "neutral"] | None = None
    structure_scope: Literal["internal", "swing", "external", "unknown"] | None = None
    timestamp: str | None = None
    price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    status: Literal["fresh", "partial", "mitigated", "swept", "unswept", "unknown"] = "unknown"
    confidence: Literal["high", "medium", "low"] = "high"
    notes: str | None = None

    @model_validator(mode="after")
    def validate_location(self) -> "PerceptionAnnotation":
        if self.price_low is not None and self.price_high is not None and self.price_low > self.price_high:
            raise ValueError("price_low must be less than or equal to price_high")
        if self.primitive in EVENT_PRIMITIVES and self.timestamp is None:
            raise ValueError(f"{self.primitive} annotations require a timestamp")
        if self.primitive in EVENT_PRIMITIVES and self.price is None:
            raise ValueError(f"{self.primitive} annotations require a price")
        if self.primitive in ZONE_PRIMITIVES and self.price_low is None and self.price_high is None:
            raise ValueError(f"{self.primitive} annotations require price_low/price_high")
        return self


class PerceptionAnnotationSet(BaseModel):
    """Expert perception labels attached to one case.json file."""

    schema_version: str = "1.0"
    label_status: Literal["missing", "draft", "reviewed", "adjudicated"] = "missing"
    reviewer_ids: list[str] = Field(default_factory=list)
    adjudicated_by: str | None = None
    objects: list[PerceptionAnnotation] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> "PerceptionAnnotationSet":
        if self.label_status == "adjudicated" and not self.adjudicated_by:
            raise ValueError("adjudicated labels require adjudicated_by")
        if self.label_status in {"reviewed", "adjudicated"} and not self.reviewer_ids:
            raise ValueError("reviewed labels require reviewer_ids")
        return self


def perception_annotation_scaffold() -> dict[str, Any]:
    """JSON-safe empty schema included in every new case."""
    return PerceptionAnnotationSet().model_dump(mode="json")


def _event_primitive(label: str) -> Primitive | None:
    return {
        "BOS": "bos",
        "CHoCH": "choch",
        "Liquidity Sweep": "liquidity_sweep",
        "Inducement": "inducement",
    }.get(label)


def engine_perception_objects(machine_analysis: dict[str, Any]) -> list[PerceptionAnnotation]:
    """Translate engine output into the same object schema used by experts."""
    objects: list[PerceptionAnnotation] = []
    for number, event in enumerate(machine_analysis.get("events") or []):
        primitive = _event_primitive(str(event.get("label") or ""))
        if primitive is None:
            continue
        objects.append(
            PerceptionAnnotation(
                annotation_id=f"engine-event-{number}",
                primitive=primitive,
                timeframe=str(machine_analysis.get("timeframe") or "15m"),
                direction=event.get("direction"),
                structure_scope=event.get("structure_scope"),
                timestamp=event.get("timestamp"),
                price=event.get("price"),
                status="swept" if primitive == "liquidity_sweep" else "unknown",
                confidence="high" if event.get("strength") == "strong" else "medium",
                notes=event.get("reason"),
            )
        )

    for number, zone in enumerate(machine_analysis.get("zones") or []):
        kind = str(zone.get("kind") or "")
        label = str(zone.get("label") or "")
        primitive: Primitive | None = None
        if kind == "fvg":
            primitive = "fvg"
        elif kind == "order_block":
            primitive = "order_block"
        elif label == "Equal Highs":
            primitive = "equal_highs"
        elif label == "Equal Lows":
            primitive = "equal_lows"
        if primitive is None:
            continue
        objects.append(
            PerceptionAnnotation(
                annotation_id=f"engine-zone-{number}",
                primitive=primitive,
                timeframe=str(machine_analysis.get("timeframe") or "15m"),
                direction=zone.get("direction"),
                price_low=zone.get("low"),
                price_high=zone.get("high"),
                status=zone.get("status") or "unknown",
                confidence="high" if float(zone.get("score") or 0.0) >= 0.8 else "medium",
                notes=zone.get("reason"),
            )
        )
    return objects


def annotation_set_from_case(case: dict[str, Any]) -> PerceptionAnnotationSet:
    expert_label = case.get("expert_label") or {}
    raw = expert_label.get("perception_annotations") or perception_annotation_scaffold()
    return PerceptionAnnotationSet.model_validate(raw)


def annotation_set_is_gold_ready(annotation_set: PerceptionAnnotationSet) -> bool:
    return annotation_set.label_status == "adjudicated" and bool(annotation_set.objects)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _direction_matches(left: PerceptionAnnotation, right: PerceptionAnnotation) -> bool:
    return not left.direction or not right.direction or left.direction == right.direction


def _zone_band(annotation: PerceptionAnnotation) -> tuple[float, float]:
    low = annotation.price_low if annotation.price_low is not None else annotation.price_high
    high = annotation.price_high if annotation.price_high is not None else annotation.price_low
    if low is None or high is None:
        raise ValueError("zone annotation has no price band")
    return min(float(low), float(high)), max(float(low), float(high))


def zone_overlap_score(left: PerceptionAnnotation, right: PerceptionAnnotation) -> float:
    """Intersection-over-union for two price zones."""
    left_low, left_high = _zone_band(left)
    right_low, right_high = _zone_band(right)
    intersection = max(0.0, min(left_high, right_high) - max(left_low, right_low))
    union = max(left_high, right_high) - min(left_low, right_low)
    if union <= 0:
        return 1.0 if left_low == right_low else 0.0
    return intersection / union


def event_match_score(
    truth: PerceptionAnnotation,
    machine: PerceptionAnnotation,
    *,
    time_tolerance_minutes: float,
    price_tolerance_pct: float,
) -> float | None:
    if not truth.timestamp or not machine.timestamp or truth.price is None or machine.price is None:
        return None
    minutes = abs((_parse_timestamp(machine.timestamp) - _parse_timestamp(truth.timestamp)).total_seconds()) / 60.0
    if minutes > time_tolerance_minutes:
        return None
    scale = max(abs(float(truth.price)), 1e-9)
    price_error = abs(float(machine.price) - float(truth.price)) / scale
    if price_error > price_tolerance_pct:
        return None
    return 1.0 - 0.5 * (minutes / max(time_tolerance_minutes, 1e-9)) - 0.5 * (price_error / max(price_tolerance_pct, 1e-9))


def annotation_match_score(
    truth: PerceptionAnnotation,
    machine: PerceptionAnnotation,
    *,
    time_tolerance_minutes: float = 15.0,
    price_tolerance_pct: float = 0.001,
    min_zone_iou: float = 0.5,
) -> float | None:
    """Return a match score, or ``None`` when objects are not equivalent."""
    if truth.primitive != machine.primitive or truth.timeframe != machine.timeframe:
        return None
    if not _direction_matches(truth, machine):
        return None
    if truth.primitive in EVENT_PRIMITIVES:
        return event_match_score(
            truth,
            machine,
            time_tolerance_minutes=time_tolerance_minutes,
            price_tolerance_pct=price_tolerance_pct,
        )
    if truth.primitive in ZONE_PRIMITIVES:
        score = zone_overlap_score(truth, machine)
        return score if score >= min_zone_iou else None
    return None


def greedy_match_annotations(
    truth_objects: list[PerceptionAnnotation],
    machine_objects: list[PerceptionAnnotation],
    *,
    time_tolerance_minutes: float = 15.0,
    price_tolerance_pct: float = 0.001,
    min_zone_iou: float = 0.5,
) -> list[tuple[int, int, float]]:
    """One-to-one maximum-score matching without hiding duplicate detections."""
    candidates: list[tuple[float, int, int]] = []
    for truth_index, truth in enumerate(truth_objects):
        for machine_index, machine in enumerate(machine_objects):
            score = annotation_match_score(
                truth,
                machine,
                time_tolerance_minutes=time_tolerance_minutes,
                price_tolerance_pct=price_tolerance_pct,
                min_zone_iou=min_zone_iou,
            )
            if score is not None:
                candidates.append((score, truth_index, machine_index))
    matches: list[tuple[int, int, float]] = []
    used_truth: set[int] = set()
    used_machine: set[int] = set()
    for score, truth_index, machine_index in sorted(candidates, reverse=True):
        if truth_index in used_truth or machine_index in used_machine:
            continue
        matches.append((truth_index, machine_index, score))
        used_truth.add(truth_index)
        used_machine.add(machine_index)
    return matches
