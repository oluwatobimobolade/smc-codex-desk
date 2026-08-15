"""Native-timeframe professional SMC storyboards and render pack.

The official 15m chart remains available for compatibility. This module avoids
flattening every structural object onto that canvas by rendering D1, 4H, 1H,
and 15m evidence in their own coordinate systems.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import ValidationResult
from smc_desk.brain.annotation_evidence import AnnotationEvidenceAnchor, build_annotation_evidence_index
from smc_desk.brain.annotation_geometry import build_geometry_contract
from smc_desk.perception.significance import SignificanceScore
from smc_desk.rendering.bitmap_annotation_review import review_rendered_annotation_bitmap
from smc_desk.rendering.swing_skeleton import build_swing_skeleton
from smc_desk.rendering.smc_trader_annotation_renderer import render_smc_trader_annotation_chart


NATIVE_TIMEFRAMES = ("1d", "4h", "1h", "15m")
MAX_NATIVE_OBJECTS = 7


def build_native_mtf_storyboards(
    evidence_pack: Mapping[str, Any],
    *,
    selected_evidence_ids: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    graph_timeframes = graph.get("timeframes") if isinstance(graph, Mapping) else {}
    accepted_by_timeframe = _accepted_episode_ids_by_timeframe(graph_timeframes)
    definition_blocked_timeframes = _definition_blocked_timeframes(evidence_pack)
    source_identity_block = _source_identity_block(evidence_pack)
    scenarios = (evidence_pack.get("causal_poi_authority") or {}).get("scenarios")
    index = build_annotation_evidence_index(evidence_pack)
    context_authority = evidence_pack.get("annotation_context_authority") or {}
    context_requirements = [
        item
        for item in (context_authority.get("requirements") or [])
        if isinstance(item, Mapping) and item.get("required_render") is True
    ] if isinstance(context_authority, Mapping) else []
    storyboards: dict[str, Any] = {}
    for timeframe in NATIVE_TIMEFRAMES:
        if source_identity_block or timeframe in definition_blocked_timeframes:
            suppression_status = source_identity_block or definition_blocked_timeframes[timeframe]
            storyboards[timeframe] = {
                "schema": "native_smc_storyboard_v1",
                "timeframe": timeframe,
                "objects": [],
                "source": (
                    "market_source_identity_fail_closed"
                    if source_identity_block
                    else "autonomous_definition_conformance_fail_closed"
                ),
                "resolution_manifest": {
                    "schema": "native_annotation_resolution_v1",
                    "requested_ids": [],
                    "required_context_ids": [],
                    "rendered_ids": [],
                    "deduplicated_ids": [],
                    "off_window_ids": [],
                    "unsupported_ids": [],
                    "unknown_ids": [],
                    "budget_omissions": [],
                    "data_authority_suppressed": True,
                    "suppression_status": suppression_status,
                },
                "authority_contract": {
                    "observe_only": True,
                    "can_promote_trade_state": False,
                    "trade_box_allowed": False,
                    "data_authority_suppressed": True,
                },
            }
            continue
        node = graph_timeframes.get(timeframe) if isinstance(graph_timeframes, Mapping) else None
        objects: list[dict[str, Any]] = []
        if isinstance(node, Mapping):
            for key in ("latest_external_episode", "latest_internal_episode"):
                episode = node.get(key)
                if not isinstance(episode, Mapping):
                    continue
                object_id = str(episode.get("structure_event_id") or "")
                anchor = index.get(object_id)
                if anchor is not None and _native_visible(anchor, timeframe):
                    objects.append(_structure_object(anchor, episode))
            episode = node.get("latest_external_episode")
            if isinstance(episode, Mapping):
                primary = episode.get("primary_poi")
                poi_anchor = _poi_anchor(index, primary)
                if poi_anchor is not None and poi_anchor.timeframe == timeframe and _native_visible(poi_anchor, timeframe):
                    objects.append(_poi_object(poi_anchor, primary))
                idm = _first_anchor(index, episode.get("inducement_ids"), timeframe)
                if idm is not None:
                    objects.append(_liquidity_object(idm, label="IDM", kind="idm"))
                elif (sweep := _first_anchor(index, episode.get("sweep_ids"), timeframe)) is not None:
                    objects.append(_liquidity_object(sweep, label="Sweep", kind="liquidity"))
        # Structural context: the HH/HL/LH/LL sequence the episode above broke.
        # Without it a reader sees a BOS tag floating in bare candles with no
        # way to check the structure it refers to. Selection is by significance
        # and capped, so this narrows the 400-odd detected swings to a
        # chart-sized set rather than restoring the detector firehose.
        objects.extend(
            _swing_skeleton_objects(evidence_pack, index, timeframe)
        )

        # The causal POI authority is the production primary selector.  The
        # episode graph may deliberately leave episode.primary_poi unset, so a
        # native storyboard must also consume the selected scenario primary or
        # the professionally important OB disappears from the chart.
        if isinstance(scenarios, Mapping):
            for scenario in scenarios.values():
                if not isinstance(scenario, Mapping) or scenario.get("status") != "SELECTED":
                    continue
                primary = scenario.get("primary_causal_poi")
                if not isinstance(primary, Mapping) or primary.get("timeframe") != timeframe:
                    continue
                linked_break_id = str(primary.get("linked_break_id") or scenario.get("accepted_break_id") or "")
                if linked_break_id not in accepted_by_timeframe.get(timeframe, set()):
                    # A V1-selected POI whose native break failed V3 is a
                    # disputed hypothesis, not a drawable continuation zone.
                    continue
                poi_anchor = _poi_anchor(index, primary)
                if poi_anchor is not None and _native_visible(poi_anchor, timeframe):
                    objects.append(_poi_object(poi_anchor, primary))
        requirements = [
            item for item in context_requirements
            if str(item.get("timeframe") or "") == timeframe
        ]
        required_ids = {str(item.get("object_id") or "") for item in requirements}
        resolution = {
            "schema": "native_annotation_resolution_v1",
            "requested_ids": [],
            "required_context_ids": sorted(required_ids),
            "rendered_ids": [],
            "deduplicated_ids": [],
            "off_window_ids": [],
            "unsupported_ids": [],
            "unknown_ids": [],
            "budget_omissions": [],
        }
        for requirement in requirements:
            object_id = str(requirement.get("object_id") or "")
            if not object_id or _contains_evidence_id(objects, object_id):
                continue
            materialized, outcome = _materialize_evidence_object(
                object_id=object_id,
                timeframe=timeframe,
                evidence_pack=evidence_pack,
                index=index,
                context_requirement=requirement,
            )
            if materialized is not None:
                objects.append(materialized)
            else:
                resolution[outcome].append(object_id)

        active_range = (evidence_pack.get("active_range_authority") or {}).get("selected_range")
        if (
            isinstance(active_range, Mapping)
            and str(active_range.get("timeframe") or "") == timeframe
            and not any(obj.get("object_type") == "range_zone" for obj in objects)
        ):
            range_object = _active_range_object(active_range, evidence_pack)
            if range_object is not None:
                objects.append(range_object)

        deduped, duplicate_ids = _dedupe_with_report(objects)
        resolution["deduplicated_ids"].extend(duplicate_ids)
        if selected_evidence_ids is not None and timeframe in selected_evidence_ids:
            allowed = {str(value) for value in selected_evidence_ids[timeframe]}
            resolution["requested_ids"] = sorted(allowed)
            # Deterministic context coverage cannot be suppressed by a sparse AI
            # selection. The AI can add or remove optional marks, but an object
            # classified as required context must render or fail visibly.
            allowed.update(required_ids)
            # A resolved dealing range is location authority, not an optional
            # decorative mark.  A sparse AI selection may choose the episode
            # marks, but it cannot erase the certified range that its thesis
            # uses for premium/discount language.
            allowed.update(
                str(value)
                for obj in deduped
                if obj.get("object_type") == "range_zone"
                for value in obj.get("evidence_object_ids") or []
            )
            present = {
                str(value)
                for obj in deduped
                for value in obj.get("evidence_object_ids") or []
            }
            for object_id in sorted(allowed.difference(present)):
                requirement = next(
                    (item for item in requirements if str(item.get("object_id") or "") == object_id),
                    None,
                )
                materialized, outcome = _materialize_evidence_object(
                    object_id=object_id,
                    timeframe=timeframe,
                    evidence_pack=evidence_pack,
                    index=index,
                    context_requirement=requirement,
                )
                if materialized is not None:
                    deduped.append(materialized)
                else:
                    resolution[outcome].append(object_id)
            deduped = [
                obj
                for obj in deduped
                if allowed.intersection(str(value) for value in obj.get("evidence_object_ids") or [])
            ]
            deduped, duplicate_ids = _dedupe_with_report(deduped)
            resolution["deduplicated_ids"].extend(duplicate_ids)
        kept, budget_omissions = _apply_native_budget(deduped, required_ids=required_ids)
        resolution["budget_omissions"] = budget_omissions
        resolution["rendered_ids"] = sorted({
            str(value)
            for obj in kept
            for value in obj.get("evidence_object_ids") or []
        })
        storyboards[timeframe] = {
            "schema": "native_smc_storyboard_v1",
            "timeframe": timeframe,
            "objects": kept,
            "source": "formal_causal_episode_graph_v2+annotation_context_authority_v1",
            "resolution_manifest": resolution,
            "authority_contract": {
                "observe_only": True,
                "can_promote_trade_state": False,
                "trade_box_allowed": False,
            },
        }
    validation = validate_native_mtf_storyboards(storyboards, evidence_pack)
    return {
        "schema": "native_mtf_smc_storyboard_pack_v1",
        "storyboards": storyboards,
        "validation": validation,
        "authority_contract": {
            "observe_only": True,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }


def validate_native_mtf_storyboards(
    storyboards: Mapping[str, Any], evidence_pack: Mapping[str, Any]
) -> dict[str, Any]:
    index = build_annotation_evidence_index(evidence_pack)
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    accepted_by_timeframe = _accepted_episode_ids_by_timeframe(
        graph.get("timeframes") if isinstance(graph, Mapping) else {}
    )
    issues: list[dict[str, str]] = []
    raw_storyboards = storyboards.get("storyboards") if storyboards.get("schema") == "native_mtf_smc_storyboard_pack_v1" else storyboards
    for timeframe, storyboard in raw_storyboards.items() if isinstance(raw_storyboards, Mapping) else []:
        if not isinstance(storyboard, Mapping):
            continue
        objects = storyboard.get("objects") or []
        # Swing markers are context, budgeted separately from the story marks;
        # counting them here would flag every chart that carries a skeleton.
        story_objects = [obj for obj in objects if not _is_skeleton(obj)]
        skeleton_objects = [obj for obj in objects if _is_skeleton(obj)]
        if len(story_objects) > MAX_NATIVE_OBJECTS:
            issues.append({"code": "native_storyboard_object_budget_exceeded", "message": f"{timeframe} contains more than {MAX_NATIVE_OBJECTS} story objects."})
        if len(skeleton_objects) > SWING_SKELETON_LIMIT:
            issues.append({"code": "native_storyboard_skeleton_budget_exceeded", "message": f"{timeframe} carries more than {SWING_SKELETON_LIMIT} swing markers."})
        resolution = storyboard.get("resolution_manifest") or {}
        unresolved = [
            *list(resolution.get("unknown_ids") or []),
            *list(resolution.get("off_window_ids") or []),
            *list(resolution.get("unsupported_ids") or []),
        ]
        if unresolved:
            issues.append({"code": "native_storyboard_selected_evidence_unresolved", "message": f"{timeframe} could not materialize {sorted(set(map(str, unresolved)))}."})
        requested = {str(value) for value in resolution.get("requested_ids") or []}
        rendered = {str(value) for value in resolution.get("rendered_ids") or []}
        missing_requested = sorted(requested.difference(rendered))
        if missing_requested:
            issues.append({
                "code": "native_storyboard_requested_evidence_missing_from_scene",
                "message": f"{timeframe} requested evidence was not present in the final visible scene: {missing_requested}.",
            })
        for obj in objects:
            if not isinstance(obj, Mapping):
                continue
            evidence_ids = [str(value) for value in obj.get("evidence_object_ids") or []]
            unknown = [value for value in evidence_ids if value not in index]
            if unknown:
                issues.append({"code": "native_storyboard_unknown_evidence", "message": f"{timeframe} object {obj.get('semantic_object_id')} references {unknown}."})
            if obj.get("timeframe") != timeframe:
                issues.append({"code": "native_storyboard_scope_mismatch", "message": f"{obj.get('semantic_object_id')} is not native to {timeframe}."})
            if obj.get("object_type") == "trade_box":
                issues.append({"code": "native_storyboard_trade_box_forbidden", "message": "Native observe-only storyboards cannot contain trade boxes."})
            if (
                obj.get("object_type") == "structure_segment"
                and evidence_ids
                and evidence_ids[0] not in accepted_by_timeframe.get(str(timeframe), set())
            ):
                issues.append({"code": "native_storyboard_structure_not_v3_accepted", "message": f"{evidence_ids[0]} did not survive the V3 lifecycle."})
    rendered_ids = {
        str(value)
        for storyboard in raw_storyboards.values() if isinstance(storyboard, Mapping)
        for obj in storyboard.get("objects", []) or [] if isinstance(obj, Mapping)
        for value in obj.get("evidence_object_ids") or []
    } if isinstance(raw_storyboards, Mapping) else set()
    context_authority = evidence_pack.get("annotation_context_authority") or {}
    for requirement in context_authority.get("requirements", []) or [] if isinstance(context_authority, Mapping) else []:
        if not isinstance(requirement, Mapping) or requirement.get("required_render") is not True:
            continue
        object_id = str(requirement.get("object_id") or "")
        if object_id and object_id not in rendered_ids:
            issues.append({
                "code": "native_storyboard_required_context_missing",
                "message": f"Required contextual evidence {object_id} was neither rendered nor validly resolved.",
            })
    return {
        "schema": "native_mtf_smc_storyboard_validation_v1",
        "status": "PASS" if not issues else "REVIEW_REQUIRED",
        "issues": issues,
    }


def render_native_mtf_story_pack(
    *,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    evidence_pack: Mapping[str, Any],
    validation_result: ValidationResult,
    output_dir: str | Path,
    semantic_review_status: str = "NOT_PERFORMED_NO_VISION_PROVIDER",
    selected_evidence_ids: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    pack = build_native_mtf_storyboards(
        evidence_pack,
        selected_evidence_ids=selected_evidence_ids,
    )
    (root / "native_mtf_storyboards.json").write_text(json.dumps(pack, indent=2, sort_keys=True, default=str), encoding="utf-8")
    renders: dict[str, Any] = {}
    for timeframe, storyboard in pack["storyboards"].items():
        df = timeframe_dfs.get(timeframe)
        if df is None or df.empty:
            continue
        rows = len((evidence_pack.get("ohlcv_windows") or {}).get(timeframe) or [])
        render_df = df.tail(rows or 120).copy()
        official = copy.deepcopy(validation_result.official_decision)
        official["annotation_plan_v2"] = {
            "schema": "professional_smc_annotation_plan_v2",
            "style": "professional_smc_sparse",
            "objects": list(storyboard.get("objects") or []),
            "notes": [f"Native {timeframe} causal-episode storyboard; observe-only."],
        }
        annotation_plan = dict(official.get("annotation_plan") or {})
        annotation_plan["chart_template"] = "review_chart" if validation_result.status == "REVIEW_REQUIRED" else "watch_chart"
        annotation_plan["show_trade_box"] = False
        official["annotation_plan"] = annotation_plan
        native_result = ValidationResult(
            status=validation_result.status,
            decision=validation_result.decision,
            official_decision=official,
            issues=validation_result.issues,
            smc_model_validity=validation_result.smc_model_validity,
            trade_plan_validity=validation_result.trade_plan_validity,
        )
        chart_path = root / f"{timeframe}_professional_smc_story.png"
        scene = render_smc_trader_annotation_chart(
            render_df,
            native_result,
            chart_path,
            timeframe=timeframe,
            # Native storyboards are already causally selected and capped at
            # their professional object budget. Do not silently prune a mark
            # chosen by the external AI seat with the generic review limit.
            visible_object_limit=len(storyboard.get("objects") or []),
        )
        bitmap_review = review_rendered_annotation_bitmap(
            chart_path,
            scene=scene,
            semantic_review_status=semantic_review_status,
        )
        scene_coverage = _validate_rendered_scene_coverage(storyboard, scene)
        renders[timeframe] = {
            "chart_path": str(chart_path),
            "scene": scene,
            "bitmap_review": bitmap_review,
            "scene_coverage": scene_coverage,
        }
    manifest = {
        "schema": "native_mtf_smc_story_render_manifest_v1",
        "storyboard_validation": pack["validation"],
        "renders": renders,
        "status": (
            "REVIEW_REQUIRED"
            if pack["validation"]["status"] != "PASS"
            or any(item["bitmap_review"]["deterministic_bitmap_status"] != "PASS" for item in renders.values())
            or any(item["scene_coverage"]["status"] != "PASS" for item in renders.values())
            else "PASS_WITH_SEMANTIC_REVIEW_PENDING"
            if semantic_review_status == "NOT_PERFORMED_NO_VISION_PROVIDER"
            else "PASS"
        ),
    }
    (root / "native_mtf_render_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return manifest


def _validate_rendered_scene_coverage(
    storyboard: Mapping[str, Any], scene: Mapping[str, Any]
) -> dict[str, Any]:
    """Prove requested/required IDs survived final visual cleanup."""
    resolution = storyboard.get("resolution_manifest") or {}
    expected = {
        str(value)
        for key in ("requested_ids", "required_context_ids")
        for value in resolution.get(key) or []
    }
    visible = {
        str(value)
        for obj in scene.get("visible_drawing_objects", []) or []
        if isinstance(obj, Mapping)
        for value in obj.get("evidence_object_ids") or []
    }
    missing = sorted(expected.difference(visible))
    trade_boxes = [
        str(obj.get("semantic_object_id") or "")
        for obj in scene.get("visible_drawing_objects", []) or []
        if isinstance(obj, Mapping) and obj.get("object_type") == "trade_box"
    ]
    issues: list[dict[str, Any]] = []
    if missing:
        issues.append({
            "code": "native_final_scene_coverage_missing",
            "message": f"Evidence selected for the native chart disappeared before final pixels: {missing}.",
            "object_ids": missing,
        })
    if trade_boxes:
        issues.append({
            "code": "native_final_scene_trade_box_forbidden",
            "message": "Observe-only native storyboards cannot render a trade box.",
            "object_ids": trade_boxes,
        })
    return {
        "schema": "native_final_scene_coverage_v1",
        "status": "PASS" if not issues else "REVIEW_REQUIRED",
        "expected_evidence_ids": sorted(expected),
        "visible_evidence_ids": sorted(visible),
        "issues": issues,
    }


def _materialize_evidence_object(
    *,
    object_id: str,
    timeframe: str,
    evidence_pack: Mapping[str, Any],
    index: Mapping[str, AnnotationEvidenceAnchor],
    context_requirement: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Materialize any supported selected evidence type, never silently skip."""
    anchor = index.get(object_id)
    if anchor is None:
        return None, "unknown_ids"
    if anchor.timeframe != timeframe:
        return None, "unsupported_ids"
    if not _native_visible(anchor, timeframe):
        return None, "off_window_ids"
    raw = _candidate_for_id(evidence_pack, timeframe, object_id)
    if anchor.evidence_type == "structure":
        episode = _episode_for_id(evidence_pack, timeframe, object_id)
        if episode is None:
            episode = {
                "event_type": str((raw or {}).get("break_type") or "BOS"),
                "scope": anchor.structure_scope or "external",
            }
        obj = _structure_object(anchor, episode)
    elif anchor.evidence_type in {"order_block", "fvg"}:
        obj = _poi_object(anchor, raw or {})
    elif anchor.evidence_type == "sweep":
        obj = _liquidity_object(anchor, label="Sweep", kind="liquidity")
    elif anchor.evidence_type == "inducement":
        obj = _liquidity_object(anchor, label="IDM", kind="idm")
    elif anchor.evidence_type in {"liquidity", "active_range", "swing_pivot"}:
        obj = _liquidity_object(anchor, label="Liquidity", kind="liquidity")
    else:
        return None, "unsupported_ids"
    if context_requirement is not None:
        obj = _apply_context_display_contract(obj, context_requirement, evidence_pack)
    return obj, "rendered_ids"


