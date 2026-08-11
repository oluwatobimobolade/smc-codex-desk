from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from smc_desk.brain.annotation_candidate_composer import compose_local_annotation_plan_v2
from smc_desk.rendering.bitmap_annotation_review import review_rendered_annotation_bitmap
from smc_desk.brain.ai_smc_consistency_validator import ValidationResult
from smc_desk.rendering.native_mtf_story_pack import build_native_mtf_storyboards
from smc_desk.rendering.smc_trader_annotation_renderer import build_smc_trader_annotation_scene
from smc_desk.brain.annotation_visual_critic import apply_visual_cleanup


def _window() -> list[dict]:
    return [
        {
            "timestamp": f"2026-01-01T{index:02d}:00:00Z",
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 1000.0,
        }
        for index in range(20)
    ]


def _pack() -> dict:
    window = _window()
    structure = {
        "object_id": "break-1",
        "object_type": "structure_break",
        "timeframe": "15m",
        "direction": "bullish",
        "break_type": "BOS",
        "structure_scope": "external",
        "pivot_time": window[3]["timestamp"],
        "candidate_at": window[8]["timestamp"],
        "confirmed_at": window[9]["timestamp"],
        "confirmation_status": "confirmed",
        "activity_status": "inactive",
        "mitigation_status": "untouched",
        "evidence": {"broken_price": 100.0, "structure_scope": "external"},
    }
    order_block = {
        "object_id": "ob-1",
        "object_type": "order_block",
        "timeframe": "15m",
        "direction": "bullish",
        "pivot_time": window[5]["timestamp"],
        "candidate_at": window[8]["timestamp"],
        "confirmed_at": window[9]["timestamp"],
        "confirmation_status": "confirmed",
        "activity_status": "active",
        "mitigation_status": "untouched",
        "price_low": 98.5,
        "price_high": 99.5,
        "evidence": {},
    }
    inducement = {
        "object_id": "idm-1",
        "object_type": "inducement",
        "timeframe": "15m",
        "direction": "bullish",
        "pivot_time": window[7]["timestamp"],
        "candidate_at": window[7]["timestamp"],
        "confirmed_at": window[8]["timestamp"],
        "confirmation_status": "confirmed",
        "activity_status": "active",
        "mitigation_status": "untouched",
        "price_low": 99.2,
        "price_high": 99.2,
        "evidence": {"related_break_id": "break-1", "inducement_taken": False},
    }
    return {
        "ohlcv_windows": {"15m": window},
        "detector_candidates": {
            "15m": {
                "structure_breaks": [structure],
                "order_blocks": [order_block],
                "inducements": [inducement],
            }
        },
        "formal_structure_graph": {"active_range": {}},
        "formal_causal_episode_graph": {
            "schema": "formal_causal_episode_graph_v2",
            "timeframes": {
                "15m": {
                    "episodes": [{"structure_event_id": "break-1"}],
                    "latest_external_episode": {
                        "structure_event_id": "break-1",
                        "event_type": "INITIAL_DIRECTION_BREAK",
                        "scope": "external",
                        "primary_poi": {
                            "source_object_id": "ob-1",
                            "kind": "order_block",
                            "poi_role": "primary_causal_poi",
                        },
                        "inducement_ids": ["idm-1"],
                        "sweep_ids": [],
                    },
                    "latest_internal_episode": None,
                }
            },
        },
        "active_range_authority": {},
    }


def test_native_storyboard_tells_one_grounded_episode_without_trade_box():
    result = build_native_mtf_storyboards(_pack())
    storyboard = result["storyboards"]["15m"]

    assert result["validation"]["status"] == "PASS"
    assert [obj["object_type"] for obj in storyboard["objects"]] == [
        "structure_segment",
        "poi_zone",
        "liquidity_line",
    ]
    assert storyboard["objects"][0]["label"] == "Initial Break"
    assert all(obj["object_type"] != "trade_box" for obj in storyboard["objects"])


def test_native_storyboard_includes_authority_selected_primary_poi():
    pack = _pack()
    pack["formal_causal_episode_graph"]["timeframes"]["15m"]["latest_external_episode"]["primary_poi"] = None
    pack["causal_poi_authority"] = {
        "scenarios": {
            "bullish": {
                "status": "SELECTED",
                "primary_causal_poi": {
                    "source_object_id": "ob-1",
                    "poi_id": "15m:order_block:ob-1",
                    "timeframe": "15m",
                    "kind": "order_block",
                    "lineage_role": "protected_reversal_origin",
                    "poi_role": "primary_causal_poi",
                },
            }
        }
    }

    result = build_native_mtf_storyboards(pack)
    objects = result["storyboards"]["15m"]["objects"]

    poi = next(obj for obj in objects if obj["object_type"] == "poi_zone")
    assert poi["label"] == "Protected OB"
    assert poi["evidence_object_ids"] == ["ob-1"]


