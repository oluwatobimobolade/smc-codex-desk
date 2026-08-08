"""Schema adapters shared by the experimental perception programme.

The canonical detector, formal graph, candidate atlas, and research fixtures
were created at different times. This module is the only allowed compatibility
boundary between them; downstream code must not guess identifier or geometry
field names independently.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


ID_FIELDS = ("object_id", "candidate_id", "liquidity_id", "poi_id", "range_id", "swing_id")
TIME_FIELDS = ("available_at", "confirmed_at", "candidate_at", "pivot_time", "timestamp", "close_time")


def canonical_object_id(record: Mapping[str, Any]) -> str | None:
    for field in ID_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def candidate_time(record: Mapping[str, Any]) -> str:
    for field in TIME_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def candidate_type(record: Mapping[str, Any]) -> str:
    return str(
        record.get("object_type")
        or record.get("candidate_type")
        or record.get("type")
        or record.get("pivot_type")
        or ""
    )


def candidate_price_bounds(record: Mapping[str, Any]) -> tuple[float, float] | None:
    low = _float(record.get("price_low"))
    high = _float(record.get("price_high"))
    if low is not None and high is not None:
        return (min(low, high), max(low, high))
    for field in ("price", "pivot_price", "broken_price", "level_price"):
        value = _float(record.get(field))
        if value is not None:
            return (value, value)
    return None


def flatten_candidate_objects(candidate_objects: Any) -> list[Mapping[str, Any]]:
    """Flatten either real PEV2 buckets, atlas payloads, or compact contexts."""
    out: list[Mapping[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            if canonical_object_id(node):
                out.append(node)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list) or isinstance(node, tuple):
            for value in node:
                walk(value)

    walk(candidate_objects)
    deduped: dict[str, Mapping[str, Any]] = {}
    for record in out:
        oid = canonical_object_id(record)
        if oid:
            deduped[oid] = record
    return list(deduped.values())


def graph_anchor_records(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return real formal-graph anchors with canonical IDs and source records."""
    out: list[dict[str, Any]] = []

    def add(object_id: Any, kind: str, source: str, reason: str, record: Mapping[str, Any]) -> None:
        if not isinstance(object_id, str) or not object_id:
            return
        out.append({
            "object_id": object_id,
            "anchor_kind": kind,
            "anchor_source": source,
            "anchor_reason": reason,
            "record": dict(record),
        })

    active = graph.get("active_range")
    if isinstance(active, Mapping):
        add(active.get("protected_high_swing_id") or active.get("high_object_id"),
            "active_external_high", "formal_structure_graph.active_range",
            "certified active-range protected high", active)
        add(active.get("protected_low_swing_id") or active.get("low_object_id"),
            "active_external_low", "formal_structure_graph.active_range",
            "certified active-range protected low", active)
        add(active.get("range_id"), "range_endpoint", "formal_structure_graph.active_range",
            "certified active dealing range", active)

    timeframes = graph.get("timeframes") or {}
    if isinstance(timeframes, Mapping):
        for timeframe, node in timeframes.items():
            if not isinstance(node, Mapping):
                continue
            for key, kind in (("protected_high", "active_external_high"), ("protected_low", "active_external_low")):
                point = node.get(key)
                if isinstance(point, Mapping):
                    add(point.get("swing_id") or point.get("object_id"), kind,
                        f"formal_structure_graph.timeframes.{timeframe}.{key}",
                        f"{timeframe} {key.replace('_', ' ')}", point)
            for key in ("latest_external_break", "latest_internal_break"):
                event = node.get(key)
                if isinstance(event, Mapping):
                    add(event.get("object_id"), "break_origin",
                        f"formal_structure_graph.timeframes.{timeframe}.{key}",
                        f"{timeframe} {key.replace('_', ' ')}", event)
            if str(timeframe).lower() in {"1d", "4h", "1h"}:
                for key in ("order_blocks", "poi_grade_fvgs"):
                    values = node.get(key) or []
                    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                        for value in values:
                            if isinstance(value, Mapping):
                                add(canonical_object_id(value), "htf_active_poi",
                                    f"formal_structure_graph.timeframes.{timeframe}.{key}",
                                    f"active {timeframe} {key}", value)
            liquidity = node.get("liquidity_levels")
            # The real formal graph emits a COUNT here; only atlas-enriched
            # nodes carry actual liquidity records.
            if isinstance(liquidity, Sequence) and not isinstance(liquidity, (str, bytes)):
                for value in liquidity:
                    if isinstance(value, Mapping) and str(value.get("activity_status", "active")).lower() not in {"consumed", "terminal"}:
                        add(canonical_object_id(value), "unswept_external_liquidity",
                            f"formal_structure_graph.timeframes.{timeframe}.liquidity_levels",
                            f"unconsumed {timeframe} liquidity", value)

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in out:
        deduped[(item["object_id"], item["anchor_kind"])] = item
    return list(deduped.values())


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ID_FIELDS",
    "TIME_FIELDS",
    "canonical_object_id",
    "candidate_time",
    "candidate_type",
    "candidate_price_bounds",
    "flatten_candidate_objects",
    "graph_anchor_records",
]
