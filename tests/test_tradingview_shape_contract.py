"""Tests binding the compiler to the MCP server's real shape vocabulary.

The server (tradesdontlie/tradingview-mcp) exposes one drawing tool,
``draw_shape``, accepting exactly four shapes: horizontal_line, trend_line,
rectangle and text.

This file exists because an earlier version of the compiler emitted
``horizontal_ray``, ``path``, ``long_position`` and ``short_position`` -- none
of which the server implements. Those payloads validated locally and would
have drawn nothing: the run reports success and the chart stays empty, which
is worse than an error.
"""
from __future__ import annotations

import pytest

from smc_desk.rendering.tradingview_hcn_profile import (
    NATIVE_TOOL_MAP,
    SUPPORTED_SHAPES,
    compile_hcn_native_markup,
    flatten_draw_calls,
)


def _zone(kind="order_block"):
    return {"kind": kind, "label": "4H OB", "time_start": 1_750_000_000,
            "time_end": 1_750_100_000, "price_low": 100.0, "price_high": 110.0}


def _position(kind="long_position"):
    return {"kind": kind, "label": "Long", "time": 1_750_000_000,
            "time_end": 1_750_100_000, "entry_price": 105.0,
            "stop_price": 100.0, "target_prices": [120.0]}


# -- the vocabulary is exactly what the server implements ----------------------


def test_supported_shapes_match_the_server():
    assert SUPPORTED_SHAPES == {"horizontal_line", "trend_line", "rectangle", "text"}


def test_shapes_the_server_lacks_are_never_emitted():
    """The exact bug this file exists for."""
    plan = compile_hcn_native_markup([
        _zone(),
        {"kind": "liquidity", "label": "EQL", "time": 1_750_000_000, "price": 99.0},
        {"kind": "structure_segment", "label": "4H BOS", "scope": "external",
         "time_start": 1_750_000_000, "time_end": 1_750_050_000, "price": 108.0},
    ])
    for call in flatten_draw_calls(plan):
        assert call["shape"] in SUPPORTED_SHAPES, f"server cannot draw {call['shape']!r}"


def test_liquidity_is_a_horizontal_line_not_a_ray():
    plan = compile_hcn_native_markup([
        {"kind": "liquidity", "label": "EQL", "time": 1_750_000_000, "price": 99.0},
    ])
    assert plan["drawings"][0]["shape"] == "horizontal_line"


def test_structure_segment_is_a_trend_line():
    """A BOS ran from the broken swing to the breaking candle."""
    plan = compile_hcn_native_markup([
        {"kind": "structure_segment", "label": "4H BOS", "scope": "external",
         "time_start": 1_750_000_000, "time_end": 1_750_050_000, "price": 108.0},
    ])
    assert plan["drawings"][0]["shape"] == "trend_line"


# -- decomposition of concepts with no native shape ---------------------------


def test_position_decomposes_into_risk_and_reward_boxes():
    plan = compile_hcn_native_markup([_position()], watch_only=False)
    drawing = plan["drawings"][0]
    assert drawing["native_support"] is False
    roles = [part["role"] for part in drawing["parts"]]
    assert roles == ["risk", "reward", "label"]
    assert {part["shape"] for part in drawing["parts"]} <= SUPPORTED_SHAPES


def test_position_carries_its_own_risk_reward_because_nothing_else_computes_it():
    plan = compile_hcn_native_markup([_position()], watch_only=False)
    # entry 105, stop 100, target 120 -> risk 5, reward 15
    assert plan["drawings"][0]["risk_reward"] == pytest.approx(3.0)


def test_long_position_rejects_an_impossible_geometry():
    bad = {**_position(), "stop_price": 130.0}
    with pytest.raises(ValueError, match="stop < entry < target"):
        compile_hcn_native_markup([bad], watch_only=False)


def test_short_position_geometry_is_mirrored():
    good = {**_position("short_position"), "entry_price": 105.0,
            "stop_price": 110.0, "target_prices": [90.0]}
    plan = compile_hcn_native_markup([good], watch_only=False)
    assert plan["drawings"][0]["semantic_kind"] == "short_position"


def test_conditional_path_decomposes_into_connected_segments():
    plan = compile_hcn_native_markup([{
        "kind": "conditional_path", "label": "Draw to 4H high",
        "points": [
            {"time": 1_750_000_000, "price": 100.0},
            {"time": 1_750_050_000, "price": 104.0},
            {"time": 1_750_100_000, "price": 110.0},
        ],
    }])
    parts = plan["drawings"][0]["parts"]
    assert len(parts) == 2, "three points make two segments"
    assert all(part["shape"] == "trend_line" for part in parts)
    # Segments must join end-to-end or the path reads as disconnected marks.
    assert parts[0]["point2"] == parts[1]["point"]


# -- flattening to individual draw_shape calls --------------------------------


def test_flatten_expands_composites_into_individual_calls():
    plan = compile_hcn_native_markup([_zone(), _position()], watch_only=False)
    calls = flatten_draw_calls(plan)
    # one rectangle for the zone, plus three parts for the position
    assert len(calls) == 4
    assert all("role" not in call for call in calls)
    assert all(call["semantic_kind"] for call in calls)


def test_flatten_preserves_the_semantic_kind_of_each_part():
    plan = compile_hcn_native_markup([_position()], watch_only=False)
    calls = flatten_draw_calls(plan)
    assert {call["semantic_kind"] for call in calls} == {"long_position"}


# -- the map is honest about what is native -----------------------------------


def test_native_tool_map_marks_non_native_concepts():
    assert NATIVE_TOOL_MAP["order_block"] == "rectangle"
    assert "no native position tool" in NATIVE_TOOL_MAP["long_position"]
    assert "segmented" in NATIVE_TOOL_MAP["conditional_path"]


def test_watch_only_still_refuses_positions():
    """Decomposing a position must not become a way around the authority gate."""
    with pytest.raises(ValueError, match="watch-only"):
        compile_hcn_native_markup([_position()])