def _apply_context_display_contract(
    obj: dict[str, Any],
    requirement: Mapping[str, Any],
    evidence_pack: Mapping[str, Any],
) -> dict[str, Any]:
    role = str(requirement.get("display_role") or "context_only")
    direction = str(obj.get("direction") or "unknown")
    if obj.get("object_type") == "poi_zone":
        if obj.get("kind") == "order_block":
            side = "Supply" if direction == "bearish" else "Demand" if direction == "bullish" else "Context"
            # Native storyboards render each object on its own timeframe.  A
            # superseded 15m/1h/4h zone is therefore *prior* structure on that
            # chart, not automatically a higher-timeframe zone.  Calling it
            # HTF would visually grant authority the evidence does not have.
            prefix = "Refined" if role == "context_refinement" else "Prior"
            obj["label"] = f"{prefix} {side} OB (context)"
        else:
            side = "Bearish" if direction == "bearish" else "Bullish" if direction == "bullish" else "Context"
            obj["label"] = f"{side} FVG (context)"
    elif obj.get("object_type") == "structure_segment":
        prefix = "Refinement" if role == "context_refinement_structure" else "Prior"
        obj["label"] = f"{prefix} {obj.get('label')} (context)"
    obj["reason"] = str(requirement.get("reason") or obj.get("reason") or "Context-only evidence.")
    obj["line_style"] = "dashed"
    obj["display_role"] = role
    obj["control_status"] = str(requirement.get("control_status") or "context_only")
    obj["active_entry_authority"] = False
    obj["context_requirement_id"] = str(requirement.get("requirement_id") or "")
    obj["importance"] = max(1, min(3, int(requirement.get("render_priority") or 2)))
    if obj.get("object_type") == "poi_zone":
        latest = _latest_visible_window_point(evidence_pack, str(obj.get("timeframe") or ""))
        if latest is not None:
            latest_index, latest_time = latest
            evidence_geometry = {
                key: obj.get(key)
                for key in ("start_index", "end_index", "start_time", "end_time", "price", "price_low", "price_high")
            }
            display_geometry = {
                **evidence_geometry,
                "end_index": max(int(obj.get("end_index") or 0), latest_index),
                "end_time": latest_time,
            }
            obj.update(display_geometry)
            obj.update(
                build_geometry_contract(
                    evidence=evidence_geometry,
                    display=display_geometry,
                    source_object_ids=[str(value) for value in obj.get("evidence_object_ids") or []],
                    anchor_mode="exact_source",
                    clipping_rule="context_zone_to_latest_visible_bar",
                )
            )
    return obj


