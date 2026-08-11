from __future__ import annotations

from copy import deepcopy

from smc_desk.brain.annotation_context_authority import (
    build_annotation_context_authority,
    validate_context_exception_requests,
)
from smc_desk.rendering.native_mtf_story_pack import build_native_mtf_storyboards
from smc_desk.brain.smc_evidence_pack_builder import _expand_annotation_context_windows


def _candles(timeframe: str, count: int = 80) -> list[dict]:
    import pandas as pd

    frequency = {"4h": "4h", "1h": "1h"}[timeframe]
    stamps = pd.date_range("2026-07-20T00:00:00Z", periods=count, freq=frequency)
    return [
        {
            "timestamp": stamp.isoformat().replace("+00:00", "Z"),
            "open": 55.0,
            "high": 61.0,
            "low": 54.0,
            "close": 56.0,
            "volume": 1000.0,
        }
        for stamp in stamps
    ]


def _break(object_id: str, timeframe: str, direction: str, pivot: str, confirmed: str, *, scope: str = "external") -> dict:
    return {
        "object_id": object_id,
        "object_type": "structure_break",
        "timeframe": timeframe,
        "direction": direction,
        "break_type": "CHOCH" if "CHOCH" in object_id else "BOS",
        "structure_scope": scope,
        "pivot_time": pivot,
        "candidate_at": confirmed,
        "confirmed_at": confirmed,
        "confirmation_status": "confirmed",
        "activity_status": "inactive",
        "mitigation_status": "untouched",
        "evidence": {
            "broken_price": 56.45 if direction == "bearish" else 58.0,
            "structure_scope": scope,
            "is_unconfirmed_probe": False,
        },
    }


def _ob(
    object_id: str,
    timeframe: str,
    linked_break_id: str,
    pivot: str,
    confirmed: str,
    low: float,
    high: float,
    *,
    causal: bool = True,
) -> dict:
    return {
        "object_id": object_id,
        "object_type": "order_block",
        "timeframe": timeframe,
        "direction": "bearish",
        "pivot_time": pivot,
        "candidate_at": confirmed,
        "confirmed_at": confirmed,
        "confirmation_status": "confirmed",
        "activity_status": "active",
        "mitigation_status": "untouched",
        "terminal_reason": "none",
        "price_low": low,
        "price_high": high,
        "evidence_strength": 0.85 if causal else 0.48,
        "evidence": {
            "poi_grade": causal,
            "caused_structure_break": causal,
            "admission_status": (
                "departure_produced_displacement_into_accepted_break"
                if causal else "not_nearest_traced_departure_origin"
            ),
            "body_ratio": 0.7 if causal else 0.3,
            "structure_break_id": linked_break_id,
        },
        "metadata": {
            "linked_break_id": linked_break_id,
            "causal_link_method": (
                "explicit_break_departure_trace"
                if causal else "geometric_opposing_cluster_in_break_lookback"
            ),
            "candidate_authority": (
                "causal_candidate_not_final_poi"
                if causal else "geometric_visibility_only_no_promotion"
            ),
            "causal_origin_admission": {
                "admitted": causal,
                "reason": (
                    "departure_produced_displacement_into_accepted_break"
                    if causal else "not_nearest_traced_departure_origin"
                ),
                "score": 0.8 if causal else 0.0,
            },
        },
    }


