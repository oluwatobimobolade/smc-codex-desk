from __future__ import annotations

from smc_desk.brain.ai_smc_trader_brain import AnnotationDrawingObject
from smc_desk.brain.annotation_evidence import AnnotationEvidenceAnchor
from smc_desk.brain.annotation_geometry import build_geometry_contract, geometry_hash
from smc_desk.brain.annotation_plan_validator import _check_geometry_contract
from smc_desk.perception.evidence_contract import build_object_evidence_contracts, contract_ids_for_object
from smc_desk.rendering.smc_trader_annotation_renderer import _object_with_display_geometry


def _structure_object() -> AnnotationDrawingObject:
    geometry = build_geometry_contract(
        evidence={
            "start_index": 5,
            "end_index": 40,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T08:45:00Z",
            "price": 100.0,
            "price_low": None,
            "price_high": None,
        },
        display={
            "start_index": 22,
            "end_index": 40,
            "start_time": None,
            "end_time": None,
            "price": 100.0,
            "price_low": None,
            "price_high": None,
        },
        source_object_ids=["break-1"],
        clipping_rule="confirmation_side_max_18_bars",
    )
    return AnnotationDrawingObject.model_validate(
        {
            "object_type": "structure_segment",
            "semantic_object_id": "break-1:segment",
            "timeframe": "15m",
            "label": "BOS",
            "reason": "Confirmed external break.",
            "kind": "bos",
            "direction": "bullish",
            "price": 100.0,
            "start_index": 22,
            "end_index": 40,
            "structure_scope": "external",
            "evidence_object_ids": ["break-1"],
            "evidence_contract_ids": ["break-1"],
            **geometry,
        }
    )


def _anchor() -> AnnotationEvidenceAnchor:
    return AnnotationEvidenceAnchor(
        object_id="break-1",
        evidence_type="structure",
        timeframe="15m",
        direction="bullish",
        structure_scope="external",
        kind="bos",
        price_low=100.0,
        price_high=100.0,
        exact_price=100.0,
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T08:45:00Z",
        start_index=5,
        end_index=40,
        confirmation_status="confirmed",
        activity_status="active",
        mitigation_status="untouched",
        is_wick_only_probe=False,
        evidence_strength=0.8,
        source="test",
    )


def test_exact_evidence_geometry_survives_display_clipping() -> None:
    obj = _structure_object()
    issues = []
    _check_geometry_contract(obj, [_anchor()], issues)
    assert issues == []
    assert obj.evidence_geometry.start_index == 5
    assert obj.display_geometry.start_index == 22
    assert obj.evidence_geometry.geometry_hash == obj.display_geometry.derived_from_evidence_hash


def test_renderer_reads_display_geometry_without_destroying_source_geometry() -> None:
    raw = _structure_object().model_dump(mode="json")
    rendered = _object_with_display_geometry(raw)
    assert rendered["start_index"] == 22
    assert rendered["evidence_geometry"]["start_index"] == 5


def test_display_price_change_is_a_hard_geometry_issue() -> None:
    raw = _structure_object().model_dump(mode="json")
    raw["display_geometry"]["price"] = 101.0
    raw["price"] = 101.0
    obj = AnnotationDrawingObject.model_validate(raw)
    issues = []
    _check_geometry_contract(obj, [_anchor()], issues)
    assert "annotation_v2_display_changed_price" in {issue.code for issue in issues}


def test_geometry_hash_detects_source_tampering() -> None:
    raw = _structure_object().model_dump(mode="json")
    original_hash = raw["evidence_geometry"]["geometry_hash"]
    raw["evidence_geometry"]["start_index"] = 6
    assert geometry_hash(raw["evidence_geometry"]) != original_hash


def test_object_evidence_contract_refuses_fake_probability() -> None:
    registry = build_object_evidence_contracts(
        detector_candidates={
            "15m": {
                "structure_breaks": [
                    {
                        "object_id": "break-1",
                        "object_type": "structure_break",
                        "break_type": "BOS",
                        "direction": "bullish",
                        "structure_scope": "external",
                        "pivot_time": "2026-01-01T00:00:00Z",
                        "confirmed_at": "2026-01-01T00:15:00Z",
                        "price_low": 100.0,
                        "price_high": 100.0,
                        "evidence_strength": 0.82,
                        "evidence": {"broken_price": 100.0},
                    }
                ]
            }
        },
        decision_time="2026-01-01T00:15:00Z",
        doctrine_hash="doctrine-hash",
    )
    contract_id = contract_ids_for_object(registry, "break-1", timeframe="15m")[0]
    contract = registry["contracts"][contract_id]
    assert contract["contract_status"] == "COMPLETE"
    assert contract["confidence"] is None
    assert contract["confidence_status"] == "UNAVAILABLE_UNCALIBRATED"
    assert contract["evidence_strength"] == 0.82
    assert contract["first_knowable_candle"] == "2026-01-01T00:15:00Z"
    assert contract["competing_interpretations"]


def test_poi_lifecycle_history_supplies_complete_temporal_contract() -> None:
    registry = build_object_evidence_contracts(
        detector_candidates={
            "1h": {
                "active_pois": [
                    {
                        "object_id": "poi-1",
                        "object_type": "order_block",
                        "direction": "bullish",
                        "price_low": 98.0,
                        "price_high": 100.0,
                        "status": "active",
                        "event_history": [
                            {"event_type": "OBJECT_CREATED", "timestamp": "2026-01-01T00:00:00Z"},
                            {"event_type": "OBJECT_CONFIRMED", "timestamp": "2026-01-01T01:00:00Z"},
                        ],
                    }
                ]
            }
        },
        decision_time="2026-01-01T02:00:00Z",
        doctrine_hash="doctrine-hash",
    )
    contract_id = contract_ids_for_object(registry, "poi-1", timeframe="1h")[0]
    contract = registry["contracts"][contract_id]
    assert contract["contract_status"] == "COMPLETE"
    assert contract["first_knowable_candle"] == "2026-01-01T01:00:00Z"
    assert registry["incomplete_contract_ids"] == []
