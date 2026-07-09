from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.annotation_visual_critic import review_annotation_scene
from smc_desk.rendering.smc_trader_annotation_renderer import (
    build_smc_trader_annotation_scene,
    render_smc_trader_annotation_chart,
)
from tests.test_wp0034_ai_smc_trader_brain import _decision, _df, _issue_codes, _valid_payload
from tests.test_wp0041_professional_annotation_planner import _pack_with_v2_geometry, _watch_payload_with_v2


def test_wp0041a_rejects_real_evidence_id_with_invented_bos_geometry() -> None:
    payload = _watch_payload_with_v2()
    obj = payload["annotation_plan_v2"]["objects"][0]
    obj["price"] = 999_999.0
    obj["start_index"] = 0
    obj["end_index"] = 1

    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_structure_price_mismatch" in _issue_codes(result)
    assert "annotation_v2_structure_span_mismatch" in _issue_codes(result)


def test_wp0041a_rejects_internal_break_disguised_as_external_structure() -> None:
    pack = _pack_with_v2_geometry()
    internal = deepcopy(pack["detector_candidates"]["15m"]["structure_breaks"][0])
    internal.update({"object_id": "break_internal", "structure_scope": "internal"})
    internal["evidence"] = {"broken_price": 98.0, "structure_scope": "internal"}
    pack["detector_candidates"]["15m"]["structure_breaks"].append(internal)
    payload = _watch_payload_with_v2()
    obj = payload["annotation_plan_v2"]["objects"][0]
    obj["semantic_object_id"] = "break_internal:fake_external"
    obj["evidence_object_ids"] = ["break_internal"]
    obj["structure_scope"] = "external"
    obj["label"] = "BOS"

    result = validate_ai_smc_decision(_decision(payload), pack)

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_structure_scope_mismatch" in _issue_codes(result)
    assert "annotation_v2_internal_structure_not_labeled" in _issue_codes(result)


def test_wp0041a_path_requires_a_certified_active_poi() -> None:
    payload = _watch_payload_with_v2()
    payload["active_poi"]["poi_id"] = None
    payload["active_poi"]["evidence_object_ids"] = []

    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_path_without_active_poi" in _issue_codes(result)


def test_wp0041a_trade_box_is_v2_native_and_suppresses_legacy_text(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["annotation_plan_v2"] = {
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": [
            {
                "object_type": "trade_box",
                "semantic_object_id": "poi1:validated_trade_box",
                "timeframe": "15m",
                "label": "TRADE",
                "reason": "All V2 levels match the validated entry, structural stop, and model-completion target.",
                "kind": "trade",
                "direction": "bearish",
                "price": 100.5,
                "price_low": 95.0,
                "price_high": 102.0,
                "entry_price": 100.5,
                "stop_price": 102.0,
                "target_prices": [95.0],
                "start_index": 14,
                "end_index": 25,
                "line_style": "solid",
                "evidence_object_ids": ["poi1", "liq1"],
                "importance": 1,
            }
        ],
        "notes": [],
    }
    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    assert result.status == "VALIDATED"
    scene = build_smc_trader_annotation_scene(result)
    assert scene["level_source"] == "annotation_plan_v2"
    assert scene["visible_labels"] == []
    assert scene["legacy_labels_suppressed"] is True
    output = tmp_path / "v2_trade_box.png"
    rendered = render_smc_trader_annotation_chart(_df(), result, output)
    assert output.exists()
    assert rendered["visual_critic"]["status"] == "PASSED"


def test_wp0041a_visual_critic_requests_cleanup_for_overlapping_marks() -> None:
    df = _df()
    scene = {
        "level_source": "annotation_plan_v2",
        "chart_template": "watch_chart",
        "visible_labels": [],
        "visible_drawing_objects": [
            {"semantic_object_id": "a", "object_type": "liquidity_line", "label": "BSL", "price": 100.0, "start_index": 10, "end_index": 16, "importance": 1},
            {"semantic_object_id": "b", "object_type": "liquidity_line", "label": "EQL", "price": 100.01, "start_index": 11, "end_index": 17, "importance": 3},
        ],
    }

    review = review_annotation_scene(scene, df)

    assert review["status"] == "CLEANUP_REQUIRED"
    assert review["cleanup_object_ids"] == ["b"]
