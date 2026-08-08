from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.annotation_visual_critic import apply_visual_cleanup, review_annotation_scene
from smc_desk.brain.annotation_candidate_composer import compose_local_annotation_plan_v2, select_local_active_poi
from smc_desk.brain.annotation_evidence import build_annotation_evidence_index
from smc_desk.colleague.orchestrator_v3 import apply_visual_critic_authority
from smc_desk.rendering.smc_trader_annotation_renderer import (
    _level_x_span,
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
    assert "annotation_v2_top_level_not_display_geometry" in _issue_codes(result)


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


def test_wp0041a_wick_probe_cannot_be_drawn_as_confirmed_bos() -> None:
    pack = _pack_with_v2_geometry()
    probe = pack["detector_candidates"]["15m"]["structure_breaks"][0]
    probe["confirmation_status"] = "candidate"
    probe["evidence"]["is_unconfirmed_probe"] = True
    payload = _watch_payload_with_v2()

    result = validate_ai_smc_decision(_decision(payload), pack)

    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_structure_not_confirmed" in _issue_codes(result)


def test_wp0041a_local_composer_selects_confirmed_watch_poi_without_trade_levels() -> None:
    pack = _pack_with_v2_geometry()
    pack["ohlcv_windows"]["15m"][19]["high"] = 100.5
    active_range = {"low": 95.0, "high": 103.0, "range_id": "test:range1"}

    active_poi = select_local_active_poi(evidence_pack=pack, direction="bearish", active_range=active_range)
    plan = compose_local_annotation_plan_v2(
        evidence_pack=pack,
        official_state="WATCH_ONLY",
        direction="bearish",
        active_range=active_range,
        active_poi=active_poi,
    )

    assert active_poi is not None
    assert active_poi["poi_id"] == "poi1"
    assert active_poi["freshness"] == "partially_mitigated"
    assert any(obj["object_type"] == "poi_zone" for obj in plan["objects"])
    assert any(obj["object_type"] == "path_projection" for obj in plan["objects"])
    assert all(obj["object_type"] != "trade_box" for obj in plan["objects"])


def test_wp0041a_mixed_context_draws_scenario_poi_and_material_mtf_breaks() -> None:
    pack = _pack_with_v2_geometry()
    window_15m = pack["ohlcv_windows"]["15m"]
    window_1h = [deepcopy(window_15m[index]) for index in (0, 4, 8, 12, 16)]
    pack["ohlcv_windows"]["1h"] = window_1h
    pack["detector_candidates"]["1h"] = {
        "structure_breaks": [
            {
                "object_id": "break_1h",
                "object_type": "structure_break",
                "timeframe": "1h",
                "direction": "bullish",
                "break_type": "BOS",
                "structure_scope": "external",
                "pivot_time": window_1h[0]["timestamp"],
                "confirmed_at": window_1h[2]["timestamp"],
                "confirmation_status": "confirmed",
                "activity_status": "inactive",
                "mitigation_status": "untouched",
                "evidence": {"broken_price": 101.0, "structure_scope": "external"},
            }
        ]
    }
    pack["formal_structure_graph"] = {
        "timeframes": {
            "1h": {"latest_external_break": {"object_id": "break_1h"}},
            "15m": {"latest_external_break": {"object_id": "break1"}},
        }
    }
    pack["causal_poi_authority"] = {
        "authority_contract": {"enforcement_ready": True},
        "scenarios": {
            "bearish": {
                "status": "SELECTED",
                "controlling_timeframe": "15m",
                "primary_causal_poi": {
                    "poi_id": "15m:order_block:poi1",
                    "source_object_id": "poi1",
                    "timeframe": "15m",
                    "kind": "order_block",
                    "direction": "bearish",
                    "price_low": 100.0,
                    "price_high": 101.0,
                    "freshness": "partial",
                    "lineage_role": "latest_external_continuation_origin",
                    "range_location": "premium",
                },
                "execution_refinements": [],
            },
            "bullish": {"status": "UNRESOLVED"},
        },
    }

    plan = compose_local_annotation_plan_v2(
        evidence_pack=pack,
        official_state="THESIS_ONLY",
        direction="mixed",
        active_range={},
        active_poi=None,
    )

    assert [obj["object_type"] for obj in plan["objects"]] == [
        "poi_zone",
        "structure_segment",
        "structure_segment",
    ]
    assert {obj["timeframe"] for obj in plan["objects"] if obj["object_type"] == "structure_segment"} == {"1h", "15m"}
    assert all(obj["object_type"] != "trade_box" for obj in plan["objects"])
    assert "no trade is authorized" in plan["objects"][0]["reason"].lower()


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

    cleaned = apply_visual_cleanup(scene, df)
    assert cleaned["visual_critic"]["pre_cleanup_status"] == "CLEANUP_REQUIRED"
    assert cleaned["visual_critic"]["status"] == "PASSED"
    assert cleaned["visual_critic"]["cleanup_applied"] == ["b"]


def test_wp0041a_visual_critic_hard_failure_downgrades_official_decision() -> None:
    result = validate_ai_smc_decision(_decision(_valid_payload()), _pack_with_v2_geometry())
    review = {
        "status": "REVIEW_REQUIRED",
        "issues": [{"code": "forced_visual_failure", "message": "Official annotation scene failed layout integrity."}],
    }

    downgraded = apply_visual_critic_authority(result, review)

    assert result.status == "VALIDATED"
    assert downgraded.status == "REVIEW_REQUIRED"
    assert downgraded.official_decision["official_state"] == "REVIEW_REQUIRED"
    assert downgraded.official_decision["annotation_plan"]["show_trade_box"] is False
    assert downgraded.official_decision["entry_plan"]["entry_price"] is None
    assert downgraded.official_decision["stop_loss_plan"]["stop_price"] is None
    assert downgraded.official_decision["target_plan"]["targets"] == []


def test_wp0041a_empty_v2_plan_suppresses_legacy_clutter() -> None:
    payload = _watch_payload_with_v2()
    payload["annotation_plan_v2"]["objects"] = []
    result = validate_ai_smc_decision(_decision(payload), _pack_with_v2_geometry())

    scene = build_smc_trader_annotation_scene(result)

    assert result.status == "VALIDATED"
    assert scene["level_source"] == "annotation_plan_v2"
    assert scene["visible_labels"] == []
    assert scene["visible_levels"] == []
    assert scene["legacy_labels_suppressed"] is True


def test_wp0041a_one_candle_poi_is_locally_visible_but_not_full_width() -> None:
    left, right = _level_x_span(
        {"kind": "order_block", "start_index": 0, "end_index": 0},
        n=120,
        chart_template="watch_chart",
    )

    assert left == 0.0
    assert right == 12.0
    assert right < 120 * 0.15


def test_wp0041a_out_of_window_evidence_is_not_snapped_to_chart_edge() -> None:
    pack = _pack_with_v2_geometry()
    poi = pack["detector_candidates"]["15m"]["order_blocks"][0]
    poi.update(
        {
            "pivot_time": "2026-06-01T00:00:00Z",
            "candidate_at": "2026-06-01T00:15:00Z",
            "confirmed_at": "2026-06-01T00:15:00Z",
        }
    )

    anchor = build_annotation_evidence_index(pack)["poi1"]
    active_poi = select_local_active_poi(
        evidence_pack=pack,
        direction="bearish",
        active_range={"low": 95.0, "high": 103.0, "range_id": "test:range1"},
    )

    assert anchor.start_index is None
    assert anchor.end_index is None
    assert active_poi is None

    payload = _watch_payload_with_v2()
    result = validate_ai_smc_decision(_decision(payload), pack)
    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_evidence_outside_visible_window" in _issue_codes(result)
    assert "annotation_v2_poi_lifecycle_unverifiable" in _issue_codes(result)


def test_wp0041a_consumed_order_block_cannot_be_selected_as_active_poi() -> None:
    pack = _pack_with_v2_geometry()
    pack["ohlcv_windows"]["15m"][19].update({"high": 101.5, "close": 100.5})

    active_poi = select_local_active_poi(
        evidence_pack=pack,
        direction="bearish",
        active_range={"low": 95.0, "high": 103.0, "range_id": "test:range1"},
    )

    assert active_poi is None

    result = validate_ai_smc_decision(_decision(_watch_payload_with_v2()), pack)
    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_v2_poi_observed_consumed" in _issue_codes(result)
