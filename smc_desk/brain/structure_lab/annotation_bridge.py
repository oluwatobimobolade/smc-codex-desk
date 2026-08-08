"""Resolve AI semantic annotation selections into certified V2 geometry.

The AI chooses what matters. This module owns every price and timestamp used by
the renderer, so a semantic selection cannot move or invent chart geometry.
"""
from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from smc_desk.brain.ai_smc_trader_brain import AnnotationPlanV2
from smc_desk.brain.annotation_evidence import (
    AnnotationEvidenceAnchor,
    build_annotation_evidence_index,
)
from smc_desk.brain.annotation_semantics import certified_annotation_semantic


def resolve_semantic_annotation_plan(
    semantic_plan: Mapping[str, Any],
    evidence_pack: Mapping[str, Any],
) -> dict[str, Any]:
    selections = semantic_plan.get("selections") or []
    hidden = {str(value) for value in semantic_plan.get("hidden_evidence_ids") or []}
    clutter_budget = int(semantic_plan.get("clutter_budget") or 0)
    evidence = build_annotation_evidence_index(evidence_pack)
    issues: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    label_overrides: list[dict[str, str]] = []

    if not isinstance(selections, list):
        selections = []
        _issue(issues, "selections_not_list", "AI annotation selections must be a list.")
    if not selections:
        _issue(issues, "empty_semantic_plan", "The AI selected no objects, so no professional annotation can be certified.")
    if clutter_budget < 1 or clutter_budget > 12:
        _issue(issues, "invalid_clutter_budget", "clutter_budget must be between 1 and 12.")
    if clutter_budget and len(selections) > clutter_budget:
        _issue(
            issues,
            "semantic_object_budget_exceeded",
            f"The AI selected {len(selections)} objects against a clutter budget of {clutter_budget}.",
        )

    for selection in selections:
        if not isinstance(selection, Mapping):
            _issue(issues, "invalid_selection", "Every semantic selection must be an object.")
            continue
        evidence_id = str(selection.get("semantic_object_id") or "")
        if not evidence_id:
            _issue(issues, "selection_missing_evidence_id", "A semantic selection omitted semantic_object_id.")
            continue
        if evidence_id in hidden:
            _issue(issues, "selected_object_marked_hidden", f"{evidence_id} is both selected and hidden.")
            continue
        anchor = evidence.get(evidence_id)
        if anchor is None:
            _issue(issues, "unresolved_semantic_object", f"No certified annotation anchor exists for {evidence_id}.")
            continue
        timeframe = str(selection.get("timeframe") or "")
        if timeframe != anchor.timeframe:
            _issue(
                issues,
                "selection_timeframe_mismatch",
                f"{evidence_id} belongs to {anchor.timeframe}, not {timeframe or 'unspecified'}.",
            )
            continue
        if anchor.is_wick_only_probe or anchor.confirmation_status not in {None, "confirmed"}:
            _issue(issues, "uncertified_semantic_object", f"{evidence_id} is not a confirmed drawable object.")
            continue
        resolved = _resolve_selection(selection, anchor, evidence_pack, issues, label_overrides)
        if resolved is not None:
            objects.append(resolved)

    plan_payload = {
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": objects,
        "notes": [
            "AI selected semantic objects; deterministic evidence anchors supplied all geometry.",
            "No full-width structure ray, unsupported POI, trade box, or detector firehose is allowed.",
        ],
    }
    try:
        validated_plan = AnnotationPlanV2.model_validate(plan_payload).model_dump(mode="json", by_alias=True)
    except ValidationError as exc:
        _issue(issues, "resolved_plan_schema_failure", str(exc))
        validated_plan = plan_payload

    resolved_ids = [str(obj.get("semantic_object_id")) for obj in objects]
    planned_ids = [
        str(item.get("semantic_object_id"))
        for item in selections
        if isinstance(item, Mapping) and item.get("semantic_object_id")
    ]
    status = "PASS" if not issues and len(objects) == len(selections) and bool(objects) else "REVIEW_REQUIRED"
    return {
        "schema": "semantic_annotation_geometry_resolution_v1",
        "status": status,
        "planned_selection_count": len(selections),
        "resolved_object_count": len(objects),
        "planned_evidence_ids": planned_ids,
        "resolved_semantic_object_ids": resolved_ids,
        "hidden_evidence_ids": sorted(hidden),
        "timeframes": sorted({str(obj.get("timeframe")) for obj in objects}),
        "issues": issues,
        "label_overrides": label_overrides,
        "label_authority": "deterministic_annotation_semantics_v1",
        "annotation_plan_v2": validated_plan,
        "geometry_authority": "certified_evidence_resolver",
        "ai_geometry_authority": False,
        "trade_box_allowed": False,
    }


