"""WP-0044 stabilization: the AI semantic-selection schema and the certified
evidence resolver must agree on which object types the AI may select.

Regression net for the contract mismatch the v9 review found: the AI selection
schema (``AnnotationSelection``) advertised ``path_projection`` even though the
certified resolver (``annotation_bridge._resolve_selection``) has no branch for
it, so a valid AI selection was silently rejected.

The fix: ``path_projection`` is removed from the AI-selectable set. A forward
projecting arrow past the last candle is mild forecast authority the AI must not
hold; the deterministic conservative composer remains the only sanctioned
emitter, gated on a certified active POI and an official state in
``PATH_ALLOWED_STATES``.
"""
from __future__ import annotations

import json

import pytest

from smc_desk.brain.structure_lab.prompts import (
    build_role_prompt,
    compact_candidate_objects,
)
from smc_desk.brain.structure_lab.schemas import AnnotationSelection


def test_ai_cannot_select_path_projection() -> None:
    """path_projection must be rejected at the AI selection schema boundary."""
    with pytest.raises(Exception):
        AnnotationSelection.model_validate(
            {
                "object_type": "path_projection",
                "semantic_object_id": "ob1:conditional_path",
                "timeframe": "15m",
                "label": "PATH",
                "reason": "route",
                "priority": 2,
            }
        )


def test_ai_can_select_the_three_certified_object_types() -> None:
    for kind in ("structure_segment", "poi_zone", "liquidity_line"):
        sel = AnnotationSelection.model_validate(
            {
                "object_type": kind,
                "semantic_object_id": "ob1",
                "timeframe": "15m",
                "label": kind.upper(),
                "reason": "certified evidence",
                "priority": 2,
            }
        )
        assert sel.object_type == kind