def _active_range_object(
    active_range: Mapping[str, Any], evidence_pack: Mapping[str, Any]
) -> dict[str, Any] | None:
    range_id = str(active_range.get("range_id") or "")
    timeframe = str(active_range.get("timeframe") or "")
    low = _float_or_none(active_range.get("range_low", active_range.get("low")))
    high = _float_or_none(active_range.get("range_high", active_range.get("high")))
    equilibrium = _float_or_none(active_range.get("equilibrium"))
    pivots = [
        item for item in active_range.get("source_pivots", []) or []
        if isinstance(item, Mapping) and item.get("timestamp")
    ]
    latest = _latest_visible_window_point(evidence_pack, timeframe)
    if not range_id or low is None or high is None or equilibrium is None or len(pivots) < 2 or latest is None:
        return None
    pivot_times = sorted(str(item["timestamp"]) for item in pivots)
    latest_index, latest_time = latest
    window = (evidence_pack.get("ohlcv_windows") or {}).get(timeframe) or []
    start_index = _window_index_for_time(window, pivot_times[0])
    source_end_index = _window_index_for_time(window, pivot_times[-1])
    if start_index is None or source_end_index is None:
        return None
    evidence_geometry = {
        "start_index": start_index,
        "end_index": source_end_index,
        "start_time": pivot_times[0],
        "end_time": pivot_times[-1],
        "price": None,
        "price_low": min(low, high),
        "price_high": max(low, high),
    }
    display_geometry = {
        **evidence_geometry,
        "end_index": max(source_end_index, latest_index),
        "end_time": latest_time,
    }
    return {
        "object_type": "range_zone",
        "semantic_object_id": f"{range_id}:native_dealing_range",
        "timeframe": timeframe,
        "label": f"{timeframe.upper()} Dealing Range",
        "reason": "Certified protected-swing dealing range governing current premium/discount location.",
        "kind": "range",
        "direction": str(active_range.get("direction") or "unknown"),
        "price_low": evidence_geometry["price_low"],
        "price_high": evidence_geometry["price_high"],
        "equilibrium_price": equilibrium,
        "start_index": display_geometry["start_index"],
        "end_index": display_geometry["end_index"],
        "start_time": display_geometry["start_time"],
        "end_time": display_geometry["end_time"],
        "line_style": "dashed",
        "evidence_object_ids": [range_id],
        "evidence_contract_ids": [range_id],
        **build_geometry_contract(
            evidence=evidence_geometry,
            display=display_geometry,
            source_object_ids=[range_id],
            anchor_mode="derived_level",
            clipping_rule="active_range_to_latest_visible_bar",
        ),
        "active_entry_authority": False,
        "allow_htf_full_width": True,
        "importance": 1,
    }


