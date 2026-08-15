"""Conservative local composer for professional SMC annotation_plan_v2.

This is deliberately a selector, not a second detector. It chooses a handful
of already-certified objects that are visible in the execution chart and lets
the validator reject anything that drifts from those anchors.
"""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.brain.annotation_evidence import (
    AnnotationEvidenceAnchor,
    build_annotation_evidence_index,
    index_for_time,
    observed_poi_state,
)
from smc_desk.brain.annotation_geometry import build_geometry_contract
from smc_desk.brain.annotation_semantics import certified_annotation_semantic
from smc_desk.perception.evidence_contract import contract_ids_for_object


def select_local_active_poi(
    *,
    evidence_pack: Mapping[str, Any],
    direction: str,
    active_range: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Choose a confirmed untouched watch POI without creating trade readiness."""
    if direction not in {"bullish", "bearish"}:
        return None
    authority = evidence_pack.get("causal_poi_authority")
    if isinstance(authority, Mapping) and (authority.get("authority_contract") or {}).get("enforcement_ready") is True:
        selected = _authority_active_poi(authority, direction)
        if not _poi_link_survives_episode_graph(evidence_pack, selected):
            return None
        # linked_break_id is causal-authority evidence used to validate the
        # selection, not a field in the canonical ActivePOI decision schema.
        # Preserve the linkage through evidence_object_ids and never leak the
        # authority's wider internal record into the strict AI decision.
        decision_poi = dict(selected or {})
        linked_break_id = str(decision_poi.pop("linked_break_id", "") or "")
        evidence_ids = [str(item) for item in decision_poi.get("evidence_object_ids", []) if item]
        if linked_break_id and linked_break_id not in evidence_ids:
            evidence_ids.append(linked_break_id)
        decision_poi["evidence_object_ids"] = evidence_ids
        return decision_poi
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
    recent_start = max(0, row_count - 14)
    recent_end = max(recent_start + 4, row_count - 2)
    objects: list[dict[str, Any]] = []

    poi_anchor = _active_poi_anchor(index, active_poi)
    poi_is_scenario_watch = False
    if poi_anchor is None and official_state in {"THESIS_ONLY", "WATCH_ONLY", "REVIEW_REQUIRED"}:
        scenario_poi = _best_visible_scenario_poi(evidence_pack, index)
        poi_anchor = _active_poi_anchor(index, scenario_poi)
        poi_is_scenario_watch = poi_anchor is not None
    if poi_anchor is not None and _visible_on_chart(poi_anchor, evidence_pack, "15m"):
        objects.append(_poi_object(poi_anchor, evidence_pack=evidence_pack, scenario_watch=poi_is_scenario_watch))

    for structure_anchor in _material_structure_anchors(evidence_pack, index, row_count):
        objects.append(_structure_object(structure_anchor, evidence_pack=evidence_pack))

    target_price = _range_target(active_range, direction)
    range_id = active_range.get("range_id") if isinstance(active_range, Mapping) else None
    source_span = _active_range_source_span(evidence_pack) if target_price is not None and range_id else None
    if target_price is not None and range_id and str(range_id) in index and source_span is not None:
        evidence_geometry = {
            **source_span,
            "price": target_price,
            "price_low": None,
            "price_high": None,
        }
        display_geometry = {
            "start_index": recent_start,
            "end_index": recent_end,
            "start_time": None,
            "end_time": None,
            "price": target_price,
            "price_low": None,
            "price_high": None,
        }
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
                "evidence_contract_ids": _contract_ids(evidence_pack, [str(range_id)], timeframe=None),
                **build_geometry_contract(
                    evidence=evidence_geometry,
                    display=display_geometry,
                    source_object_ids=[str(range_id)],
                    anchor_mode="derived_level",
                    clipping_rule="local_span_max_12_bars",
                ),
                "importance": 2,
            }
        )

    # A projected route is valuable only after a real active POI exists. It is
    # omitted rather than inventing a forecast from an empty watch state.
    if poi_anchor is not None and official_state in _PATH_ALLOWED_STATES and target_price is not None and range_id:
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
                    "evidence_object_ids": [poi_anchor.object_id, str(range_id)],
                    "evidence_contract_ids": [
                        *_contract_ids(evidence_pack, [poi_anchor.object_id], timeframe=poi_anchor.timeframe),
                        *_contract_ids(evidence_pack, [str(range_id)], timeframe=None),
                    ],
                    **build_geometry_contract(
                        evidence={
                            "start_index": max(0, row_count - 3),
                            "end_index": row_count + 5,
                            "start_time": None,
                            "end_time": None,
                            "price": None,
                            "price_low": poi_mid,
                            "price_high": target_price,
                        },
                        source_object_ids=[poi_anchor.object_id, str(range_id)],
                        anchor_mode="conditional_projection",
                        clipping_rule="conditional_projection",
                    ),
                    "importance": 3,
                }
            )

    return {
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": objects[:4],
        "notes": [
            "Local composer selected current, evidence-anchored SMC objects, including a scenario POI when execution is not ready.",
            "No generic warning banner, detector firehose, or unsupported path is permitted.",
            "Scenario POIs are route-map information only and never create entry, stop, target, risk, or execution authority.",
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


def _material_structure_anchors(
    evidence_pack: Mapping[str, Any],
    index: Mapping[str, AnnotationEvidenceAnchor],
    row_count: int,
) -> list[AnnotationEvidenceAnchor]:
    """Select the controlling and execution breaks, not a detector firehose."""
    episode_graph = evidence_pack.get("formal_causal_episode_graph") or {}
    episode_nodes = episode_graph.get("timeframes") if isinstance(episode_graph, Mapping) else None
    episode_contract = episode_graph.get("authority_contract") if isinstance(episode_graph, Mapping) else {}
    if isinstance(episode_nodes, Mapping) and isinstance(episode_contract, Mapping) and episode_contract.get("enforcement_ready") is True:
        selected_from_episode_graph: list[AnnotationEvidenceAnchor] = []
        for timeframe in ("1h", "15m"):
            episode_node = episode_nodes.get(timeframe)
            if not isinstance(episode_node, Mapping):
                continue
            for key, required_scope in (
                ("latest_external_episode", "external"),
                ("latest_internal_episode", "internal"),
            ):
                episode = episode_node.get(key)
                object_id = episode.get("structure_event_id") if isinstance(episode, Mapping) else None
                anchor = index.get(str(object_id)) if object_id else None
                if _material_structure_anchor_is_visible(anchor, evidence_pack, required_scope=required_scope):
                    selected_from_episode_graph.append(anchor)
                    break
        if selected_from_episode_graph:
            unique_episode_anchors: dict[str, AnnotationEvidenceAnchor] = {}
            for anchor in selected_from_episode_graph:
                unique_episode_anchors.setdefault(anchor.object_id, anchor)
            return list(unique_episode_anchors.values())[:2]
        # V2 graph exists but accepted no visible event. Do not silently revive
        # a V1 break that the stricter lifecycle challenged.
        return []

    graph = evidence_pack.get("formal_structure_graph") or {}
    nodes = graph.get("timeframes") if isinstance(graph, Mapping) else {}
    selected: list[AnnotationEvidenceAnchor] = []
    for timeframe in ("1h", "15m"):
        node = nodes.get(timeframe) if isinstance(nodes, Mapping) else None
        summary = node.get("latest_external_break") if isinstance(node, Mapping) else None
        object_id = summary.get("object_id") if isinstance(summary, Mapping) else None
        anchor = index.get(str(object_id)) if object_id else None
        if _material_structure_anchor_is_visible(anchor, evidence_pack, required_scope="external"):
            selected.append(anchor)
            continue
        narrative = evidence_pack.get("structure_narrative") or {}
        narrative_nodes = narrative.get("timeframes") if isinstance(narrative, Mapping) else {}
        narrative_node = narrative_nodes.get(timeframe) if isinstance(narrative_nodes, Mapping) else None
        internal_id = narrative_node.get("latest_internal_break_id") if isinstance(narrative_node, Mapping) else None
        internal_anchor = index.get(str(internal_id)) if internal_id else None
        if _material_structure_anchor_is_visible(internal_anchor, evidence_pack, required_scope="internal"):
            selected.append(internal_anchor)
    if not selected:
        fallback = _latest_visible_external_structure(index, row_count)
        if fallback is not None:
            selected.append(fallback)
    unique: dict[str, AnnotationEvidenceAnchor] = {}
    for anchor in selected:
        unique.setdefault(anchor.object_id, anchor)
    return list(unique.values())[:2]


def _material_structure_anchor_is_visible(
    anchor: AnnotationEvidenceAnchor | None,
    evidence_pack: Mapping[str, Any],
    *,
    required_scope: str,
) -> bool:
    return bool(
        anchor is not None
        and anchor.evidence_type == "structure"
        and anchor.structure_scope == required_scope
        and anchor.confirmation_status == "confirmed"
        and not anchor.is_wick_only_probe
        and _visible_on_chart(anchor, evidence_pack, "15m")
    )


def _active_poi_anchor(
    index: Mapping[str, AnnotationEvidenceAnchor], active_poi: Mapping[str, Any] | None,
) -> AnnotationEvidenceAnchor | None:
    if not isinstance(active_poi, Mapping):
        return None
    ids = [active_poi.get("poi_id"), *(active_poi.get("evidence_object_ids") or [])]
    anchor = next((
        candidate
        for object_id in ids
        if object_id
        and (candidate := index.get(str(object_id))) is not None
        and candidate.evidence_type in {"order_block", "fvg"}
    ), None)
    if anchor is None:
        return None
    if anchor.confirmation_status != "confirmed" or anchor.activity_status == "terminal":
        return None
    if anchor.mitigation_status in {"full", "invalidated"}:
        return None
    return anchor


def _visible(anchor: AnnotationEvidenceAnchor, row_count: int) -> bool:
    return anchor.start_index is not None and anchor.end_index is not None and 0 <= anchor.start_index <= anchor.end_index < row_count


def _visible_on_chart(
    anchor: AnnotationEvidenceAnchor, evidence_pack: Mapping[str, Any], chart_timeframe: str,
) -> bool:
    if anchor.start_time is None or anchor.end_time is None:
        return False
    start = index_for_time(evidence_pack, chart_timeframe, anchor.start_time)
    end = index_for_time(evidence_pack, chart_timeframe, anchor.end_time)
    return start is not None and end is not None


def _structure_object(
    anchor: AnnotationEvidenceAnchor, *, evidence_pack: Mapping[str, Any]
) -> dict[str, Any]:
    semantic = certified_annotation_semantic(anchor)
    scope = anchor.structure_scope if anchor.structure_scope in {"external", "internal"} else "external"
    episode_event_type = _episode_event_type(
        evidence_pack, anchor.object_id, timeframe=anchor.timeframe
    )
    label, kind, line_style = _episode_annotation_semantic(
        episode_event_type,
        fallback_label=semantic.label,
        fallback_kind=semantic.kind,
        fallback_line_style=semantic.line_style,
        scope=scope,
    )
    display_label = f"{anchor.timeframe.upper()} {label}" if anchor.timeframe != "15m" else label
    start_index = anchor.start_index if anchor.timeframe == "15m" else None
    end_index = anchor.end_index if anchor.timeframe == "15m" else None
    start_time = anchor.start_time
    end_time = anchor.end_time
    if start_index is not None and end_index is not None and end_index - start_index > 18:
        start_index = end_index - 18
        # Index geometry is now an intentional confirmation-side visual clip;
        # source swing and confirmation timestamps remain in the evidence anchor.
        start_time = None
        end_time = None
    elif anchor.timeframe != "15m" and start_time and end_time:
        projected_start = index_for_time(evidence_pack, "15m", start_time)
        projected_end = index_for_time(evidence_pack, "15m", end_time)
        windows = evidence_pack.get("ohlcv_windows") or {}
        chart_window = windows.get("15m") if isinstance(windows, Mapping) else None
        if (
            projected_start is not None
            and projected_end is not None
            and projected_end - projected_start > 18
            and isinstance(chart_window, list)
        ):
            clipped = chart_window[max(projected_start, projected_end - 18)]
            if isinstance(clipped, Mapping) and clipped.get("timestamp"):
                start_time = str(clipped["timestamp"])
    evidence_geometry = {
        "start_index": anchor.start_index,
        "end_index": anchor.end_index,
        "start_time": anchor.start_time,
        "end_time": anchor.end_time,
        "price": anchor.exact_price,
        "price_low": None,
        "price_high": None,
    }
    display_geometry = {
        "start_index": start_index,
        "end_index": end_index,
        "start_time": start_time,
        "end_time": end_time,
        "price": anchor.exact_price,
        "price_low": None,
        "price_high": None,
    }
    was_clipped = any(
        evidence_geometry[key] != display_geometry[key]
        for key in ("start_index", "end_index", "start_time", "end_time")
    )
    return {
        "object_type": "structure_segment",
        "semantic_object_id": f"{anchor.object_id}:structure_segment",
        "timeframe": anchor.timeframe,
        "label": display_label,
        "reason": (
            "Latest visible confirmed external structure break, anchored from protected swing to confirmation candle."
            if scope == "external"
            else "Latest visible internal structure shift; it times the pullback but cannot flip parent structure."
        ),
        "kind": kind,
        "direction": anchor.direction or "unknown",
        "price": anchor.exact_price,
        # HTF origin indices belong to their own candle arrays. The 15m
        # renderer maps them by timestamp so they cannot drift to a wrong bar.
        "start_index": start_index,
        "end_index": end_index,
        "start_time": start_time,
        "end_time": end_time,
        "structure_scope": scope,
        "line_style": line_style,
        "evidence_object_ids": [anchor.object_id],
        "evidence_contract_ids": _contract_ids(evidence_pack, [anchor.object_id], timeframe=anchor.timeframe),
        **build_geometry_contract(
            evidence=evidence_geometry,
            display=display_geometry,
            source_object_ids=[anchor.object_id],
            anchor_mode="exact_source",
            clipping_rule="confirmation_side_max_18_bars" if was_clipped else "none",
        ),
        "importance": 1,
    }


def _episode_event_type(
    evidence_pack: Mapping[str, Any], object_id: str, *, timeframe: str
) -> str | None:
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    timeframes = graph.get("timeframes") if isinstance(graph, Mapping) else None
    node = timeframes.get(timeframe) if isinstance(timeframes, Mapping) else None
    for episode in node.get("episodes", []) or [] if isinstance(node, Mapping) else []:
        if isinstance(episode, Mapping) and str(episode.get("structure_event_id") or "") == object_id:
            return str(episode.get("event_type") or "") or None
    return None


def _episode_annotation_semantic(
    event_type: str | None,
    *,
    fallback_label: str,
    fallback_kind: str,
    fallback_line_style: str,
    scope: str,
) -> tuple[str, str, str]:
    token = str(event_type or "")
    if token == "INITIAL_DIRECTION_BREAK":
        return "Initial Break", "structure", "solid"
    if "MSS" in token:
        return "MSS", "structure", "solid"
    if "CHOCH" in token:
        return ("Internal CHoCH" if scope == "internal" else "CHoCH", "choch", "dashed" if scope == "internal" else "solid")
    if "BOS" in token:
        return ("Internal BOS" if scope == "internal" else "BOS", "bos", "dashed" if scope == "internal" else "solid")
    return fallback_label, fallback_kind, fallback_line_style


def _poi_object(
    anchor: AnnotationEvidenceAnchor,
    *,
    evidence_pack: Mapping[str, Any],
    scenario_watch: bool = False,
) -> dict[str, Any]:
    semantic = certified_annotation_semantic(anchor)
    geometry = {
        "start_index": anchor.start_index,
        "end_index": anchor.end_index,
        "start_time": anchor.start_time,
        "end_time": anchor.end_time,
        "price": None,
        "price_low": anchor.price_low,
        "price_high": anchor.price_high,
    }
    return {
        "object_type": "poi_zone",
        "semantic_object_id": f"{anchor.object_id}:poi_zone",
        "timeframe": anchor.timeframe,
        "label": semantic.label,
        "reason": (
            "Causally selected scenario watch POI bounded to its source and confirmation candles; no trade is authorized."
            if scenario_watch
            else "Certified active POI bounded to its source and confirmation candles."
        ),
        "kind": semantic.kind,
        "direction": anchor.direction or "unknown",
        "price_low": anchor.price_low,
        "price_high": anchor.price_high,
        "start_index": anchor.start_index,
        "end_index": anchor.end_index,
        "start_time": anchor.start_time,
        "end_time": anchor.end_time,
        "line_style": semantic.line_style,
        "evidence_object_ids": [anchor.object_id],
        "evidence_contract_ids": _contract_ids(evidence_pack, [anchor.object_id], timeframe=anchor.timeframe),
        **build_geometry_contract(
            evidence=geometry,
            source_object_ids=[anchor.object_id],
            anchor_mode="exact_source",
        ),
        "importance": 1,
    }


def _active_range_source_span(evidence_pack: Mapping[str, Any]) -> dict[str, Any] | None:
    authority = evidence_pack.get("active_range_authority") or {}
    selected = authority.get("selected_range") if isinstance(authority, Mapping) else None
    selected = selected if isinstance(selected, Mapping) else authority
    pivots = selected.get("source_pivots") if isinstance(selected, Mapping) else None
    if not isinstance(pivots, list) or len(pivots) < 2:
        return None
    times = sorted(
        str(pivot.get("timestamp"))
        for pivot in pivots
        if isinstance(pivot, Mapping) and pivot.get("timestamp")
    )
    if len(times) < 2:
        return None
    return {
        "start_index": index_for_time(evidence_pack, "15m", times[0]),
        "end_index": index_for_time(evidence_pack, "15m", times[-1]),
        "start_time": times[0],
        "end_time": times[-1],
    }


def _contract_ids(
    evidence_pack: Mapping[str, Any],
    object_ids: list[str],
    *,
    timeframe: str | None,
) -> list[str]:
    registry = evidence_pack.get("object_evidence_contracts") or {}
    contract_ids: list[str] = []
    for object_id in object_ids:
        matches = contract_ids_for_object(registry, object_id, timeframe=timeframe)
        if not matches and timeframe is not None:
            matches = contract_ids_for_object(registry, object_id)
        contract_ids.extend(matches)
    return list(dict.fromkeys(contract_ids))


def _best_visible_scenario_poi(
    evidence_pack: Mapping[str, Any], index: Mapping[str, AnnotationEvidenceAnchor],
) -> dict[str, Any] | None:
    authority = evidence_pack.get("causal_poi_authority") or {}
    scenarios = authority.get("scenarios") if isinstance(authority, Mapping) else None
    if not isinstance(scenarios, Mapping):
        return None
    candidates: list[dict[str, Any]] = []
    for direction in ("bullish", "bearish"):
        poi = _authority_active_poi(authority, direction)
        anchor = _active_poi_anchor(index, poi)
        if (
            poi is not None
            and _poi_link_survives_episode_graph(evidence_pack, poi)
            and anchor is not None
            and _visible_on_chart(anchor, evidence_pack, "15m")
        ):
            candidates.append(poi)
    if not candidates:
        return None
    timeframe_rank = {"15m": 0, "1h": 1, "4h": 2, "1d": 3, "5m": 4}
    candidates.sort(key=lambda item: (timeframe_rank.get(str(item.get("timeframe") or ""), 9), str(item.get("poi_id") or "")))
    return candidates[0]


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
    confidence_rank = -float(anchor.evidence_strength or 0.0)
    # Within the same quality tier, preserve deeper-OB priority before distance.
    depth_rank = midpoint if direction == "bullish" else -midpoint
    distance_rank = abs(current_price - midpoint)
    recency_rank = -float(anchor.end_index or 0)
    return kind_rank, freshness_rank, confidence_rank, depth_rank, distance_rank, recency_rank


def _authority_active_poi(authority: Mapping[str, Any], direction: str) -> dict[str, Any] | None:
    scenarios = authority.get("scenarios") or {}
    scenario = scenarios.get(direction) if isinstance(scenarios, Mapping) else None
    if not isinstance(scenario, Mapping) or scenario.get("status") != "SELECTED":
        return None
    primary = scenario.get("primary_causal_poi")
    if not isinstance(primary, Mapping):
        return None
    source_id = str(primary.get("source_object_id") or "")
    poi_id = str(primary.get("poi_id") or source_id)
    kind = "order_block" if primary.get("kind") == "order_block" else "fvg"
    refinements = scenario.get("execution_refinements") or []
    refinement_ids = [
        str(item.get("source_object_id") or item.get("poi_id"))
        for item in refinements
        if isinstance(item, Mapping) and (item.get("source_object_id") or item.get("poi_id"))
    ]
    return {
        "poi_id": poi_id,
        "timeframe": primary.get("timeframe") or scenario.get("controlling_timeframe"),
        "kind": kind,
        "direction": direction,
        "price_low": primary.get("price_low"),
        "price_high": primary.get("price_high"),
        "freshness": primary.get("freshness"),
        "linked_break_id": primary.get("linked_break_id") or scenario.get("accepted_break_id"),
        "evidence_object_ids": [source_id, *refinement_ids] if source_id else refinement_ids,
        "summary": (
            f"{primary.get('timeframe')} {kind} selected as {primary.get('lineage_role')} by causal POI authority. "
            f"Range location={primary.get('range_location')}; lifecycle={primary.get('freshness')}. "
            f"{len(refinement_ids)} lower-timeframe refinement(s) are subordinate. "
            "This is the best evidenced watch POI, not a guaranteed reaction or execution instruction."
        ),
    }


def _poi_link_survives_episode_graph(
    evidence_pack: Mapping[str, Any], poi: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(poi, Mapping):
        return False
    graph = evidence_pack.get("formal_causal_episode_graph")
    if not isinstance(graph, Mapping):
        return True
    contract = graph.get("authority_contract") or {}
    if not isinstance(contract, Mapping) or contract.get("enforcement_ready") is not True:
        return True
    linked_break_id = str(poi.get("linked_break_id") or "")
    if not linked_break_id:
        return False
    timeframe = str(poi.get("timeframe") or "")
    if not timeframe:
        return False
    timeframes = graph.get("timeframes") or {}
    node = timeframes.get(timeframe) if isinstance(timeframes, Mapping) else None
    for episode in node.get("episodes", []) or [] if isinstance(node, Mapping) else []:
        if isinstance(episode, Mapping) and str(episode.get("structure_event_id") or "") == linked_break_id:
            return True
    return False


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