def test_native_storyboard_labels_partially_mitigated_primary_poi() -> None:
    pack = _pack()
    pack["formal_causal_episode_graph"]["timeframes"]["15m"]["latest_external_episode"]["primary_poi"] = None
    pack["causal_poi_authority"] = {
        "scenarios": {
            "bullish": {
                "status": "SELECTED",
                "primary_causal_poi": {
                    "source_object_id": "ob-1",
                    "poi_id": "15m:order_block:ob-1",
                    "timeframe": "15m",
                    "kind": "order_block",
                    "freshness": "partial",
                    "lineage_role": "protected_reversal_origin",
                    "poi_role": "primary_causal_poi",
                },
            }
        }
    }

    result = build_native_mtf_storyboards(pack)
    poi = next(
        obj for obj in result["storyboards"]["15m"]["objects"]
        if obj["object_type"] == "poi_zone"
    )

    assert poi["label"] == "Protected OB (partial)"


def test_native_storyboard_draws_certified_dealing_range_to_latest_bar() -> None:
    pack = _pack()
    window = pack["ohlcv_windows"]["15m"]
    range_id = "15m:active_range:test"
    selected = {
        "range_id": range_id,
        "timeframe": "15m",
        "direction": "bearish",
        "range_low": 98.0,
        "range_high": 102.0,
        "equilibrium": 100.0,
        "source_pivots": [
            {"timestamp": window[10]["timestamp"], "kind": "high", "price": 102.0},
            {"timestamp": window[14]["timestamp"], "kind": "low", "price": 98.0},
        ],
    }
    pack["formal_structure_graph"]["active_range"] = {
        "range_id": range_id,
        "timeframe": "15m",
        "direction": "bearish",
        "low": 98.0,
        "high": 102.0,
    }
    pack["active_range_authority"] = {"selected_range": selected}

    result = build_native_mtf_storyboards(pack)
    range_object = next(
        obj for obj in result["storyboards"]["15m"]["objects"]
        if obj["object_type"] == "range_zone"
    )

    assert result["validation"]["status"] == "PASS"
    assert range_object["equilibrium_price"] == 100.0
    assert range_object["start_time"] == window[10]["timestamp"]
    assert range_object["end_time"] == window[-1]["timestamp"]
    assert range_object["evidence_geometry"]["end_time"] == window[14]["timestamp"]
    assert range_object["display_geometry"]["clipping_rule"] == "active_range_to_latest_visible_bar"
    assert range_object["active_entry_authority"] is False


def test_external_ai_selection_can_suppress_auto_marks_and_select_sweep() -> None:
    pack = _pack()
    window = pack["ohlcv_windows"]["15m"]
    sweep = {
        "object_id": "sweep-1",
        "object_type": "sweep",
        "timeframe": "15m",
        "direction": "bullish",
        "pivot_time": window[6]["timestamp"],
        "candidate_at": window[7]["timestamp"],
        "confirmed_at": window[8]["timestamp"],
        "confirmation_status": "confirmed",
        "activity_status": "inactive",
        "mitigation_status": "untouched",
        "price_low": 98.0,
        "price_high": 99.0,
        "evidence": {"swept_price": 98.5},
    }
    pack["detector_candidates"]["15m"]["sweeps"] = [sweep]
    pack["formal_causal_episode_graph"]["timeframes"]["15m"]["latest_external_episode"]["sweep_ids"] = ["sweep-1"]

    result = build_native_mtf_storyboards(
        pack,
        selected_evidence_ids={"15m": ["break-1", "sweep-1"]},
    )
    objects = result["storyboards"]["15m"]["objects"]

    assert result["validation"]["status"] == "PASS"
    assert [obj["evidence_object_ids"] for obj in objects] == [["break-1"], ["sweep-1"]]
    assert [obj["label"] for obj in objects] == ["Initial Break", "Sweep"]