def _latest_visible_window_point(
    evidence_pack: Mapping[str, Any], timeframe: str
) -> tuple[int, str] | None:
    window = (evidence_pack.get("ohlcv_windows") or {}).get(timeframe)
    if not isinstance(window, list) or not window or not isinstance(window[-1], Mapping):
        return None
    timestamp = window[-1].get("timestamp")
    if not timestamp:
        return None
    return len(window) - 1, str(timestamp)


def _window_index_for_time(window: Sequence[Any], value: str) -> int | None:
    target = pd.Timestamp(value)
    best: tuple[pd.Timedelta, int] | None = None
    for index, raw in enumerate(window):
        if not isinstance(raw, Mapping) or not raw.get("timestamp"):
            continue
        delta = abs(pd.Timestamp(raw["timestamp"]) - target)
        if best is None or delta < best[0]:
            best = (delta, index)
    return best[1] if best is not None else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_for_id(
    evidence_pack: Mapping[str, Any], timeframe: str, object_id: str
) -> Mapping[str, Any] | None:
    detector = evidence_pack.get("detector_candidates") or {}
    payload = detector.get(timeframe) if isinstance(detector, Mapping) else None
    if not isinstance(payload, Mapping):
        return None
    for values in payload.values():
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, Mapping) and str(item.get("object_id") or item.get("id") or "") == object_id:
                return item
    return None