def _resolve_selection(
    selection: Mapping[str, Any],
    anchor: AnnotationEvidenceAnchor,
    evidence_pack: Mapping[str, Any],
    issues: list[dict[str, Any]],
    label_overrides: list[dict[str, str]],
) -> dict[str, Any] | None:
    object_type = str(selection.get("object_type") or "")
    semantic = certified_annotation_semantic(anchor)
    requested_label = str(selection.get("label") or "").strip()
    if requested_label and requested_label != semantic.label:
        label_overrides.append({
            "semantic_object_id": anchor.object_id,
            "requested_label": requested_label,
            "certified_label": semantic.label,
        })
    base = {
        "semantic_object_id": anchor.object_id,
        "timeframe": anchor.timeframe,
        "label": semantic.label,
        "reason": str(selection.get("reason") or "Certified evidence selected by the AI annotation planner."),
        "direction": anchor.direction or "unknown",
        "evidence_object_ids": [anchor.object_id],
        "importance": min(3, max(1, int(selection.get("priority") or 2))),
    }
    if object_type == "structure_segment":
        if anchor.evidence_type != "structure" or anchor.exact_price is None:
            _issue(issues, "structure_selection_without_break", f"{anchor.object_id} is not certified structure-break evidence.")
            return None
        if not _has_visible_span(anchor):
            _issue(issues, "structure_geometry_outside_window", f"{anchor.object_id} is outside its visible timeframe window.")
            return None
        kind = semantic.kind
        subordinate = any(
            token in f"{base['label']} {base['reason']}".lower()
            for token in ("stale", "child", "recovery", "pullback")
        )
        return {
            **base,
            "object_type": "structure_segment",
            "kind": kind,
            "price": anchor.exact_price,
            "start_index": anchor.start_index,
            "end_index": anchor.end_index,
            "start_time": anchor.start_time,
            "end_time": anchor.end_time,
            "line_style": "dashed" if subordinate else semantic.line_style,
            "structure_scope": anchor.structure_scope or "external",
        }
    if object_type == "liquidity_line":
        if anchor.evidence_type not in {"liquidity", "swing_pivot", "active_range"} or anchor.exact_price is None:
            _issue(issues, "liquidity_selection_without_level", f"{anchor.object_id} is not a certified scalar liquidity reference.")
            return None
        span = _local_span(evidence_pack, anchor)
        if span is None:
            _issue(issues, "liquidity_geometry_outside_window", f"{anchor.object_id} is outside its visible timeframe window.")
            return None
        start_index, end_index, start_time, end_time = span
        return {
            **base,
            "object_type": "liquidity_line",
            "kind": semantic.kind,
            "price": anchor.exact_price,
            "start_index": start_index,
            "end_index": end_index,
            "start_time": start_time,
            "end_time": end_time,
            "line_style": semantic.line_style,
        }
    if object_type == "range_zone":
        if anchor.evidence_type != "active_range" or anchor.price_low is None or anchor.price_high is None:
            _issue(issues, "range_selection_without_certified_range",
                   f"{anchor.object_id} is not a certified active-range anchor.")
            return None
        span = _window_span(evidence_pack, anchor)
        if span is None:
            _issue(issues, "range_geometry_outside_window",
                   f"{anchor.object_id} has no visible window to span.")
            return None
        start_index, end_index, start_time, end_time = span
        low = min(anchor.price_low, anchor.price_high)
        high = max(anchor.price_low, anchor.price_high)
        return {
            **base,
            "object_type": "range_zone",
            "kind": "range",
            "price_low": low,
            "price_high": high,
            # Equilibrium is derived here, never supplied by the planner.
            "equilibrium_price": (low + high) / 2.0,
            "start_index": start_index,
            "end_index": end_index,
            "start_time": start_time,
            "end_time": end_time,
            "line_style": "dashed",
        }
    if object_type == "sweep_marker":
        if anchor.evidence_type not in {"sweep", "liquidity", "swing_pivot"} or anchor.exact_price is None:
            _issue(issues, "sweep_selection_without_event",
                   f"{anchor.object_id} is not a certified sweep or liquidity interaction.")
            return None
        span = _local_span(evidence_pack, anchor, minimum_width=3)
        if span is None:
            _issue(issues, "sweep_geometry_outside_window",
                   f"{anchor.object_id} is outside its visible timeframe window.")
            return None
        start_index, end_index, start_time, end_time = span
        return {
            **base,
            "object_type": "sweep_marker",
            "kind": "sweep",
            "price": anchor.exact_price,
            "start_index": start_index,
            "end_index": end_index,
            "start_time": start_time,
            "end_time": end_time,
            "line_style": "solid",
        }
    if object_type == "equal_levels":
        if anchor.evidence_type != "liquidity" or anchor.exact_price is None:
            _issue(issues, "equal_levels_without_liquidity_cluster",
                   f"{anchor.object_id} is not a certified equal-highs/lows cluster.")
            return None
        span = _local_span(evidence_pack, anchor)
        if span is None:
            _issue(issues, "equal_levels_geometry_outside_window",
                   f"{anchor.object_id} is outside its visible timeframe window.")
            return None
        start_index, end_index, start_time, end_time = span
        kind = "equal_highs" if (anchor.direction or "").lower() == "bearish" else "equal_lows"
        if anchor.kind in {"equal_highs", "equal_lows"}:
            kind = anchor.kind
        return {
            **base,
            "object_type": "equal_levels",
            "kind": kind,
            "price": anchor.exact_price,
            "start_index": start_index,
            "end_index": end_index,
            "start_time": start_time,
            "end_time": end_time,
            "line_style": "dotted",
        }
    if object_type == "poi_zone":
        if anchor.evidence_type not in {"order_block", "fvg"} or anchor.price_low is None or anchor.price_high is None:
            _issue(issues, "poi_selection_without_zone", f"{anchor.object_id} is not a certified OB/FVG zone.")
            return None
        span = _local_span(evidence_pack, anchor, minimum_width=8)
        if span is None:
            _issue(issues, "poi_geometry_outside_window", f"{anchor.object_id} is outside its visible timeframe window.")
            return None
        start_index, end_index, start_time, end_time = span
        return {
            **base,
            "object_type": "poi_zone",
            "kind": semantic.kind,
            "price_low": min(anchor.price_low, anchor.price_high),
            "price_high": max(anchor.price_low, anchor.price_high),
            "start_index": start_index,
            "end_index": end_index,
            "start_time": start_time,
            "end_time": end_time,
            "line_style": semantic.line_style,
        }
    _issue(issues, "unsupported_semantic_object_type", f"{object_type or 'blank'} is not resolvable in the professional renderer.")
    return None