def test_explicit_native_story_budget_preserves_four_ai_selected_objects() -> None:
    objects = [
        {
            "object_id": f"mark-{index}",
            "object_type": "liquidity_line",
            "label": f"Mark {index}",
            "kind": "liquidity",
            "price_low": 99.0 + index,
            "price_high": 99.0 + index,
            "start_index": 1,
            "end_index": 5,
            "importance": 1,
        }
        for index in range(4)
    ]
    official = {
        "symbol": "AUDNZD",
        "official_state": "REVIEW_REQUIRED",
        "annotation_plan": {
            "chart_template": "review_chart",
            "show_trade_box": False,
            "labels": [],
            "levels": [],
        },
        "annotation_plan_v2": {
            "schema": "professional_smc_annotation_plan_v2",
            "objects": objects,
        },
    }
    # This unit isolates renderer budgeting; full decision-schema validation is
    # covered by the AI-brain and external-agent handoff suites.
    result = ValidationResult.model_construct(
        status="REVIEW_REQUIRED",
        decision=official,
        official_decision=official,
        issues=[],
        smc_model_validity="valid",
        trade_plan_validity="failed",
    )

    default_scene = build_smc_trader_annotation_scene(result)
    native_scene = build_smc_trader_annotation_scene(result, visible_object_limit=4)

    assert default_scene["visible_drawing_object_count"] == 3
    assert native_scene["visible_drawing_object_count"] == 4
    assert native_scene["visible_level_count"] == 4
    assert native_scene["visible_object_limit_override"] == 4


def test_native_visual_cleanup_respects_explicit_budget_and_protects_required_context() -> None:
    objects = [
        {
            "semantic_object_id": f"mark-{index}",
            "object_type": "structure_segment",
            "kind": "structure",
            "price": 95.0 + index * 2.0,
            "start_index": index * 4,
            "end_index": index * 4 + 2,
            "importance": 1,
            **(
                {"context_requirement_id": "context_requirement:4h:required"}
                if index == 4 else {}
            ),
        }
        for index in range(5)
    ]
    scene = {
        "level_source": "annotation_plan_v2",
        "chart_template": "review_chart",
        "visible_object_limit_override": 5,
        "visible_drawing_objects": objects,
        "visible_drawing_object_count": 5,
        "visible_levels": [
            {"semantic_object_id": item["semantic_object_id"]} for item in objects
        ],
        "visible_level_count": 5,
        "visible_labels": [],
    }
    frame = pd.DataFrame({"high": [110.0] * 30, "low": [90.0] * 30})

    cleaned = apply_visual_cleanup(scene, frame)

    assert cleaned["visible_drawing_object_count"] == 5
    assert cleaned["visual_critic"]["cleanup_applied"] == []
    assert "mark-4" in {
        item["semantic_object_id"] for item in cleaned["visible_drawing_objects"]
    }


def test_bitmap_review_reads_the_rendered_pixels(tmp_path: Path):
    pixels = np.full((600, 1200, 3), 255, dtype=np.uint8)
    pixels[100:520, 200:204] = (20, 20, 20)
    pixels[180:420, 500:700] = (38, 166, 154)
    path = tmp_path / "chart.png"
    Image.fromarray(pixels).save(path)

    review = review_rendered_annotation_bitmap(
        path,
        scene={"visible_drawing_object_count": 2},
    )

    assert review["deterministic_bitmap_status"] == "PASS"
    assert review["overall_status"] == "PASS_WITH_SEMANTIC_REVIEW_PENDING"
    assert review["metrics"]["colored_pixel_ratio"] > 0


def test_official_projection_uses_v3_semantic_and_clips_long_structure_line():
    pack = _pack()
    structure = pack["detector_candidates"]["15m"]["structure_breaks"][0]
    structure.update(
        {
            "direction": "bearish",
            "break_type": "CHOCH",
            "pivot_time": pack["ohlcv_windows"]["15m"][0]["timestamp"],
            "confirmed_at": pack["ohlcv_windows"]["15m"][19]["timestamp"],
        }
    )
    pack["formal_causal_episode_graph"] = {
        "schema": "formal_causal_episode_graph_v2",
        "authority_contract": {"enforcement_ready": True},
        "timeframes": {
            "15m": {
                "episodes": [
                    {
                        "structure_event_id": "break-1",
                        "event_type": "EXTERNAL_MSS_CONFIRMED_BEARISH",
                        "scope": "external",
                    }
                ],
                "latest_external_episode": {
                    "structure_event_id": "break-1",
                    "event_type": "EXTERNAL_MSS_CONFIRMED_BEARISH",
                    "scope": "external",
                },
                "latest_internal_episode": None,
            }
        },
    }
    pack["causal_poi_authority"] = {"scenarios": {}}

    plan = compose_local_annotation_plan_v2(
        evidence_pack=pack,
        official_state="REVIEW_REQUIRED",
        direction="bearish",
        active_range={},
        active_poi=None,
    )
    structure_object = next(obj for obj in plan["objects"] if obj["object_type"] == "structure_segment")

    assert structure_object["label"] == "MSS"
    assert structure_object["kind"] == "structure"
    assert structure_object["end_index"] - structure_object["start_index"] <= 18
    assert structure_object["end_index"] == 19
