"""Downgrade-only local visual critic for professional SMC annotations.

No external vision API is needed for the first line of defence. The critic
inspects the actual drawing geometry before it is made official and can only
remove clutter or request review; it has no promotion path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class VisualCriticIssue:
    code: str
    severity: str
    message: str
    object_ids: tuple[str, ...] = ()


def review_annotation_scene(scene: Mapping[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    objects = [item for item in scene.get("visible_drawing_objects", []) if isinstance(item, Mapping)]
    v2_active = scene.get("level_source") == "annotation_plan_v2"
    issues: list[VisualCriticIssue] = []
    if v2_active and scene.get("visible_labels"):
        issues.append(
            VisualCriticIssue(
                code="legacy_text_panel_on_v2_chart",
                severity="hard",
                message="A V2 professional chart must not retain legacy explanatory text panels.",
            )
        )
    explicit_limit = scene.get("visible_object_limit_override")
    limit = (
        max(0, int(explicit_limit))
        if explicit_limit is not None
        else 4 if scene.get("chart_template") in {"watch_chart", "context_chart", "review_chart"} else 5
    )
    if len(objects) > limit:
        issues.append(
            VisualCriticIssue(
                code="visual_object_density_exceeded",
                severity="cleanup",
                message=f"Professional {scene.get('chart_template')} markup allows at most {limit} visible V2 objects.",
                object_ids=tuple(str(item.get("semantic_object_id") or "") for item in objects[limit:]),
            )
        )
    required_context_ids = {
        str(item.get("semantic_object_id") or "")
        for item in objects
        if item.get("context_requirement_id")
    }
    for issue in _overlap_issues(objects, df):
        if required_context_ids.intersection(issue.object_ids):
            issues.append(
                VisualCriticIssue(
                    code="required_context_overlap_requires_review",
                    severity="hard",
                    message="A mandatory context mark has a label-overlap risk and cannot be silently removed.",
                    object_ids=issue.object_ids,
                )
            )
        else:
            issues.append(issue)
    cleanup_ids = _cleanup_ids(issues, objects)
    hard = [issue for issue in issues if issue.severity == "hard"]
    status = "REVIEW_REQUIRED" if hard else "CLEANUP_REQUIRED" if cleanup_ids else "PASSED"
    return {
        "schema": "professional_smc_annotation_visual_review_v1",
        "status": status,
        "critic_authority": "downgrade_or_cleanup_only",
        "visible_object_count": len(objects),
        "cleanup_object_ids": cleanup_ids,
        "issues": [
            {"code": issue.code, "severity": issue.severity, "message": issue.message, "object_ids": list(issue.object_ids)}
            for issue in issues
        ],
    }


def apply_visual_cleanup(scene: Mapping[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    """Return a render scene with only the critic-approved objects visible."""
    out = dict(scene)
    initial_review = review_annotation_scene(out, df)
    cleanup = set(initial_review["cleanup_object_ids"])
    if cleanup:
        out["visible_drawing_objects"] = [
            item for item in out.get("visible_drawing_objects", [])
            if str(item.get("semantic_object_id") or "") not in cleanup
        ]
        out["visible_drawing_object_count"] = len(out["visible_drawing_objects"])
        out["visible_levels"] = [
            item for item in out.get("visible_levels", [])
            if str(item.get("semantic_object_id") or "") not in cleanup
        ]
        out["visible_level_count"] = len(out["visible_levels"])
    final_review = review_annotation_scene(out, df)
    final_review["pre_cleanup_status"] = initial_review["status"]
    final_review["cleanup_applied"] = sorted(cleanup)
    final_review["pre_cleanup_issues"] = initial_review["issues"]
    out["visual_critic"] = final_review
    return out


def _overlap_issues(objects: list[Mapping[str, Any]], df: pd.DataFrame) -> list[VisualCriticIssue]:
    prices = [_object_price(obj) for obj in objects]
    prices = [price for price in prices if price is not None]
    if not prices:
        return []
    if {"high", "low"}.issubset(df.columns):
        chart_low = float(df["low"].min())
        chart_high = float(df["high"].max())
    else:
        chart_low, chart_high = min(prices), max(prices)
    span = max(chart_high - chart_low, abs(chart_high) * 0.001, 1e-9)
    result: list[VisualCriticIssue] = []
    for left_idx, left in enumerate(objects):
        for right in objects[left_idx + 1:]:
            if left.get("object_type") == "poi_zone" or right.get("object_type") == "poi_zone":
                continue
            left_price, right_price = _object_price(left), _object_price(right)
            if left_price is None or right_price is None:
                continue
            left_x = _label_x(left)
            right_x = _label_x(right)
            if abs(left_x - right_x) <= 10 and abs(left_price - right_price) <= span * 0.035:
                weaker = _weaker(left, right)
                result.append(
                    VisualCriticIssue(
                        code="annotation_label_overlap_risk",
                        severity="cleanup",
                        message="Two local labels would overlap or become visually ambiguous.",
                        object_ids=(str(weaker.get("semantic_object_id") or ""),),
                    )
                )
    return result


def _cleanup_ids(issues: list[VisualCriticIssue], objects: list[Mapping[str, Any]]) -> list[str]:
    ids: list[str] = []
    for issue in issues:
        if issue.severity == "cleanup":
            ids.extend(object_id for object_id in issue.object_ids if object_id)
    # Avoid deleting all evidence objects when duplicate overlap diagnostics point
    # at the same small plan. A professional chart with no mark is less useful.
    all_ids = {str(item.get("semantic_object_id") or "") for item in objects}
    protected = {
        str(item.get("semantic_object_id") or "")
        for item in objects
        if item.get("context_requirement_id")
    }
    unique = [object_id for object_id in dict.fromkeys(ids) if object_id not in protected]
    return unique if len(unique) < len(all_ids) else unique[:-1]


def _object_price(obj: Mapping[str, Any]) -> float | None:
    for key in ("price", "price_high", "price_low"):
        value = obj.get(key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _label_x(obj: Mapping[str, Any]) -> float:
    try:
        start = float(obj.get("start_index"))
        end = float(obj.get("end_index"))
        return (start + end) / 2.0
    except (TypeError, ValueError):
        return 0.0


def _weaker(left: Mapping[str, Any], right: Mapping[str, Any]) -> Mapping[str, Any]:
    left_rank = int(left.get("importance") or 2)
    right_rank = int(right.get("importance") or 2)
    return right if left_rank <= right_rank else left