def _pack() -> dict:
    four_hour = _candles("4h")
    one_hour = _candles("1h", 320)
    old_break = _break(
        "BOS_bearish_context",
        "4h",
        "bearish",
        four_hour[18]["timestamp"],
        four_hour[24]["timestamp"],
    )
    current_break = _break(
        "CHOCH_bullish_current",
        "4h",
        "bullish",
        four_hour[45]["timestamp"],
        four_hour[50]["timestamp"],
    )
    refined_break = _break(
        "CHOCH_internal_bearish_refinement",
        "1h",
        "bearish",
        one_hour[80]["timestamp"],
        one_hour[86]["timestamp"],
        scope="internal",
    )
    parent_ob = _ob(
        "ob_bearish_parent",
        "4h",
        old_break["object_id"],
        four_hour[20]["timestamp"],
        four_hour[24]["timestamp"],
        58.468,
        60.471,
    )
    fvg = {
        "object_id": "fvg_bearish_context",
        "object_type": "fvg",
        "timeframe": "4h",
        "direction": "bearish",
        "pivot_time": four_hour[22]["timestamp"],
        "candidate_at": four_hour[23]["timestamp"],
        "confirmed_at": four_hour[23]["timestamp"],
        "confirmation_status": "confirmed",
        "activity_status": "active",
        "mitigation_status": "partial",
        "terminal_reason": "none",
        "price_low": 57.924,
        "price_high": 59.716,
        "evidence": {
            "poi_grade": True,
            "location_context": "causal_impulse_overlap",
            "origin_break_id": old_break["object_id"],
        },
        "metadata": {
            "linked_break_id": old_break["object_id"],
            "causal_link_method": "break_source_candle_overlap",
        },
    }
    refined = _ob(
        "ob_bearish_refined",
        "1h",
        refined_break["object_id"],
        one_hour[82]["timestamp"],
        one_hour[86]["timestamp"],
        59.963,
        60.394,
    )
    broad = _ob(
        "ob_bearish_broad_geometric",
        "1h",
        refined_break["object_id"],
        one_hour[81]["timestamp"],
        one_hour[86]["timestamp"],
        59.716,
        60.311,
        causal=False,
    )
    return {
        "ohlcv_windows": {"4h": four_hour, "1h": one_hour},
        "detector_candidates": {
            "4h": {
                "structure_breaks": [old_break, current_break],
                "order_blocks": [parent_ob],
                "fvgs": [fvg],
            },
            "1h": {
                "structure_breaks": [refined_break],
                "order_blocks": [broad, refined],
                "fvgs": [],
            },
        },
        "formal_structure_graph": {"active_range": {}},
        "formal_causal_episode_graph": {
            "schema": "formal_causal_episode_graph_v2",
            "timeframes": {
                "4h": {
                    "episodes": [
                        {
                            "structure_event_id": old_break["object_id"],
                            "event_type": "EXTERNAL_BOS_BEARISH",
                            "scope": "external",
                            "direction": "bearish",
                            "confirmation_time": old_break["confirmed_at"],
                        },
                        {
                            "structure_event_id": current_break["object_id"],
                            "event_type": "EXTERNAL_MSS_CONFIRMED_BULLISH",
                            "scope": "external",
                            "direction": "bullish",
                            "confirmation_time": current_break["confirmed_at"],
                        },
                    ],
                    "latest_external_episode": {
                        "structure_event_id": current_break["object_id"],
                        "event_type": "EXTERNAL_MSS_CONFIRMED_BULLISH",
                        "scope": "external",
                        "direction": "bullish",
                        "confirmation_time": current_break["confirmed_at"],
                    },
                    "latest_internal_episode": None,
                },
                "1h": {
                    "episodes": [
                        {
                            "structure_event_id": refined_break["object_id"],
                            "event_type": "INTERNAL_CHOCH_BEARISH",
                            "scope": "internal",
                            "direction": "bearish",
                            "confirmation_time": refined_break["confirmed_at"],
                        }
                    ],
                    "latest_external_episode": None,
                    "latest_internal_episode": {
                        "structure_event_id": refined_break["object_id"],
                        "event_type": "INTERNAL_CHOCH_BEARISH",
                        "scope": "internal",
                        "direction": "bearish",
                        "confirmation_time": refined_break["confirmed_at"],
                    },
                },
            },
        },
        "causal_poi_authority": {"scenarios": {}},
        "active_range_authority": {},
    }


def test_historical_causal_supply_is_retained_as_context_without_entry_authority() -> None:
    pack = _pack()
    authority = build_annotation_context_authority(pack)

    selected = authority["selected_evidence_ids"]
    assert selected["4h"] == [
        "BOS_bearish_context",
        "ob_bearish_parent",
        "fvg_bearish_context",
    ]
    assert selected["1h"] == [
        "ob_bearish_refined",
        "CHOCH_internal_bearish_refinement",
    ]
    assert all(item["active_entry_authority"] is False for item in authority["requirements"])
    assert authority["omission_ledger"] == [
        {
            "object_id": "ob_bearish_broad_geometric",
            "timeframe": "1h",
            "parent_cluster_id": "context_cluster:4h:BOS_bearish_context",
            "status": "OMITTED_WITH_REASON",
            "reason_code": "geometric_visibility_only_not_causal_origin",
            "reason": "A narrower admitted departure origin owns the break; this older geometric base remains in the audit ledger only.",
            "selected_causal_refinement_id": "ob_bearish_refined",
            "active_entry_authority": False,
        }
    ]