def test_resolver_rejects_path_projection_selection_with_named_issue() -> None:
    """If a path_projection slips past the schema, the resolver names it."""
    from smc_desk.brain.structure_lab.annotation_bridge import resolve_semantic_annotation_plan

    # Minimal evidence pack with one confirmed structure anchor.
    evidence_pack = {
        "ohlcv_windows": {
            "15m": [{"timestamp": f"2026-01-01T00:{i:02d}:00Z", "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1} for i in range(40)],
        },
        "detector_candidates": {
            "15m": {
                "structure_breaks": [
                    {
                        "object_id": "brk1",
                        "timeframe": "15m",
                        "direction": "bullish",
                        "break_type": "bos",
                        "price": 1.0,
                        "confirmation_status": "confirmed",
                        "activity_status": "active",
                        "mitigation_status": "untouched",
                        "is_wick_only_probe": False,
                        "evidence": {"broken_price": 1.0, "structure_scope": "external"},
                        "pivot_time": "2026-01-01T00:00:00Z",
                        "confirmed_at": "2026-01-01T00:05:00Z",
                    }
                ],
            }
        },
    }
    semantic_plan = {
        "schema": "semantic_annotation_selection_v1",
        "role": "annotation_planner",
        "selections": [
            {
                "object_type": "path_projection",
                "semantic_object_id": "brk1",
                "timeframe": "15m",
                "label": "PATH",
                "reason": "route",
                "priority": 2,
            }
        ],
        "hidden_evidence_ids": [],
        "clutter_budget": 3,
        "geometry_source": "certified_evidence_resolver",
        "trade_box_allowed": False,
    }
    result = resolve_semantic_annotation_plan(semantic_plan, evidence_pack)
    codes = {issue["code"] for issue in result["issues"]}
    assert "unsupported_semantic_object_type" in codes
    assert result["resolved_object_count"] == 0


def test_v2_plan_schema_still_accepts_deterministic_path_projection() -> None:
    """The deterministic composer path must still be able to emit path_projection.

    The v2 drawing-object schema (AnnotationDrawingObject) retains path_projection
    so the conservative local composer can draw a certified conditional route.
    Only the AI selection surface dropped it.
    """
    from smc_desk.brain.ai_smc_trader_brain import AnnotationDrawingObject, AnnotationPlanV2

    obj = AnnotationDrawingObject.model_validate(
        {
            "object_type": "path_projection",
            "semantic_object_id": "poi1:conditional_path",
            "timeframe": "15m",
            "label": "PATH",
            "reason": "conditional route",
            "direction": "bullish",
            "kind": "path",
            "price_low": 100.0,
            "price_high": 110.0,
            "start_index": 37,
            "end_index": 45,
            "start_time": "2026-01-01T00:37:00Z",
            "end_time": "2026-01-01T00:45:00Z",
            "line_style": "dashed",
            "evidence_object_ids": ["poi1"],
            "importance": 3,
        }
    )
    assert obj.object_type == "path_projection"
    # And a full v2 plan with it validates (AnnotationPlanV2 is minimal:
    # schema, style, objects, notes -- the check fields live on SelfReview).
    AnnotationPlanV2.model_validate(
        {
            "schema": "professional_smc_annotation_plan_v2",
            "style": "professional_smc_sparse",
            "objects": [obj.model_dump(mode="json", by_alias=True)],
            "notes": ["conditional route emitted by the deterministic composer"],
        }
    )


# --- WP-0044 stabilization: prompt compaction -------------------------------


def _fat_candidates(count: int, *, confirmed_at: str) -> dict:
    """A candidate catalog with the bloat fields the compactor must drop."""
    return {
        "15m": {
            "swings": [
                {
                    "object_id": f"swing_{i}",
                    "direction": "bullish",
                    "scale": "external",
                    "confirmation_status": "confirmed",
                    "price": 100.0 + i,
                    "confirmed_at": confirmed_at,
                    "pivot_time": confirmed_at,
                    # bloat fields that must be dropped:
                    "events": [{"event_type": "OBJECT_CREATED", "trigger_candle_id": f"c_{i}"}] * 5,
                    "evidence": {"nested_blob": "x" * 400},
                    "source_candle_ids": [f"c_{j}" for j in range(50)],
                    "configuration_hash": "deadbeef",
                    "detector_version": "2.0",
                }
                for i in range(count)
            ]
        }
    }


def test_compaction_caps_per_bucket_and_keeps_most_recent() -> None:
    candidates = {
        "15m": {
            "fvgs": [
                {"object_id": f"fvg_{i}", "confirmed_at": f"2026-01-{i+1:02d}T00:00:00Z", "price_low": i}
                for i in range(1, 101)  # 100 candidates
            ]
        }
    }
    compacted, summary = compact_candidate_objects(candidates, per_bucket_limit=80)
    kept = compacted["15m"]["fvgs"]
    assert len(kept) == 80
    # Most recent by confirmed_at first -> descending lexicographic order, so
    # the highest day of the month comes first. Sanity-check ordering directly.
    confirmed = [item["confirmed_at"] for item in kept]
    assert confirmed == sorted(confirmed, reverse=True)
    assert summary["totals"]["candidates_before"] == 100
    assert summary["totals"]["candidates_after"] == 80
    assert summary["per_bucket"][0]["dropped"] == 20


def test_compaction_drops_bloat_fields_and_keeps_essential() -> None:
    candidates = _fat_candidates(5, confirmed_at="2026-01-01T00:00:00Z")
    compacted, _ = compact_candidate_objects(candidates)
    one = compacted["15m"]["swings"][0]
    assert set(one.keys()) == {
        "object_id", "direction", "scale", "confirmation_status", "price",
        "confirmed_at", "pivot_time",
    }
    # bloat fields removed
    assert "events" not in one
    assert "evidence" not in one
    assert "source_candle_ids" not in one
    assert "configuration_hash" not in one


def test_compaction_summary_is_transparent_not_silent() -> None:
    candidates = _fat_candidates(150, confirmed_at="2026-01-01T00:00:00Z")
    _, summary = compact_candidate_objects(candidates)
    assert summary["schema"] == "candidate_compaction_summary_v1"
    assert summary["totals"]["candidates_before"] == 150
    assert summary["totals"]["candidates_after"] == 80
    assert summary["per_bucket"][0]["timeframe"] == "15m"
    assert summary["per_bucket"][0]["bucket"] == "swings"
    assert summary["per_bucket"][0]["dropped"] == 70


def test_build_role_prompt_compacts_candidate_objects_and_records_summary() -> None:
    payload = {
        "case_id": "smoke",
        "symbol": "BTCUSDT",
        "decision_time": "2026-07-09T19:00:00Z",
        "candidate_objects": _fat_candidates(200, confirmed_at="2026-07-09T19:00:00Z"),
    }
    packet = build_role_prompt("annotation_planner", payload)
    assert "compaction_summaries" in packet
    assert packet["compaction_summaries"][0]["totals"]["candidates_before"] == 200
    assert packet["compaction_summaries"][0]["totals"]["candidates_after"] == 80
    # The prompt itself must be far smaller than the un-compacted ~9 MB shape.
    assert len(packet["prompt"]) < 200_000  # well under any model context limit
    # No bloat field should survive into the prompt text.
    assert "source_candle_ids" not in packet["prompt"]
    assert "configuration_hash" not in packet["prompt"]


def test_small_case_is_not_truncated_by_compaction() -> None:
    candidates = _fat_candidates(10, confirmed_at="2026-01-01T00:00:00Z")
    compacted, summary = compact_candidate_objects(candidates)
    assert len(compacted["15m"]["swings"]) == 10
    assert summary["totals"]["candidates_after"] == 10
    assert summary["per_bucket"][0]["dropped"] == 0


def test_compaction_is_deterministic_for_hashing() -> None:
    candidates = {
        "15m": {"swings": [
            {"object_id": "s1", "confirmed_at": "2026-01-02T00:00:00Z"},
            {"object_id": "s2", "confirmed_at": "2026-01-01T00:00:00Z"},
            {"object_id": "s3", "confirmed_at": "2026-01-03T00:00:00Z"},
        ]}
    }
    a, _ = compact_candidate_objects(candidates)
    b, _ = compact_candidate_objects(candidates)
    # Recency ordering is deterministic (most recent first), so identical input
    # produces identical compacted output -> stable prompt hash.
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["15m"]["swings"][0]["object_id"] == "s3"  # most recent