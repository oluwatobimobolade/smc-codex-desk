from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.annotation_geometry import build_geometry_contract
from smc_desk.perception.evidence_contract import build_object_evidence_contracts
from smc_desk.rendering.smc_trader_annotation_renderer import (
    build_smc_trader_annotation_scene,
    render_smc_trader_annotation_chart,
)
from tests.test_wp0034_ai_smc_trader_brain import (
    _decision,
    _df,
    _issue_codes,
    _pack,
    _watch_payload,
)


def _v2_objects() -> list[dict]:
    return [
        {
            "object_type": "structure_segment",
            "semantic_object_id": "break1:local_bos",
            "timeframe": "15m",
            "label": "BOS",
            "reason": "Local structure break after the sweep; drawn as a short segment only.",
            "kind": "bos",
            "direction": "bearish",
            "price": 98.0,
            "start_index": 5,
            "end_index": 11,
            "line_style": "solid",
            "structure_scope": "external",
            "evidence_object_ids": ["break1"],
            "importance": 1,
        },
        {
            "object_type": "poi_zone",
            "semantic_object_id": "poi1:active_supply",
            "timeframe": "15m",
            "label": "OB",
            "reason": "Bearish supply order block candidate selected as the active POI.",
            "kind": "order_block",
            "direction": "bearish",
            "price_low": 100.0,
            "price_high": 101.0,
            "start_index": 12,
            "end_index": 18,
            "line_style": "solid",
            "evidence_object_ids": ["poi1"],
            "importance": 1,
        },
        {
            "object_type": "liquidity_line",
            "semantic_object_id": "liq1:sell_side_draw",
            "timeframe": "15m",
            "label": "SSL",
            "reason": "Sell-side liquidity is the model-completion draw.",
            "kind": "liquidity",
            "direction": "bearish",
            "price": 95.0,
            "start_index": 10,
            "end_index": 19,
            "line_style": "dotted",
            "evidence_object_ids": ["liq1"],
            "importance": 2,
        },
        {
            "object_type": "path_projection",
            "semantic_object_id": "watch:path",
            "timeframe": "15m",
            "label": "PATH",
            "reason": "Conditional watch path only, not a guaranteed forecast.",
            "kind": "path",
            "direction": "bearish",
            "price_low": 100.5,
            "price_high": 95.0,
            "start_index": 15,
            "end_index": 19,
            "line_style": "dashed",
            "evidence_object_ids": [],
            "importance": 3,
        },
    ]


def _watch_payload_with_v2() -> dict:
    payload = _watch_payload()
    objects = _v2_objects()
    for obj in objects:
        obj.update(
            build_geometry_contract(
                evidence=obj,
                source_object_ids=obj.get("evidence_object_ids") or [],
                anchor_mode="conditional_projection" if obj["object_type"] == "path_projection" else "exact_source",
                clipping_rule="conditional_projection" if obj["object_type"] == "path_projection" else "none",
            )
        )
    payload["annotation_plan_v2"] = {
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": objects,
        "notes": ["professional sparse SMC markup"],
    }
    return payload


def _pack_with_v2_geometry() -> dict:
    pack = deepcopy(_pack())
    window = pack["ohlcv_windows"]["15m"]
    # Keep the fixture POI partially touched but not fully consumed after confirmation.
    window[19]["high"] = 100.5
    stamps = [str(candle["timestamp"]) for candle in window]
    breaks = pack["detector_candidates"]["15m"]["structure_breaks"]
    breaks[0].update(
        {
            "break_type": "BOS",
            "structure_scope": "external",
            "pivot_time": stamps[5],
            "candidate_at": stamps[11],
            "confirmed_at": stamps[11],
            "evidence": {"broken_price": 98.0, "structure_scope": "external"},
            "confirmation_status": "confirmed",
            "activity_status": "inactive",
            "mitigation_status": "untouched",
        }
    )
    poi = pack["detector_candidates"]["15m"]["order_blocks"][0]
    poi.update({"pivot_time": stamps[12], "candidate_at": stamps[18], "confirmed_at": stamps[18], "confirmation_status": "confirmed", "activity_status": "inactive", "mitigation_status": "untouched"})
    liquidity = pack["detector_candidates"]["15m"]["liquidity_levels"][0]
    liquidity.update({"pivot_time": stamps[10], "candidate_at": stamps[19], "confirmed_at": stamps[19], "confirmation_status": "confirmed", "activity_status": "inactive", "mitigation_status": "untouched"})
    pack["object_evidence_contracts"] = build_object_evidence_contracts(
        detector_candidates=pack["detector_candidates"],
        decision_time=stamps[-1],
        doctrine_hash="test-doctrine-hash",
        formal_structure_graph=pack.get("formal_structure_graph") or {},
    )
    return pack


def test_wp0041_valid_professional_annotation_plan_v2_renders(tmp_path: Path) -> None:
    result = validate_ai_smc_decision(_decision(_watch_payload_with_v2()), _pack_with_v2_geometry())
    assert result.status == "VALIDATED"

    scene = build_smc_trader_annotation_scene(result)
    assert scene["level_source"] == "annotation_plan_v2"
    assert scene["drawing_object_count"] == 4
    assert scene["visible_drawing_object_count"] == 3

    output = tmp_path / "professional_annotation.png"
    rendered_scene = render_smc_trader_annotation_chart(_df(), result, output)
    assert output.exists()
    assert rendered_scene["level_source"] == "annotation_plan_v2"


def test_wp0041_rejects_full_width_structure_segment() -> None:
    payload = _watch_payload_with_v2()
    payload["annotation_plan_v2"]["objects"][0]["start_index"] = 0
    payload["annotation_plan_v2"]["objects"][0]["end_index"] = 19

    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_structure_segment_too_wide" in _issue_codes(result)


def test_wp0041_rejects_fvg_mislabeled_as_order_block() -> None:
    payload = _watch_payload_with_v2()
    payload["annotation_plan_v2"]["objects"][1]["semantic_object_id"] = "fvg1:mislabeled_ob"
    payload["annotation_plan_v2"]["objects"][1]["evidence_object_ids"] = ["fvg1"]

    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_fvg_mislabeled_as_ob" in _issue_codes(result)


def test_wp0041_watch_state_cannot_draw_trade_box() -> None:
    payload = _watch_payload_with_v2()
    payload["annotation_plan_v2"]["objects"].append(
        {
            "object_type": "trade_box",
            "semantic_object_id": "bad:trade_box",
            "timeframe": "15m",
            "label": "ENTRY",
            "reason": "Bad test object: watch states must not expose trade boxes.",
            "kind": "trade",
            "direction": "bearish",
            "price": 100.0,
            "entry_price": 100.0,
            "stop_price": 101.0,
            "target_prices": [95.0],
            "start_index": 14,
            "end_index": 19,
            "line_style": "solid",
            "evidence_object_ids": ["poi1"],
            "importance": 1,
        }
    )

    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_watch_contains_trade_object" in _issue_codes(result)
    assert "annotation_v2_trade_box_without_trade_ready" in _issue_codes(result)
    assert result.official_decision["annotation_plan_v2"]["objects"][-1]["object_type"] != "trade_box"


def test_wp0041_parent_child_conflict_blocks_clean_structure_annotation() -> None:
    pack = _pack_with_v2_geometry()
    pack["formal_structure_graph"]["parent_child_context"]["has_conflict"] = True
    payload = _watch_payload_with_v2()

    result = validate_ai_smc_decision(_decision(payload), pack)

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_internal_structure_drawn_as_parent_bias" in _issue_codes(result)