def test_native_storyboard_cannot_silently_drop_required_context() -> None:
    pack = _pack()
    pack["annotation_context_authority"] = build_annotation_context_authority(pack)

    result = build_native_mtf_storyboards(pack)
    assert result["validation"]["status"] == "PASS"
    rendered = {
        value
        for storyboard in result["storyboards"].values()
        for obj in storyboard["objects"]
        for value in obj["evidence_object_ids"]
    }
    required = {
        item["object_id"] for item in pack["annotation_context_authority"]["requirements"]
    }
    assert required <= rendered
    assert "ob_bearish_broad_geometric" not in rendered
    assert all(
        obj.get("active_entry_authority") is False
        for storyboard in result["storyboards"].values()
        for obj in storyboard["objects"]
        if obj.get("context_requirement_id")
    )
    assert all(
        obj["object_type"] != "trade_box"
        for storyboard in result["storyboards"].values()
        for obj in storyboard["objects"]
    )
    parent = next(
        obj for obj in result["storyboards"]["4h"]["objects"]
        if "ob_bearish_parent" in obj.get("evidence_object_ids", [])
    )
    assert parent["end_time"] == pack["ohlcv_windows"]["4h"][-1]["timestamp"]
    assert parent["end_index"] == len(pack["ohlcv_windows"]["4h"]) - 1
    assert parent["evidence_geometry"]["end_time"] != parent["display_geometry"]["end_time"]
    assert parent["display_geometry"]["clipping_rule"] == "context_zone_to_latest_visible_bar"
    assert parent["active_entry_authority"] is False


def test_ai_context_exception_is_prequalified_and_visibility_only() -> None:
    authority = build_annotation_context_authority(_pack())
    requirement = next(
        item for item in authority["requirements"]
        if item["object_id"] == "ob_bearish_parent"
    )
    request = {
        "request_id": "keep-parent-supply",
        "requirement_id": requirement["requirement_id"],
        "evidence_object_ids": ["ob_bearish_parent"],
        "requested_display_role": "context_only",
        "rationale": "The OB owns the accepted historical bearish break and remains unspent.",
        "acknowledges_no_entry_authority": True,
        "acknowledges_no_bias_override": True,
    }

    passed = validate_context_exception_requests([request], authority)
    assert passed["status"] == "PASS"
    assert passed["accepted_requests"][0]["active_entry_authority"] is False

    promoted = deepcopy(request)
    promoted["requested_display_role"] = "active_setup"
    failed = validate_context_exception_requests([promoted], authority)
    assert failed["status"] == "REVIEW_REQUIRED"
    assert failed["accepted_requests"] == []
    assert failed["issues"][0]["code"] == "context_exception_role_forbidden"


def test_sealed_window_expands_to_include_required_refinement_origin() -> None:
    import pandas as pd

    candles = _candles("1h", 320)
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    required_time = candles[82]["timestamp"]
    pack = {
        "ohlcv_windows": {"1h": candles[-120:]},
        "annotation_context_authority": {
            "requirements": [
                {
                    "object_id": "ob_bearish_refined",
                    "timeframe": "1h",
                    "required_render": True,
                    "required_start_time": required_time,
                }
            ],
            "window_requirements": {
                "earliest_required_time_by_timeframe": {"1h": required_time},
                "maximum_context_rows_per_timeframe": 720,
                "pre_anchor_padding_bars": 8,
            },
        },
    }

    _expand_annotation_context_windows(
        pack=pack,
        normalized_dfs={"1h": df},
        base_max_rows=120,
    )

    expanded = pack["ohlcv_windows"]["1h"]
    assert len(expanded) == 246
    assert expanded[0]["timestamp"] == str(df.iloc[74]["timestamp"])
    requirement = pack["annotation_context_authority"]["requirements"][0]
    assert requirement["window_status"] == "VISIBLE_IN_EXPANDED_WINDOW"
