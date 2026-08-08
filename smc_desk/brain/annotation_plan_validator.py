"""Validation for professional AI SMC annotation plans.

The AI is allowed to choose the trader-facing markup, but every drawing object
must remain subordinate to the formal structure graph and detector evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from smc_desk.brain.ai_smc_trader_brain import AISMCDecision, AnnotationDrawingObject
from smc_desk.brain.annotation_evidence import (
    AnnotationEvidenceAnchor,
    build_annotation_evidence_index,
    observed_poi_state,
    prices_match,
    zones_match,
)
from smc_desk.brain.annotation_geometry import GEOMETRY_FIELDS, geometry_hash


@dataclass(frozen=True)
class AnnotationPlanIssue:
    code: str
    message: str
    severity: str = "hard"


@dataclass(frozen=True)
class AnnotationPlanValidation:
    status: str
    issues: list[AnnotationPlanIssue]
    object_count: int


WATCH_STATES = {
    "THESIS_ONLY",
    "WATCH_ONLY",
    "WAIT_FOR_POI",
    "WAIT_FOR_RETRACE_TO_SUPPLY",
    "WAIT_FOR_RETRACE_TO_DEMAND",
    "POI_TOUCHED_AWAIT_CONFIRMATION",
    "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY",
    "MISSED_TRADE_NO_CHASE",
    "INDUCEMENT_RISK",
    "INVALIDATED_REMAP",
    "MOVE_STARTED_NOT_CHASEABLE",
    "NO_TRADE",
    "REVIEW_REQUIRED",
}

STRUCTURE_KINDS = {"bos", "choch", "structure"}
TRADE_KINDS = {"entry", "stop", "target", "trade"}
POI_KINDS = {"poi", "order_block", "fvg"}
PATH_ALLOWED_STATES = {
    "WATCH_ONLY",
    "WAIT_FOR_POI",
    "WAIT_FOR_RETRACE_TO_SUPPLY",
    "WAIT_FOR_RETRACE_TO_DEMAND",
    "POI_TOUCHED_AWAIT_CONFIRMATION",
    "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY",
    "TRADE_PLAN_READY",
}
MAX_V2_OBJECTS = {
    "context_chart": 5,
    "watch_chart": 7,
    "review_chart": 7,
    "trade_plan_chart": 8,
    "debug_chart": 99,
}


def validate_annotation_plan_v2(
    decision: AISMCDecision,
    evidence_pack: Mapping[str, Any],
) -> AnnotationPlanValidation:
    plan = decision.annotation_plan_v2
    if plan is None:
        return AnnotationPlanValidation(status="NOT_PRESENT", issues=[], object_count=0)

    issues: list[AnnotationPlanIssue] = []
    objects = list(plan.objects)
    chart_template = decision.annotation_plan.chart_template
    max_objects = MAX_V2_OBJECTS.get(chart_template, 7)
    if len(objects) > max_objects:
        _issue(issues, "annotation_v2_object_budget_exceeded", f"{chart_template} allows at most {max_objects} professional drawing objects.")

    evidence_index = build_annotation_evidence_index(evidence_pack)
    graph = evidence_pack.get("formal_structure_graph") or {}
    parent_child = graph.get("parent_child_context") if isinstance(graph, Mapping) else {}
    has_parent_child_conflict = bool(isinstance(parent_child, Mapping) and parent_child.get("has_conflict"))

    for obj in objects:
        anchors = _anchors_for(obj, evidence_index)
        _check_common_object(obj, evidence_index, decision, issues)
        _check_evidence_contract_links(obj, evidence_pack, issues)
        _check_geometry_contract(obj, anchors, issues)
        _check_geometry(obj, decision, evidence_pack, anchors, issues)
        _check_type_semantics(obj, anchors, decision, evidence_pack, issues)
        _check_trade_gating(obj, decision, issues)
        _check_parent_child_conflict(obj, decision, has_parent_child_conflict, issues)

    status = "REVIEW_REQUIRED" if any(issue.severity == "hard" for issue in issues) else "VALIDATED"
    return AnnotationPlanValidation(status=status, issues=issues, object_count=len(objects))


def annotation_validation_to_dict(validation: AnnotationPlanValidation) -> dict[str, Any]:
    return {
        "schema": "professional_smc_annotation_validation_v1",
        "status": validation.status,
        "object_count": validation.object_count,
        "issues": [
            {"code": issue.code, "severity": issue.severity, "message": issue.message}
            for issue in validation.issues
        ],
    }


def _issue(issues: list[AnnotationPlanIssue], code: str, message: str, severity: str = "hard") -> None:
    issues.append(AnnotationPlanIssue(code=code, message=message, severity=severity))


def _check_common_object(
    obj: AnnotationDrawingObject,
    evidence_index: Mapping[str, AnnotationEvidenceAnchor],
    decision: AISMCDecision,
    issues: list[AnnotationPlanIssue],
) -> None:
    if obj.object_type != "path_projection" and not obj.evidence_object_ids:
        _issue(issues, "annotation_v2_missing_evidence", f"{obj.label} has no evidence_object_ids.")
        return
    unknown = [eid for eid in obj.evidence_object_ids if eid not in evidence_index]
    if unknown:
        _issue(issues, "annotation_v2_unresolved_evidence", f"{obj.label} references unknown evidence ids: {unknown}.")
    if obj.object_type == "path_projection":
        if decision.official_state not in PATH_ALLOWED_STATES:
            _issue(issues, "annotation_v2_path_not_allowed_for_state", f"{decision.official_state} cannot draw a thesis path.")
        if not decision.active_poi.poi_id or not decision.active_poi.evidence_object_ids:
            _issue(issues, "annotation_v2_path_without_active_poi", "A path projection requires a certified active POI.")


def _check_evidence_contract_links(
    obj: AnnotationDrawingObject,
    evidence_pack: Mapping[str, Any],
    issues: list[AnnotationPlanIssue],
) -> None:
    registry = evidence_pack.get("object_evidence_contracts")
    if not isinstance(registry, Mapping) or (registry.get("authority_contract") or {}).get("enforcement_ready") is not True:
        return
    contracts = registry.get("contracts")
    object_index = registry.get("object_id_index")
    if not isinstance(contracts, Mapping) or not isinstance(object_index, Mapping):
        _issue(issues, "annotation_v2_evidence_contract_registry_invalid", "Evidence contract registry is malformed.")
        return
    expected = {str(value) for value in obj.evidence_object_ids}
    linked_tokens = {str(value) for value in obj.evidence_contract_ids}
    resolved: set[str] = set()
    for token in linked_tokens:
        if token in contracts:
            resolved.add(token)
            continue
        candidates = [
            str(contract_id)
            for contract_id in object_index.get(token, [])
            if str((contracts.get(str(contract_id)) or {}).get("timeframe")) in {str(obj.timeframe), "unknown"}
        ]
        resolved.update(candidates)
    resolved_object_ids = {
        str((contracts.get(contract_id) or {}).get("object_id"))
        for contract_id in resolved
    }
    if not expected.issubset(resolved_object_ids):
        _issue(issues, "annotation_v2_evidence_contract_links_mismatch", f"{obj.label} evidence contracts do not match evidence objects.")
    missing = sorted(token for token in linked_tokens if token not in contracts and token not in object_index)
    if missing:
        _issue(issues, "annotation_v2_evidence_contract_missing", f"{obj.label} lacks contracts for {missing}.")
    incomplete = sorted(
        contract_id
        for contract_id in resolved
        if str((contracts[contract_id] or {}).get("contract_status")) != "COMPLETE"
    )
    if incomplete:
        _issue(issues, "annotation_v2_evidence_contract_incomplete", f"{obj.label} references incomplete contracts {incomplete}.")


def _check_geometry(
    obj: AnnotationDrawingObject,
    decision: AISMCDecision,
    evidence_pack: Mapping[str, Any],
    anchors: list[AnnotationEvidenceAnchor],
    issues: list[AnnotationPlanIssue],
) -> None:
    if obj.start_index is not None and obj.end_index is not None:
        span = abs(obj.end_index - obj.start_index)
        chart_rows = _chart_rows(evidence_pack, obj.timeframe)
        max_local_span = max(6, int(chart_rows * 0.36)) if chart_rows else 48
        if obj.kind in STRUCTURE_KINDS and span > max_local_span and not obj.allow_htf_full_width:
            _issue(
                issues,
                "annotation_v2_structure_segment_too_wide",
                f"{obj.label} spans {span} candles. BOS/CHoCH must be local unless explicitly marked as an HTF boundary.",
            )
        if obj.object_type == "poi_zone" and span > max(8, int((chart_rows or 120) * 0.45)) and not obj.allow_htf_full_width:
            _issue(issues, "annotation_v2_poi_zone_too_wide", f"{obj.label} POI zone is too wide for professional local markup.")

    if obj.object_type == "trade_box" and decision.official_state != "TRADE_PLAN_READY":
        _issue(issues, "annotation_v2_trade_box_without_trade_ready", "trade_box object requires TRADE_PLAN_READY.")
    if obj.object_type == "structure_segment":
        _check_structure_geometry(obj, anchors, issues)
    elif obj.object_type == "poi_zone":
        _check_poi_geometry(obj, anchors, evidence_pack, issues)
    elif obj.object_type == "liquidity_line":
        _check_liquidity_geometry(obj, anchors, issues)
    elif obj.object_type == "trade_box":
        _check_trade_box_geometry(obj, decision, issues)


def _check_geometry_contract(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    issues: list[AnnotationPlanIssue],
) -> None:
    evidence_model = obj.evidence_geometry
    display_model = obj.display_geometry
    if evidence_model is None or display_model is None:
        _issue(issues, "annotation_v2_geometry_contract_missing", f"{obj.label} lacks evidence/display geometry.")
        return
    evidence = evidence_model.model_dump(mode="json")
    display = display_model.model_dump(mode="json")
    expected_hash = geometry_hash(evidence)
    if evidence.get("geometry_hash") != expected_hash:
        _issue(issues, "annotation_v2_evidence_geometry_hash_mismatch", f"{obj.label} evidence geometry hash is invalid.")
    if display.get("derived_from_evidence_hash") != expected_hash:
        _issue(issues, "annotation_v2_display_geometry_not_derived", f"{obj.label} display geometry is not linked to immutable evidence geometry.")
    if evidence.get("anchor_mode") == "legacy_compatibility" and obj.object_type not in {"trade_box", "path_projection"}:
        _issue(issues, "annotation_v2_legacy_geometry_uncertified", f"{obj.label} uses compatibility geometry and cannot be certified.")
    source_ids = {str(value) for value in evidence.get("source_object_ids") or []}
    object_ids = {str(value) for value in obj.evidence_object_ids}
    if source_ids != object_ids:
        _issue(issues, "annotation_v2_geometry_source_ids_mismatch", f"{obj.label} geometry source IDs differ from evidence_object_ids.")

    for key in ("price", "price_low", "price_high"):
        if not _same_optional_number(evidence.get(key), display.get(key)):
            _issue(issues, "annotation_v2_display_changed_price", f"{obj.label} display geometry changed evidence {key}.")
        if not _same_optional_number(getattr(obj, key), display.get(key)):
            _issue(issues, "annotation_v2_top_level_not_display_geometry", f"{obj.label} top-level {key} does not match display geometry.")
    for key in ("start_index", "end_index", "start_time", "end_time"):
        if getattr(obj, key) != display.get(key):
            _issue(issues, "annotation_v2_top_level_not_display_geometry", f"{obj.label} top-level {key} does not match display geometry.")

    rule = str(display.get("clipping_rule") or "")
    if rule == "none":
        if any(evidence.get(key) != display.get(key) for key in GEOMETRY_FIELDS):
            _issue(issues, "annotation_v2_unreported_geometry_change", f"{obj.label} changed geometry while declaring clipping_rule=none.")
    elif rule == "confirmation_side_max_18_bars":
        _check_confirmation_side_clip(obj.label, evidence, display, issues)
    elif rule == "local_span_max_12_bars":
        start = display.get("start_index")
        end = display.get("end_index")
        if start is None or end is None or not (0 <= int(end) - int(start) <= 12):
            _issue(issues, "annotation_v2_local_display_span_invalid", f"{obj.label} local display span must be at most 12 bars.")
    elif rule == "legacy_unverified" and obj.object_type not in {"trade_box", "path_projection"}:
        _issue(issues, "annotation_v2_legacy_display_geometry", f"{obj.label} has unverified legacy display geometry.")

    if evidence.get("anchor_mode") == "exact_source" and anchors:
        anchor = anchors[0]
        _check_evidence_geometry_matches_anchor(obj.label, evidence, anchor, issues)


def _check_confirmation_side_clip(
    label: str,
    evidence: Mapping[str, Any],
    display: Mapping[str, Any],
    issues: list[AnnotationPlanIssue],
) -> None:
    if evidence.get("end_index") is not None and display.get("end_index") is not None:
        source_start = int(evidence["start_index"])
        source_end = int(evidence["end_index"])
        display_start = int(display["start_index"])
        display_end = int(display["end_index"])
        if display_end != source_end or not (source_start <= display_start <= display_end) or display_end - display_start > 18:
            _issue(issues, "annotation_v2_invalid_confirmation_side_clip", f"{label} display clip is not a bounded confirmation-side subset.")
        return
    if evidence.get("end_time") is not None and display.get("end_time") is not None:
        if display.get("end_time") != evidence.get("end_time") or display.get("start_time") is None:
            _issue(issues, "annotation_v2_invalid_confirmation_side_clip", f"{label} timestamp clip must preserve the confirmation anchor.")
        return
    _issue(issues, "annotation_v2_invalid_confirmation_side_clip", f"{label} clip cannot be reconstructed from source geometry.")


def _check_evidence_geometry_matches_anchor(
    label: str,
    evidence: Mapping[str, Any],
    anchor: AnnotationEvidenceAnchor,
    issues: list[AnnotationPlanIssue],
) -> None:
    index_grounded = (
        evidence.get("start_index") is not None
        and evidence.get("end_index") is not None
        and evidence.get("start_index") == anchor.start_index
        and evidence.get("end_index") == anchor.end_index
    )
    keys = ("start_index", "end_index") if index_grounded else ("start_time", "end_time")
    for key in keys:
        expected = getattr(anchor, key)
        actual = evidence.get(key)
        if expected is not None and actual != expected:
            _issue(issues, "annotation_v2_evidence_geometry_anchor_mismatch", f"{label} evidence {key} does not match source anchor.")
    expected_price = anchor.exact_price
    if expected_price is not None and not _same_optional_number(evidence.get("price"), expected_price):
        _issue(issues, "annotation_v2_evidence_geometry_anchor_mismatch", f"{label} evidence price does not match source anchor.")
    if expected_price is None and anchor.price_low is not None and not _same_optional_number(evidence.get("price_low"), anchor.price_low):
        _issue(issues, "annotation_v2_evidence_geometry_anchor_mismatch", f"{label} evidence price_low does not match source anchor.")
    if expected_price is None and anchor.price_high is not None and not _same_optional_number(evidence.get("price_high"), anchor.price_high):
        _issue(issues, "annotation_v2_evidence_geometry_anchor_mismatch", f"{label} evidence price_high does not match source anchor.")


def _same_optional_number(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return prices_match(float(left), float(right), basis_points=0.01)


def _chart_rows(evidence_pack: Mapping[str, Any], timeframe: str) -> int | None:
    windows = evidence_pack.get("ohlcv_windows") or {}
    if isinstance(windows, Mapping) and isinstance(windows.get(timeframe), list):
        return len(windows[timeframe])
    summaries = evidence_pack.get("ohlcv_summaries") or {}
    if isinstance(summaries, Mapping) and isinstance(summaries.get(timeframe), Mapping):
        count = summaries[timeframe].get("row_count")
        return int(count) if count is not None else None
    return None


def _check_type_semantics(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    decision: AISMCDecision,
    evidence_pack: Mapping[str, Any],
    issues: list[AnnotationPlanIssue],
) -> None:
    referenced_types = {anchor.evidence_type for anchor in anchors}
    if obj.kind == "order_block" and referenced_types and referenced_types <= {"fvg"}:
        _issue(issues, "annotation_v2_fvg_mislabeled_as_ob", f"{obj.label} is labeled OB but references only FVG evidence.")
    if obj.object_type == "structure_segment" and obj.kind not in STRUCTURE_KINDS:
        _issue(issues, "annotation_v2_bad_structure_kind", f"{obj.label} structure_segment must use BOS/CHoCH/structure kind.")
    if obj.object_type == "poi_zone" and obj.kind not in POI_KINDS:
        _issue(issues, "annotation_v2_bad_poi_kind", f"{obj.label} poi_zone must use POI/OB/FVG kind.")
    if obj.object_type == "liquidity_line" and obj.kind not in {"liquidity", "idm"}:
        _issue(issues, "annotation_v2_bad_liquidity_kind", f"{obj.label} liquidity_line must use liquidity or IDM kind.")
    if obj.object_type == "trade_box" and obj.kind != "trade":
        _issue(issues, "annotation_v2_bad_trade_box_kind", "trade_box must use kind=trade.")
    if obj.object_type == "structure_segment":
        structure = _first_anchor(anchors, "structure")
        if structure is None:
            _issue(issues, "annotation_v2_structure_requires_structure_evidence", f"{obj.label} has no confirmed structure-break evidence.")
        else:
            episode_event_type = _episode_event_type_for_object(evidence_pack, structure.object_id)
            expected_kind = _expected_structure_kind(episode_event_type, str(structure.kind or "").lower())
            if expected_kind in {"bos", "choch"} and obj.kind != expected_kind:
                _issue(issues, "annotation_v2_structure_kind_mismatch", f"{obj.label} must match its {expected_kind.upper()} evidence.")
            if expected_kind == "structure" and obj.kind != "structure":
                _issue(issues, "annotation_v2_structure_kind_mismatch", f"{obj.label} must use generic structure kind for {episode_event_type}.")
            expected_scope = structure.structure_scope or "external"
            if obj.structure_scope != expected_scope:
                _issue(issues, "annotation_v2_structure_scope_mismatch", f"{obj.label} must declare structure_scope={expected_scope}.")
            if expected_scope == "internal" and "internal" not in obj.label.lower() and not obj.label.lower().startswith("i"):
                _issue(issues, "annotation_v2_internal_structure_not_labeled", f"{obj.label} must visibly identify internal structure.")
    if obj.object_type == "poi_zone":
        poi = _first_anchor(anchors, "order_block", "fvg")
        if poi is None:
            _issue(issues, "annotation_v2_poi_requires_poi_evidence", f"{obj.label} has no OB/FVG evidence.")
        elif obj.kind == "poi":
            if decision.active_poi.poi_id != poi.object_id:
                _issue(issues, "annotation_v2_generic_poi_not_active", f"{obj.label} can use kind=poi only for the certified active POI.")
        elif obj.kind != poi.evidence_type:
            _issue(issues, "annotation_v2_poi_kind_mismatch", f"{obj.label} is {obj.kind}, but evidence is {poi.evidence_type}.")


def _episode_event_type_for_object(evidence_pack: Mapping[str, Any], object_id: str) -> str | None:
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    timeframes = graph.get("timeframes") if isinstance(graph, Mapping) else None
    for node in timeframes.values() if isinstance(timeframes, Mapping) else []:
        if not isinstance(node, Mapping):
            continue
        for episode in node.get("episodes", []) or []:
            if isinstance(episode, Mapping) and str(episode.get("structure_event_id") or "") == object_id:
                return str(episode.get("event_type") or "") or None
    return None


def _expected_structure_kind(event_type: str | None, fallback_kind: str) -> str:
    token = str(event_type or "")
    if token == "INITIAL_DIRECTION_BREAK" or "MSS" in token:
        return "structure"
    if "CHOCH" in token:
        return "choch"
    if "BOS" in token:
        return "bos"
    return fallback_kind


def _check_trade_gating(
    obj: AnnotationDrawingObject,
    decision: AISMCDecision,
    issues: list[AnnotationPlanIssue],
) -> None:
    if decision.official_state in WATCH_STATES and (obj.kind in TRADE_KINDS or obj.object_type == "trade_box"):
        _issue(issues, "annotation_v2_watch_contains_trade_object", f"{decision.official_state} cannot draw {obj.kind}/{obj.object_type}.")
    if decision.official_state == "TRADE_PLAN_READY" and obj.object_type == "trade_box" and not decision.annotation_plan.show_trade_box:
        _issue(issues, "annotation_v2_trade_box_without_legacy_gate", "trade_box requires annotation_plan.show_trade_box=true.")
    if decision.official_state == "TRADE_PLAN_READY" and obj.object_type != "trade_box" and obj.kind in {"entry", "stop", "target"}:
        _issue(issues, "annotation_v2_split_trade_box_forbidden", "V2 trade levels must be contained in one trade_box object.")


def _check_parent_child_conflict(
    obj: AnnotationDrawingObject,
    decision: AISMCDecision,
    has_parent_child_conflict: bool,
    issues: list[AnnotationPlanIssue],
) -> None:
    if not has_parent_child_conflict:
        return
    if obj.object_type == "structure_segment" and obj.kind in STRUCTURE_KINDS and decision.direction in {"bullish", "bearish"}:
        _issue(
            issues,
            "annotation_v2_internal_structure_drawn_as_parent_bias",
            "Parent-child conflict requires mixed direction; structure annotations cannot present a clean parent bias.",
        )


def _anchors_for(
    obj: AnnotationDrawingObject,
    evidence_index: Mapping[str, AnnotationEvidenceAnchor],
) -> list[AnnotationEvidenceAnchor]:
    return [evidence_index[eid] for eid in obj.evidence_object_ids if eid in evidence_index]


def _first_anchor(anchors: list[AnnotationEvidenceAnchor], *types: str) -> AnnotationEvidenceAnchor | None:
    return next((anchor for anchor in anchors if anchor.evidence_type in types), None)


def _check_structure_geometry(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    issues: list[AnnotationPlanIssue],
) -> None:
    anchor = _first_anchor(anchors, "structure")
    if anchor is None:
        return
    if anchor.start_index is None or anchor.end_index is None:
        _issue(issues, "annotation_v2_evidence_outside_visible_window", f"{obj.label} structure evidence is outside the chart evidence window.")
    if anchor.confirmation_status != "confirmed" or anchor.is_wick_only_probe:
        _issue(issues, "annotation_v2_structure_not_confirmed", f"{obj.label} references a wick probe or unconfirmed structure candidate.")
    expected = anchor.exact_price
    if not prices_match(obj.price, expected):
        _issue(issues, "annotation_v2_structure_price_mismatch", f"{obj.label} price does not match the broken swing level.")
    _check_anchor_span(
        obj,
        anchor,
        "annotation_v2_structure_span_mismatch",
        issues,
        allow_confirmation_side_clip=True,
    )


def _check_poi_geometry(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    evidence_pack: Mapping[str, Any],
    issues: list[AnnotationPlanIssue],
) -> None:
    anchor = _first_anchor(anchors, "order_block", "fvg")
    if anchor is None:
        return
    if anchor.start_index is None or anchor.end_index is None:
        _issue(issues, "annotation_v2_evidence_outside_visible_window", f"{obj.label} POI evidence is outside the chart evidence window.")
    if anchor.confirmation_status != "confirmed":
        _issue(issues, "annotation_v2_poi_not_confirmed", f"{obj.label} references an unconfirmed POI candidate.")
    if anchor.activity_status == "terminal" or anchor.mitigation_status in {"full", "invalidated"}:
        _issue(issues, "annotation_v2_poi_not_active", f"{obj.label} references a consumed or invalidated POI.")
    observed_state = observed_poi_state(anchor, evidence_pack)
    if observed_state in {"consumed", "invalidated"}:
        _issue(issues, "annotation_v2_poi_observed_consumed", f"{obj.label} was {observed_state} by subsequent visible candles.")
    elif observed_state == "unverifiable":
        _issue(issues, "annotation_v2_poi_lifecycle_unverifiable", f"{obj.label} lifecycle cannot be reconstructed inside the visible evidence window.")
    if not zones_match(obj.price_low, obj.price_high, anchor.price_low, anchor.price_high):
        _issue(issues, "annotation_v2_poi_price_mismatch", f"{obj.label} zone does not match the certified POI bounds.")
    _check_anchor_span(obj, anchor, "annotation_v2_poi_span_mismatch", issues)


def _check_liquidity_geometry(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    issues: list[AnnotationPlanIssue],
) -> None:
    anchor = _first_anchor(anchors, "liquidity", "active_range", "inducement", "sweep")
    if anchor is None:
        _issue(issues, "annotation_v2_liquidity_requires_liquidity_evidence", f"{obj.label} has no liquidity or active-range evidence.")
        return
    expected_prices = [value for value in (anchor.exact_price, anchor.price_low, anchor.price_high) if value is not None]
    if obj.price is None or not any(prices_match(obj.price, expected) for expected in expected_prices):
        _issue(issues, "annotation_v2_liquidity_price_mismatch", f"{obj.label} price does not match its liquidity evidence.")
    _check_anchor_span(obj, anchor, "annotation_v2_liquidity_span_mismatch", issues, allow_unindexed=True)


def _check_trade_box_geometry(
    obj: AnnotationDrawingObject,
    decision: AISMCDecision,
    issues: list[AnnotationPlanIssue],
) -> None:
    if obj.entry_price is None or obj.stop_price is None or not obj.target_prices:
        return
    if decision.entry_plan.entry_price is not None and not prices_match(obj.entry_price, decision.entry_plan.entry_price):
        _issue(issues, "annotation_v2_trade_entry_mismatch", "V2 trade-box entry does not match the validated entry plan.")
    if decision.stop_loss_plan.stop_price is not None and not prices_match(obj.stop_price, decision.stop_loss_plan.stop_price):
        _issue(issues, "annotation_v2_trade_stop_mismatch", "V2 trade-box stop does not match the validated stop plan.")
    expected_targets = [target.price for target in decision.target_plan.targets]
    if expected_targets and not all(any(prices_match(price, expected) for expected in expected_targets) for price in obj.target_prices):
        _issue(issues, "annotation_v2_trade_target_mismatch", "V2 trade-box targets do not match validated target liquidity.")
    if obj.price is not None and not prices_match(obj.price, obj.entry_price):
        _issue(issues, "annotation_v2_trade_price_mismatch", "trade_box price must equal entry_price.")


def _check_anchor_span(
    obj: AnnotationDrawingObject,
    anchor: AnnotationEvidenceAnchor,
    code: str,
    issues: list[AnnotationPlanIssue],
    *,
    allow_unindexed: bool = False,
    allow_confirmation_side_clip: bool = False,
) -> None:
    geometry = obj.evidence_geometry
    if geometry is not None and geometry.anchor_mode == "exact_source":
        start_index = geometry.start_index
        end_index = geometry.end_index
    else:
        start_index = obj.start_index
        end_index = obj.end_index
    if start_index is None or end_index is None:
        return
    if anchor.start_index is None or anchor.end_index is None:
        if not allow_unindexed:
            _issue(issues, code, f"{obj.label} cannot be anchored to a visible source candle.")
        return
    if abs(start_index - anchor.start_index) > 2 or abs(end_index - anchor.end_index) > 2:
        _issue(issues, code, f"{obj.label} span is not anchored to the source object’s pivot and confirmation candles.")