def _episode_for_id(
    evidence_pack: Mapping[str, Any], timeframe: str, object_id: str
) -> Mapping[str, Any] | None:
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    timeframes = graph.get("timeframes") if isinstance(graph, Mapping) else None
    node = timeframes.get(timeframe) if isinstance(timeframes, Mapping) else None
    if not isinstance(node, Mapping):
        return None
    return next(
        (
            episode for episode in node.get("episodes", []) or []
            if isinstance(episode, Mapping)
            and str(episode.get("structure_event_id") or "") == object_id
        ),
        None,
    )


def _contains_evidence_id(objects: Sequence[Mapping[str, Any]], object_id: str) -> bool:
    return any(
        object_id in {str(value) for value in obj.get("evidence_object_ids") or []}
        for obj in objects
    )


def _accepted_episode_ids_by_timeframe(graph_timeframes: Any) -> dict[str, set[str]]:
    if not isinstance(graph_timeframes, Mapping):
        return {}
    return {
        str(timeframe): {
            str(episode.get("structure_event_id"))
            for episode in node.get("episodes", []) or []
            if isinstance(episode, Mapping) and episode.get("structure_event_id")
        }
        for timeframe, node in graph_timeframes.items()
        if isinstance(node, Mapping)
    }


def _definition_blocked_timeframes(evidence_pack: Mapping[str, Any]) -> dict[str, str]:
    bundle = evidence_pack.get("definition_conformance") or {}
    by_timeframe = bundle.get("by_timeframe") if isinstance(bundle, Mapping) else None
    if not isinstance(by_timeframe, Mapping):
        return {}
    blocked = {"DATA_FAILED", "IMPLEMENTATION_CONFLICT", "DOCTRINE_UNDEFINED"}
    result: dict[str, str] = {}
    for timeframe, item in by_timeframe.items():
        certificate = item.get("certificate") if isinstance(item, Mapping) else None
        status = str(certificate.get("status") or "") if isinstance(certificate, Mapping) else ""
        if status in blocked:
            result[str(timeframe)] = status
    return result


