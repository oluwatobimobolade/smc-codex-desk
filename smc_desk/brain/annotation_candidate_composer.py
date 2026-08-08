"""Conservative local composer for professional SMC annotation_plan_v2.

This is deliberately a selector, not a second detector. It chooses a handful
of already-certified objects that are visible in the execution chart and lets
the validator reject anything that drifts from those anchors.
"""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.brain.annotation_evidence import AnnotationEvidenceAnchor, build_annotation_evidence_index, observed_poi_state


def select_local_active_poi(
    *,
    evidence_pack: Mapping[str, Any],
    direction: str,
    active_range: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Choose a confirmed untouched watch POI without creating trade readiness."""
    if direction not in {"bullish", "bearish"}:
        return None
    index = build_annotation_evidence_index(evidence_pack)
    windows = evidence_pack.get("ohlcv_windows") or {}
    candles = windows.get("15m") if isinstance(windows, Mapping) else None
    if not isinstance(candles, list) or not candles:
        return None
    current_price = _float((candles[-1] or {}).get("close")) if isinstance(candles[-1], Mapping) else None
    if current_price is None:
        return None
    row_count = len(candles)
    range_low = _float(active_range.get("low"))
    range_high = _float(active_range.get("high"))
    candidates: list[tuple[AnnotationEvidenceAnchor, str]] = []
    for anchor in index.values():
        if not (
            anchor.evidence_type in {"order_block", "fvg"}
            and anchor.timeframe == "15m"
            and anchor.direction == direction
            and anchor.confirmation_status == "confirmed"
            and not anchor.is_wick_only_probe
            and anchor.activity_status != "terminal"
            and anchor.mitigation_status not in {"full", "invalidated"}
            and _visible(anchor, row_count)
            and _on_retrace_side(anchor, current_price, direction)
            and _inside_range(anchor, range_low, range_high)
        ):
            continue
        observed_state = observed_poi_state(anchor, evidence_pack)
        if observed_state in {"consumed", "invalidated", "unverifiable"}:
            continue
        candidates.append((anchor, observed_state))
    if not candidates:
        return None
    selected, observed_state = min(candidates, key=lambda item: _poi_rank(item[0], current_price, direction))
    label = "demand order block" if direction == "bullish" else "supply order block"
    if selected.evidence_type == "fvg":
        label = f"{direction} FVG"
    freshness = "partially_mitigated" if observed_state == "partial" or selected.mitigation_status == "partial" else "fresh"
    return {
        "poi_id": selected.object_id,
        "timeframe": selected.timeframe,
        "kind": label.replace(" ", "_"),
        "direction": direction,
        "price_low": selected.price_low,
        "price_high": selected.price_high,
        "freshness": freshness,
        "evidence_object_ids": [selected.object_id],
        "summary": (
            f"Observe-only {selected.timeframe} {label} selected from confirmed, non-terminal evidence; observed lifecycle={freshness}. "
            "It is a watch POI only; no entry, stop, target, or execution authority is created."
        ),
    }


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
    recent_start = max(0, row_count - 28)
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
        and anchor.confirmation_status == "confirmed"
        and not anchor.is_wick_only_probe
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
    if anchor.confirmation_status != "confirmed" or anchor.activity_status == "terminal":
        return None
    if anchor.mitigation_status in {"full", "invalidated"}:
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


def _on_retrace_side(anchor: AnnotationEvidenceAnchor, current_price: float, direction: str) -> bool:
    if anchor.price_low is None or anchor.price_high is None:
        return False
    tolerance = abs(current_price) * 0.001
    if direction == "bullish":
        return anchor.price_low <= current_price + tolerance
    return anchor.price_high >= current_price - tolerance


def _inside_range(anchor: AnnotationEvidenceAnchor, range_low: float | None, range_high: float | None) -> bool:
    if range_low is None or range_high is None or anchor.price_low is None or anchor.price_high is None:
        return True
    return anchor.price_low >= range_low and anchor.price_high <= range_high


def _poi_rank(anchor: AnnotationEvidenceAnchor, current_price: float, direction: str) -> tuple[float, ...]:
    midpoint = _midpoint(anchor.price_low, anchor.price_high) or current_price
    kind_rank = 0.0 if anchor.evidence_type == "order_block" else 1.0
    freshness_rank = 0.0 if anchor.mitigation_status in {None, "untouched"} else 1.0
    confidence_rank = -float(anchor.confidence or 0.0)
    # Within the same quality tier, preserve deeper-OB priority before distance.
    depth_rank = midpoint if direction == "bullish" else -midpoint
    distance_rank = abs(current_price - midpoint)
    recency_rank = -float(anchor.end_index or 0)
    return kind_rank, freshness_rank, confidence_rank, depth_rank, distance_rank, recency_rank


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