def _has_visible_span(anchor: AnnotationEvidenceAnchor) -> bool:
    return (
        anchor.start_index is not None
        and anchor.end_index is not None
        and anchor.start_time is not None
        and anchor.end_time is not None
        and 0 <= anchor.start_index <= anchor.end_index
    )


def _local_span(
    evidence_pack: Mapping[str, Any],
    anchor: AnnotationEvidenceAnchor,
    *,
    minimum_width: int = 6,
) -> tuple[int, int, str, str] | None:
    windows = evidence_pack.get("ohlcv_windows") or {}
    candles = windows.get(anchor.timeframe) if isinstance(windows, Mapping) else None
    if not isinstance(candles, list) or not candles or anchor.start_index is None or anchor.start_time is None:
        return None
    start = anchor.start_index
    if start < 0 or start >= len(candles):
        return None
    width = max(minimum_width, min(18, int(len(candles) * 0.14)))
    end = min(len(candles) - 1, max(anchor.end_index or start, start + width))
    end_raw = candles[end] if isinstance(candles[end], Mapping) else {}
    end_time = str(end_raw.get("timestamp") or end_raw.get("open_time") or anchor.end_time or anchor.start_time)
    return start, end, anchor.start_time, end_time


def _window_span(
    evidence_pack: Mapping[str, Any],
    anchor: AnnotationEvidenceAnchor,
) -> tuple[int, int, str, str] | None:
    """Full visible-window span, for objects that are context rather than events.

    A dealing range is a horizontal band that governs the whole chart, so it is
    drawn across the visible window instead of anchored to one candle. The
    range carries no pivot timestamp for that reason, which is why the local
    event span cannot resolve it.
    """
    windows = evidence_pack.get("ohlcv_windows") or {}
    candles = windows.get(anchor.timeframe) if isinstance(windows, Mapping) else None
    if not isinstance(candles, list) or not candles:
        return None

    def _stamp(row: Any) -> str:
        if isinstance(row, Mapping):
            return str(row.get("timestamp") or row.get("open_time") or "")
        return ""

    start_time = _stamp(candles[0])
    end_time = _stamp(candles[-1])
    if not start_time or not end_time:
        return None
    return 0, len(candles) - 1, start_time, end_time


def _issue(issues: list[dict[str, Any]], code: str, message: str) -> None:
    issues.append({"code": code, "severity": "hard", "message": message})