def _source_identity_block(evidence_pack: Mapping[str, Any]) -> str | None:
    session = evidence_pack.get("session_context") or {}
    certificate = session.get("source_identity_certificate") if isinstance(session, Mapping) else None
    if not isinstance(certificate, Mapping):
        return None
    status = str(certificate.get("status") or "")
    return status if status in {"MISMATCH", "MISMATCH_PROXY"} else None


def _dedupe_with_report(
    objects: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    unique: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    for obj in objects:
        evidence_ids = tuple(sorted(str(value) for value in obj.get("evidence_object_ids") or []))
        key = (str(obj.get("object_type") or ""), evidence_ids)
        if key in unique:
            duplicate_ids.extend(evidence_ids)
            continue
        unique[key] = obj
    return list(unique.values()), sorted(set(duplicate_ids))


def _is_skeleton(obj: Mapping[str, Any]) -> bool:
    return str(obj.get("object_type") or "") == "swing_marker"


def _apply_native_budget(
    objects: Sequence[dict[str, Any]], *, required_ids: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Budget the story objects. The swing skeleton is budgeted separately.

    The seven-object limit was calibrated for story marks -- zones, segments,
    labelled liquidity lines -- which are visually heavy and compete for the
    same attention. A swing tick is a different class: a short dotted mark with
    a two-character label, which is what a reader scans to check the structure
    rather than something they act on.

    Making them share one budget would mean either clipping the skeleton to
    nothing (it ranks last on importance, so it loses every tie) or raising the
    story limit and letting genuinely heavy marks multiply. Separating them
    keeps the calibrated story budget untouched and bounds the context layer at
    its own selection limit.
    """
    story = [obj for obj in objects if not _is_skeleton(obj)]
    skeleton = [obj for obj in objects if _is_skeleton(obj)]
    if len(story) <= MAX_NATIVE_OBJECTS:
        return list(objects), []
    ranked = sorted(
        enumerate(story),
        key=lambda pair: (
            0 if required_ids.intersection(str(value) for value in pair[1].get("evidence_object_ids") or []) else 1,
            int(pair[1].get("importance") or 2),
            pair[0],
        ),
    )
    kept_indexes = {index for index, _obj in ranked[:MAX_NATIVE_OBJECTS]}
    kept = [obj for index, obj in enumerate(story) if index in kept_indexes] + skeleton
    omitted = [
        {
            "semantic_object_id": str(obj.get("semantic_object_id") or ""),
            "evidence_object_ids": [str(value) for value in obj.get("evidence_object_ids") or []],
            "reason_code": "native_storyboard_object_budget",
        }
        for index, obj in enumerate(objects)
        if index not in kept_indexes
    ]
    return kept, omitted


def _structure_object(anchor: AnnotationEvidenceAnchor, episode: Mapping[str, Any]) -> dict[str, Any]:
    label, kind, line_style = _structure_semantic(str(episode.get("event_type") or ""), str(episode.get("scope") or ""))
    start_index, end_index = _confirmation_side_span(anchor, maximum_bars=18)
    return {
        "object_type": "structure_segment",
        "semantic_object_id": f"{anchor.object_id}:native_episode_segment",
        "timeframe": anchor.timeframe,
        "label": label,
        "reason": f"V3-accepted {episode.get('event_type')} anchored from the certified swing to accepted confirmation.",
        "kind": kind,
        "direction": anchor.direction or "unknown",
        "price": anchor.exact_price,
        "start_index": start_index,
        "end_index": end_index,
        "start_time": None,
        "end_time": None,
        "structure_scope": anchor.structure_scope or episode.get("scope"),
        "line_style": line_style,
        "evidence_object_ids": [anchor.object_id],
        "importance": 1,
    }


def _poi_object(anchor: AnnotationEvidenceAnchor, poi: Mapping[str, Any]) -> dict[str, Any]:
    is_ob = str(poi.get("kind") or anchor.evidence_type) == "order_block"
    structural_role = str(poi.get("structural_role") or poi.get("lineage_role") or "")
    label = {
        "protected_reversal_origin_ob": "Protected OB",
        "protected_reversal_origin": "Protected OB",
        "direction_establishing_origin_ob": "Origin OB",
        "direction_establishing_origin": "Origin OB",
        "continuation_origin_ob": "Continuation OB",
        "latest_external_continuation_origin": "Continuation OB",
        "execution_refinement": "Refinement OB" if is_ob else "Refinement FVG",
    }.get(structural_role, "OB" if is_ob else "FVG")
    if str(poi.get("freshness") or "").lower() in {"partial", "partially_mitigated"}:
        label = f"{label} (partial)"
    return {
        "object_type": "poi_zone",
        "semantic_object_id": f"{anchor.object_id}:native_poi_zone",
        "timeframe": anchor.timeframe,
        "label": label,
        "reason": f"{poi.get('poi_role')} linked to the V3-accepted structural episode; reaction is not guaranteed.",
        "kind": "order_block" if is_ob else "fvg",
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


def _liquidity_object(anchor: AnnotationEvidenceAnchor, *, label: str, kind: str) -> dict[str, Any]:
    start_index, end_index = _confirmation_side_span(anchor, maximum_bars=12)
    return {
        "object_type": "liquidity_line",
        "semantic_object_id": f"{anchor.object_id}:native_liquidity",
        "timeframe": anchor.timeframe,
        "label": label,
        "reason": "Episode-linked liquidity interaction; shown locally and never treated as independent trade authority.",
        "kind": kind,
        "direction": anchor.direction or "unknown",
        "price": anchor.exact_price,
        "start_index": start_index,
        "end_index": end_index,
        "start_time": None,
        "end_time": None,
        "line_style": "dotted",
        "evidence_object_ids": [anchor.object_id],
        "importance": 2,
    }


def _structure_semantic(event_type: str, scope: str) -> tuple[str, str, str]:
    if event_type == "INITIAL_DIRECTION_BREAK":
        return "Initial Break", "structure", "solid"
    if "CHOCH" in event_type:
        return ("Internal CHoCH" if scope == "internal" else "CHoCH", "choch", "dashed" if scope == "internal" else "solid")
    if "MSS" in event_type:
        return "MSS", "structure", "solid"
    return ("Internal BOS" if scope == "internal" else "BOS", "bos", "dashed" if scope == "internal" else "solid")


def _poi_anchor(index: Mapping[str, AnnotationEvidenceAnchor], poi: Any) -> AnnotationEvidenceAnchor | None:
    if not isinstance(poi, Mapping):
        return None
    for value in (poi.get("source_object_id"), poi.get("poi_id")):
        if value and str(value) in index:
            return index[str(value)]
    return None


def _first_anchor(
    index: Mapping[str, AnnotationEvidenceAnchor], values: Any, timeframe: str
) -> AnnotationEvidenceAnchor | None:
    for value in values or []:
        anchor = index.get(str(value))
        if anchor is not None and anchor.timeframe == timeframe and _native_visible(anchor, timeframe):
            return anchor
    return None


SWING_SKELETON_LIMIT = 6


def _swing_skeleton_objects(
    evidence_pack: Mapping[str, Any],
    index: Mapping[str, AnnotationEvidenceAnchor],
    timeframe: str,
) -> list[dict[str, Any]]:
    """Labelled structural swings for one timeframe, or nothing.

    Fail-soft by contract. The skeleton is context a reader benefits from, not
    evidence anything depends on, so a missing or malformed significance report
    yields an unlabelled chart rather than a failed render.
    """
    significance = evidence_pack.get("structural_significance") or {}
    node = (significance.get("timeframes") or {}).get(timeframe) if isinstance(significance, Mapping) else None
    if not isinstance(node, Mapping):
        return []
    # The selection was already made by the grading layer, which is where the
    # prominence scores are. This only rehydrates the chosen few.
    scores_by_id = {
        str(object_id): SignificanceScore(
            object_id=str(object_id),
            grade=str(item.get("grade") or "noise"),
            atr_multiple=float(item.get("atr_multiple") or 0.0),
            range_fraction=0.0,
            prominence_percentile=item.get("prominence_percentile"),
        )
        for object_id, item in (node.get("swing_grades") or {}).items()
        if isinstance(item, Mapping)
    }
    if not scores_by_id:
        return []
    anchors = [
        anchor for anchor in index.values()
        if anchor.evidence_type == "swing" and _native_visible(anchor, timeframe)
    ]
    try:
        return build_swing_skeleton(
            anchors, scores_by_id, timeframe=timeframe, limit=SWING_SKELETON_LIMIT
        )
    except Exception:  # noqa: BLE001 -- descriptive context may never fail a render
        return []


def _native_visible(anchor: AnnotationEvidenceAnchor, timeframe: str) -> bool:
    return (
        anchor.timeframe == timeframe
        and anchor.start_index is not None
        and anchor.end_index is not None
        and anchor.confirmation_status == "confirmed"
        and not anchor.is_wick_only_probe
    )


def _confirmation_side_span(
    anchor: AnnotationEvidenceAnchor, *, maximum_bars: int
) -> tuple[int | None, int | None]:
    if anchor.start_index is None or anchor.end_index is None:
        return anchor.start_index, anchor.end_index
    return max(anchor.start_index, anchor.end_index - maximum_bars), anchor.end_index


def _dedupe(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for obj in objects:
        unique.setdefault(str(obj.get("semantic_object_id") or ""), obj)
    return list(unique.values())


__all__ = [
    "build_native_mtf_storyboards",
    "render_native_mtf_story_pack",
    "validate_native_mtf_storyboards",
]
