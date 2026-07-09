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
    prices_match,
    zones_match,
)


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
    "trade_plan_chart": 9,
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
        _check_geometry(obj, decision, evidence_pack, anchors, issues)
        _check_type_semantics(obj, anchors, decision, issues)
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
        _check_poi_geometry(obj, anchors, issues)
    elif obj.object_type == "liquidity_line":
        _check_liquidity_geometry(obj, anchors, issues)
    elif obj.object_type == "trade_box":
        _check_trade_box_geometry(obj, decision, issues)


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
            expected_kind = str(structure.kind or "").lower()
            if expected_kind in {"bos", "choch"} and obj.kind != expected_kind:
                _issue(issues, "annotation_v2_structure_kind_mismatch", f"{obj.label} must match its {expected_kind.upper()} evidence.")
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
    expected = anchor.exact_price
    if not prices_match(obj.price, expected):
        _issue(issues, "annotation_v2_structure_price_mismatch", f"{obj.label} price does not match the broken swing level.")
    _check_anchor_span(obj, anchor, "annotation_v2_structure_span_mismatch", issues)


def _check_poi_geometry(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    issues: list[AnnotationPlanIssue],
) -> None:
    anchor = _first_anchor(anchors, "order_block", "fvg")
    if anchor is None:
        return
    if not zones_match(obj.price_low, obj.price_high, anchor.price_low, anchor.price_high):
        _issue(issues, "annotation_v2_poi_price_mismatch", f"{obj.label} zone does not match the certified POI bounds.")
    _check_anchor_span(obj, anchor, "annotation_v2_poi_span_mismatch", issues)


def _check_liquidity_geometry(
    obj: AnnotationDrawingObject,
    anchors: list[AnnotationEvidenceAnchor],
    issues: list[AnnotationPlanIssue],
) -> None:
    anchor = _first_anchor(anchors, "liquidity", "active_range")
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
) -> None:
    if obj.start_index is None or obj.end_index is None:
        return
    if anchor.start_index is None or anchor.end_index is None:
        if not allow_unindexed:
            _issue(issues, code, f"{obj.label} cannot be anchored to a visible source candle.")
        return
    if abs(obj.start_index - anchor.start_index) > 2 or abs(obj.end_index - anchor.end_index) > 2:
        _issue(issues, code, f"{obj.label} span is not anchored to the source object’s pivot and confirmation candles.")
