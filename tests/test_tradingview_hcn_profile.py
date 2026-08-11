"""Contracts for the restrained HCN-inspired TradingView markup profile."""
from __future__ import annotations

import pytest

from smc_desk.rendering.tradingview_hcn_profile import (
    MAX_DRAWINGS,
    PALETTE,
    compile_hcn_native_markup,
)


def _zone(kind="order_block", index=0):
    return {
        "kind": kind,
        "time_start": 1_750_000_000 + index * 3600,
        "time_end": 1_750_086_400 + index * 3600,
        "price_low": 100.0 + index,
        "price_high": 101.0 + index,
        "label": f"4H {kind.replace('_', ' ').upper()}",
    }


def test_compiles_muted_native_zone_ray_and_path():
    plan = compile_hcn_native_markup([
        _zone("order_block"),
        {
            "kind": "structure",
            "time": 1_750_000_000,
            "price": 104.2,
            "label": "4H BOS",
        },
        {
            "kind": "conditional_path",
            "label": "IF 1H confirms",
            "points": [
                {"time": 1_750_000_000, "price": 103.0},
                {"time": 1_750_003_600, "price": 101.0},
                {"time": 1_750_007_200, "price": 104.0},
            ],
        },
    ])
    assert plan["watch_only"] is True
    # The installed MCP forwards native rays and multipoint paths.
    assert [item["shape"] for item in plan["drawings"]] == [
        "rectangle", "horizontal_ray", "path"
    ]
    zone = plan["drawings"][0]
    assert zone["overrides"]["backgroundColor"] == PALETTE["order_block"]
    assert zone["overrides"]["transparency"] >= 80
    assert zone["overrides"]["linewidth"] == 1
    assert plan["drawings"][1]["overrides"]["linewidth"] == 1
    path = plan["drawings"][2]
    assert path["native_support"] is True
    assert len(path["points"]) == 3
    assert path["overrides"]["lineWidth"] == 1


def test_watch_chart_rejects_entry_stop_target_and_position_tools():
    for kind in ("entry", "stop", "target", "long_position", "short_position"):
        with pytest.raises(ValueError, match="watch-only"):
            compile_hcn_native_markup([{"kind": kind, "label": kind}])


def test_clutter_budget_and_zone_caps_fail_closed():
    with pytest.raises(ValueError, match="clutter budget"):
        compile_hcn_native_markup([
            {"kind": "note", "time": 1_750_000_000 + index, "price": 100 + index,
             "label": f"note {index}"}
            for index in range(MAX_DRAWINGS + 1)
        ])
    with pytest.raises(ValueError, match="at most 3 active zones"):
        compile_hcn_native_markup([_zone(index=index) for index in range(4)])


def test_projection_is_unique_short_and_forward_only():
    path = {
        "kind": "conditional_path",
        "label": "IF confirmed",
        "points": [
            {"time": 1_750_000_000, "price": 100},
            {"time": 1_750_003_600, "price": 101},
        ],
    }
    with pytest.raises(ValueError, match="at most one"):
        compile_hcn_native_markup([path, path])
    backwards = {**path, "points": list(reversed(path["points"]))}
    with pytest.raises(ValueError, match="forward in time"):
        compile_hcn_native_markup([backwards])


def test_labels_stay_small_and_geometry_must_be_real():
    with pytest.raises(ValueError, match="label exceeds"):
        compile_hcn_native_markup([
            {"kind": "note", "time": 1_750_000_000, "price": 100,
             "label": "x" * 33}
        ])
    invalid = _zone()
    invalid["price_high"] = invalid["price_low"]
    with pytest.raises(ValueError, match="price_high must be above"):
        compile_hcn_native_markup([invalid])
