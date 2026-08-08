"""Native-timeframe professional SMC storyboards and render pack.

The official 15m chart remains available for compatibility. This module avoids
flattening every structural object onto that canvas by rendering 4H, 1H, and
15m evidence in their own coordinate systems.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import ValidationResult
from smc_desk.brain.annotation_evidence import AnnotationEvidenceAnchor, build_annotation_evidence_index
from smc_desk.rendering.bitmap_annotation_review import review_rendered_annotation_bitmap
from smc_desk.rendering.smc_trader_annotation_renderer import render_smc_trader_annotation_chart


NATIVE_TIMEFRAMES = ("4h", "1h", "15m")


def build_native_mtf_storyboards(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    graph_timeframes = graph.get("timeframes") if isinstance(graph, Mapping) else {}
    index = build_annotation_evidence_index(evidence_pack)
    storyboards: dict[str, Any] = {}
    for timeframe in NATIVE_TIMEFRAMES:
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
        storyboards[timeframe] = {
            "schema": "native_smc_storyboard_v1",
            "timeframe": timeframe,
            "objects": _dedupe(objects)[:4],
            "source": "formal_causal_episode_graph_v2",
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
    accepted_ids = {
        str(episode.get("structure_event_id"))
        for node in (graph.get("timeframes") or {}).values()
        if isinstance(node, Mapping)
        for episode in node.get("episodes", []) or []
        if isinstance(episode, Mapping) and episode.get("structure_event_id")
    }
    issues: list[dict[str, str]] = []
    raw_storyboards = storyboards.get("storyboards") if storyboards.get("schema") == "native_mtf_smc_storyboard_pack_v1" else storyboards
    for timeframe, storyboard in raw_storyboards.items() if isinstance(raw_storyboards, Mapping) else []:
        if not isinstance(storyboard, Mapping):
            continue
        objects = storyboard.get("objects") or []
        if len(objects) > 4:
            issues.append({"code": "native_storyboard_object_budget_exceeded", "message": f"{timeframe} contains more than four story objects."})
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
            if obj.get("object_type") == "structure_segment" and evidence_ids and evidence_ids[0] not in accepted_ids:
                issues.append({"code": "native_storyboard_structure_not_v3_accepted", "message": f"{evidence_ids[0]} did not survive the V3 lifecycle."})
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
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    pack = build_native_mtf_storyboards(evidence_pack)
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
        )
        bitmap_review = review_rendered_annotation_bitmap(
            chart_path,
            scene=scene,
            semantic_review_status=semantic_review_status,
        )
        renders[timeframe] = {
            "chart_path": str(chart_path),
            "scene": scene,
            "bitmap_review": bitmap_review,
        }
    manifest = {
        "schema": "native_mtf_smc_story_render_manifest_v1",
        "storyboard_validation": pack["validation"],
        "renders": renders,
        "status": (
            "REVIEW_REQUIRED"
            if pack["validation"]["status"] != "PASS"
            or any(item["bitmap_review"]["deterministic_bitmap_status"] != "PASS" for item in renders.values())
            else "PASS_WITH_SEMANTIC_REVIEW_PENDING"
            if semantic_review_status == "NOT_PERFORMED_NO_VISION_PROVIDER"
            else "PASS"
        ),
    }
    (root / "native_mtf_render_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return manifest


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
    structural_role = str(poi.get("structural_role") or "")
    label = {
        "protected_reversal_origin_ob": "Protected OB",
        "direction_establishing_origin_ob": "Origin OB",
        "continuation_origin_ob": "Continuation OB",
        "execution_refinement": "Refinement OB" if is_ob else "Refinement FVG",
    }.get(structural_role, "OB" if is_ob else "FVG")
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
