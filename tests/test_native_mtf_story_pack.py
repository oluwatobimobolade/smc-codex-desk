from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from smc_desk.brain.annotation_candidate_composer import compose_local_annotation_plan_v2
from smc_desk.rendering.bitmap_annotation_review import review_rendered_annotation_bitmap
from smc_desk.rendering.native_mtf_story_pack import build_native_mtf_storyboards


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
