"""Conservative local composer for professional SMC annotation_plan_v2.

This is deliberately a selector, not a second detector. It chooses a handful
of already-certified objects that are visible in the execution chart and lets
the validator reject anything that drifts from those anchors.
"""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.brain.annotation_evidence import AnnotationEvidenceAnchor, build_annotation_evidence_index


def compose_local_annotation_plan_v2(
    *,
    evidence_pack: Mapping[str, Any],
    official_state: str,
    direction: str,
    active_range: Mapping[str, Any],
    active_poi: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select at most three evidence-grounded marks for a 15m official chart."""
    index = build_annotation_evidence_index(evidence_pack)
    windows = evidence_pack.get("ohlcv_windows") or {}
    candles = windows.get("15m") if isinstance(windows, Mapping) else None
    row_count = len(candles) if isinstance(candles, list) else 0
    recent_start = max(0, row_count - 56)
    recent_end = max(recent_start + 4, row_count - 2)
    objects: list[dict[str, Any]] = []

    poi_anchor = _active_poi_anchor(index, active_poi)
    if poi_anchor is not None and _visible(poi_anchor, row_count):
        objects.append(_poi_object(poi_anchor))

    structure_anchor = _latest_visible_external_structure(index, row_count)
    if structure_anchor is not None:
        objects.append(_structure_object(structure_anchor))

    target_price = _range_target(active_range, direction)
    range_id = active_range.get("range_id") if isinstance(active_range, Mapping) else None
    if target_price is not None and range_id and str(range_id) in index:
        objects.append(
            {
                "object_type": "liquidity_line",
                "semantic_object_id": f"{range_id}:target_liquidity",
                "timeframe": "15m",
                "label": "BSL" if direction == "bullish" else "SSL",
                "reason": "Certified active-range boundary is the only current model-completion liquidity reference.",
                "kind": "liquidity",
                "direction": direction if direction in {"bullish", "bearish"} else "mixed",
                "price": target_price,
                "start_index": recent_start,
                "end_index": recent_end,
                "line_style": "dotted",
                "evidence_object_ids": [str(range_id)],
                "importance": 2,
            }
        )

    # A projected route is valuable only after a real active POI exists. It is
    # omitted rather than inventing a forecast from an empty watch state.
    if poi_anchor is not None and official_state in _PATH_ALLOWED_STATES and target_price is not None:
        poi_mid = _midpoint(poi_anchor.price_low, poi_anchor.price_high)
        if poi_mid is not None:
            objects.append(
                {
                    "object_type": "path_projection",
                    "semantic_object_id": f"{poi_anchor.object_id}:conditional_path",
                    "timeframe": "15m",
                    "label": "PATH",
                    "reason": "Conditional route from the certified active POI to validated model-completion liquidity.",
                    "kind": "path",
                    "direction": direction if direction in {"bullish", "bearish"} else "mixed",
                    "price_low": poi_mid,
                    "price_high": target_price,
                    "start_index": max(0, row_count - 3),
                    "end_index": row_count + 5,
                    "line_style": "dashed",
                    "evidence_object_ids": [poi_anchor.object_id],
                    "importance": 3,
                }
            )

    return {
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": objects[:4],
        "notes": [
            "Local composer selected only current, evidence-anchored SMC objects.",
            "No generic warning banner, detector firehose, or unsupported path is permitted.",
        ],
    }


_PATH_ALLOWED_STATES = {
    "WATCH_ONLY",
    "WAIT_FOR_POI",
    "WAIT_FOR_RETRACE_TO_SUPPLY",
    "WAIT_FOR_RETRACE_TO_DEMAND",
    "POI_TOUCHED_AWAIT_CONFIRMATION",
    "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY",
    "TRADE_PLAN_READY",
}


def _latest_visible_external_structure(
    index: Mapping[str, AnnotationEvidenceAnchor], row_count: int,
) -> AnnotationEvidenceAnchor | None:
    candidates = [
        anchor
        for anchor in index.values()
        if anchor.evidence_type == "structure"
        and anchor.timeframe == "15m"
        and anchor.structure_scope == "external"
        and _visible(anchor, row_count)
    ]
    return max(candidates, key=lambda anchor: anchor.end_index or -1, default=None)


def _active_poi_anchor(
    index: Mapping[str, AnnotationEvidenceAnchor], active_poi: Mapping[str, Any] | None,
) -> AnnotationEvidenceAnchor | None:
    if not isinstance(active_poi, Mapping):
        return None
    poi_id = active_poi.get("poi_id")
    anchor = index.get(str(poi_id)) if poi_id else None
    if anchor is None or anchor.evidence_type not in {"order_block", "fvg"}:
        return None
    return anchor


def _visible(anchor: AnnotationEvidenceAnchor, row_count: int) -> bool:
    return anchor.start_index is not None and anchor.end_index is not None and 0 <= anchor.start_index <= anchor.end_index < row_count


def _structure_object(anchor: AnnotationEvidenceAnchor) -> dict[str, Any]:
    kind = str(anchor.kind or "structure").lower()
    label = "CHoCH" if kind == "choch" else "BOS"
    return {
        "object_type": "structure_segment",
        "semantic_object_id": f"{anchor.object_id}:structure_segment",
        "timeframe": anchor.timeframe,
        "label": label,
        "reason": "Latest visible confirmed external structure break, anchored from protected swing to confirmation candle.",
        "kind": kind if kind in {"bos", "choch"} else "structure",
        "direction": anchor.direction or "unknown",
        "price": anchor.exact_price,
        "start_index": anchor.start_index,
        "end_index": anchor.end_index,
        "start_time": anchor.start_time,
        "end_time": anchor.end_time,
        "structure_scope": "external",
        "line_style": "solid",
        "evidence_object_ids": [anchor.object_id],
        "importance": 1,
    }


def _poi_object(anchor: AnnotationEvidenceAnchor) -> dict[str, Any]:
    label = "OB" if anchor.evidence_type == "order_block" else "FVG"
    return {
        "object_type": "poi_zone",
        "semantic_object_id": f"{anchor.object_id}:poi_zone",
        "timeframe": anchor.timeframe,
        "label": label,
        "reason": "Certified active POI bounded to its source and confirmation candles.",
        "kind": anchor.evidence_type,
        "direction": anchor.direction or "unknown",
        "price_low": anchor.price_low,
        "price_high": anchor.price_high,
        "start_index": anchor.start_index,
        "end_index": anchor.end_index,
        "start_time": anchor.start_time,
        "end_time": anchor.end_time,
        "line_style": "solid",
        "evidence_object_ids": [anchor.object_id],
        "importance": 1,
    }


def _range_target(active_range: Mapping[str, Any], direction: str) -> float | None:
    value = active_range.get("high") if direction == "bullish" else active_range.get("low") if direction == "bearish" else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _midpoint(low: float | None, high: float | None) -> float | None:
    if low is None or high is None:
        return None
    return (float(low) + float(high)) / 2.0
