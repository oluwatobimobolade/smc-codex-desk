from __future__ import annotations

from datetime import datetime, timedelta, timezone

from smc_desk.brain.annotation_evidence import build_annotation_evidence_index
from smc_desk.brain.structure_lab.annotation_bridge import resolve_semantic_annotation_plan
from smc_desk.rendering.structure_lab_annotation_renderer import render_structure_lab_annotation_pack


def _candles(timeframe_hours: int) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(30):
        base = 100.0 + index * 0.12
        rows.append(
            {
                "timestamp": (start + timedelta(hours=timeframe_hours * index)).isoformat(),
                "open": base,
                "high": base + 0.8,
                "low": base - 0.7,
                "close": base + (0.35 if index % 2 == 0 else -0.25),
                "volume": 1000 + index,
            }
        )
    return rows


def _pack() -> dict:
    four_hour = _candles(4)
    one_hour = _candles(1)
    return {
        "symbol": "BTCUSDT",
        "ohlcv_windows": {"4h": four_hour, "1h": one_hour},
        "detector_candidates": {
            "4h": {
                "structure_breaks": [
                    {
                        "object_id": "break-4h",
                        "object_type": "structure_break",
                        "timeframe": "4h",
                        "direction": "bearish",
                        "break_type": "CHOCH",
                        "structure_scope": "external",
                        "pivot_time": four_hour[10]["timestamp"],
                        "confirmed_at": four_hour[20]["timestamp"],
                        "confirmation_status": "confirmed",
                        "evidence": {"broken_price": 101.2, "structure_scope": "external"},
                    }
                ]
            },
            "1h": {
                "structure_breaks": [
                    {
                        "object_id": "break-1h",
                        "object_type": "structure_break",
                        "timeframe": "1h",
                        "direction": "bullish",
                        "break_type": "CHOCH",
                        "structure_scope": "external",
                        "pivot_time": one_hour[5]["timestamp"],
                        "confirmed_at": one_hour[12]["timestamp"],
                        "confirmation_status": "confirmed",
                        "evidence": {"broken_price": 101.8, "structure_scope": "external"},
                    }
                ]
            },
        },
        "active_range_authority": {
            "timeframe": "4h",
            "source_pivots": [
                {
                    "pivot_id": "protected-high-4h",
                    "timeframe": "4h",
                    "kind": "high",
                    "price": 104.5,
                    "timestamp": four_hour[15]["timestamp"],
                }
            ],
        },
        "formal_structure_graph": {
            "active_range": {
                "range_id": "range-4h",
                "timeframe": "4h",
                "direction": "bearish",
                "low": 98.0,
                "high": 104.5,
            },
            "authority_contract": {"signal_allowed": False},
        },
    }


def _semantic_plan() -> dict:
    return {
        "schema": "semantic_annotation_selection_v1",
        "role": "annotation_planner",
        "selections": [
            {
                "object_type": "structure_segment",
                "semantic_object_id": "break-4h",
                "timeframe": "4h",
                "label": "4H CHoCH",
                "reason": "Controlling parent break.",
                "priority": 1,
            },
            {
                "object_type": "liquidity_line",
                "semantic_object_id": "protected-high-4h",
                "timeframe": "4h",
                "label": "Protected High",
                "reason": "Parent invalidation reference.",
                "priority": 2,
            },
            {
                "object_type": "structure_segment",
                "semantic_object_id": "break-1h",
                "timeframe": "1h",
                "label": "1H CHoCH (stale recovery)",
                "reason": "Child recovery is stale and subordinate to the parent.",
                "priority": 3,
            },
        ],
        "hidden_evidence_ids": [],
        "clutter_budget": 3,
        "geometry_source": "certified_evidence_resolver",
        "trade_box_allowed": False,
    }


def test_wp0041b_resolves_ai_selections_from_certified_geometry() -> None:
    pack = _pack()
    evidence = build_annotation_evidence_index(pack)
    resolution = resolve_semantic_annotation_plan(_semantic_plan(), pack)

    assert evidence["protected-high-4h"].source == "active_range_authority.source_pivots"
    assert resolution["status"] == "PASS"
    assert resolution["resolved_object_count"] == 3
    assert resolution["timeframes"] == ["1h", "4h"]
    objects = {item["semantic_object_id"]: item for item in resolution["annotation_plan_v2"]["objects"]}
    assert objects["break-4h"]["label"] == "4H External CHoCH"
    assert objects["break-1h"]["label"] == "1H External CHoCH"
    assert objects["protected-high-4h"]["label"] == "4H Protected High"
    assert resolution["label_authority"] == "deterministic_annotation_semantics_v1"
    assert len(resolution["label_overrides"]) == 3
    assert objects["break-4h"]["price"] == 101.2
    assert objects["break-4h"]["start_index"] == 10
    assert objects["break-4h"]["end_index"] == 20
    assert objects["break-1h"]["line_style"] == "dashed"
    assert objects["protected-high-4h"]["price"] == 104.5


def test_wp0041b_renderer_writes_real_multitimeframe_images_and_pixel_proof(tmp_path) -> None:
    manifest = render_structure_lab_annotation_pack(
        evidence_pack=_pack(),
        semantic_plan=_semantic_plan(),
        output_dir=tmp_path,
        official_state="THESIS_ONLY",
    )

    assert manifest["status"] == "PASS"
    assert manifest["timeframes"] == ["4h", "1h"]
    assert manifest["rendered_image_count"] == 2
    assert manifest["planned_object_count"] == manifest["rendered_object_count"] == 3
    assert manifest["all_planned_objects_rendered"] is True
    assert manifest["trade_box_rendered"] is False
    assert (tmp_path / "annotation_self_review.md").exists()
    for image in manifest["images"]:
        assert image["pixel_review"]["status"] == "PASS"
        assert image["pixel_review"]["changed_pixel_count"] >= image["pixel_review"]["minimum_changed_pixel_count"]
        assert image["scene"]["text_panel_rendered"] is False
        assert image["scene"]["full_width_structure_line_rendered"] is False


def test_wp0041b_empty_ai_plan_fails_closed_without_fake_visual_pass(tmp_path) -> None:
    plan = {**_semantic_plan(), "selections": [], "clutter_budget": 1}
    manifest = render_structure_lab_annotation_pack(
        evidence_pack=_pack(),
        semantic_plan=plan,
        output_dir=tmp_path,
    )

    assert manifest["status"] == "REVIEW_REQUIRED"
    assert manifest["rendered_image_count"] == 0
    assert manifest["all_planned_objects_rendered"] is False
