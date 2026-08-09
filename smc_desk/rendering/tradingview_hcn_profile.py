"""Compile restrained SMC marks into native TradingView drawing requests.

The profile borrows the visual grammar observed in HCNFXACADEMY's public
lessons: muted zones, thin structure rays, short labels, and at most one
conditional projection. It does not borrow a market conclusion and it never
creates trade authority.

Input geometry must already be evidence-bound. This module only validates the
story and selects native TradingView shapes/styles; it does not discover or
move price levels.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Any, Iterable, Mapping


PROFILE_NAME = "hcn_clean_smc_v1"
MAX_DRAWINGS = 8
MAX_ZONES = 3
MAX_STRUCTURE_RAYS = 3
MAX_PATH_POINTS = 6
MAX_LABEL_CHARS = 32

ZONE_KINDS = {"htf_zone", "order_block", "fvg", "dealing_range"}
LINE_KINDS = {"structure", "liquidity"}
# Structure that travelled between two points in time is a trend line, not a
# ray: a BOS runs from the swing it broke to the candle that broke it.
SEGMENT_KINDS = {"structure_segment"}
POSITION_KINDS = {"long_position", "short_position"}
FORBIDDEN_WATCH_KINDS = {
    "entry",
    "stop",
    "target",
    "trade_plan",
    "long_position",
    "short_position",
}

# The MCP server (tradesdontlie/tradingview-mcp) exposes ONE drawing tool,
# `draw_shape`, and it accepts exactly four shapes. Everything we emit must be
# one of these; anything else is silently undrawable.
#
# This list is the contract, not an aspiration. An earlier version of this
# module emitted `horizontal_ray`, `path`, `long_position` and
# `short_position` -- none of which exist in the server -- so the payloads
# validated locally and would have drawn nothing.
SUPPORTED_SHAPES = {"horizontal_line", "trend_line", "rectangle", "text"}

# Native TradingView tool for each SMC concept. Using the platform's own
# drawing objects rather than approximating them means the markup stays
# editable by hand after it lands and reads as a normal chart to another
# trader.
#
# Three concepts have no native shape and are decomposed faithfully rather
# than dropped: a conditional path becomes connected trend-line segments, and
# a position becomes the two rectangles a trader would draw by hand -- risk
# from entry to stop, reward from entry to target -- plus a text label. That
# loses TradingView's own risk/reward arithmetic, which is recorded in the
# payload so a reader knows the number came from us.
NATIVE_TOOL_MAP = {
    "order_block": "rectangle",
    "fvg": "rectangle",
    "htf_zone": "rectangle",
    "dealing_range": "rectangle",
    "liquidity": "horizontal_line",
    "structure": "horizontal_line",
    "structure_segment": "trend_line",
    "conditional_path": "trend_line (segmented)",
    "note": "text",
    "long_position": "rectangle x2 + text (no native position tool)",
    "short_position": "rectangle x2 + text (no native position tool)",
}

# Server-side companions to draw_shape, recorded so a caller can clear a chart
# before re-annotating rather than stacking drawings.
COMPANION_TOOLS = ("draw_list", "draw_remove_one", "draw_clear")

PALETTE = {
    "ink": "#111827",
    "muted_ink": "#6B7280",
    "order_block": "#9CA3AF",
    "fvg": "#F4C2C2",
    "htf_zone": "#BFE8F2",
    # The dealing range is context, not a POI: it sits furthest back and
    # lightest so premium/discount location reads without competing with the
    # zones inside it.
    "dealing_range": "#D8DEE4",
}


def compile_hcn_native_markup(
    marks: Iterable[Mapping[str, Any]],
    *,
    watch_only: bool = True,
    clutter_budget: int = MAX_DRAWINGS,
) -> dict[str, Any]:
    """Return MCP-ready ``draw_shape`` payloads for a clean SMC chart."""
    mark_list = [dict(mark) for mark in marks]
    if clutter_budget < 1 or clutter_budget > MAX_DRAWINGS:
        raise ValueError(f"clutter_budget must be between 1 and {MAX_DRAWINGS}")
    if len(mark_list) > clutter_budget:
        raise ValueError(f"markup exceeds clutter budget ({len(mark_list)} > {clutter_budget})")

    kinds = Counter(str(mark.get("kind") or "") for mark in mark_list)
    if sum(kinds[kind] for kind in ZONE_KINDS) > MAX_ZONES:
        raise ValueError(f"markup may contain at most {MAX_ZONES} active zones")
    structure_marks = kinds["structure"] + sum(kinds[kind] for kind in SEGMENT_KINDS)
    if structure_marks > MAX_STRUCTURE_RAYS:
        raise ValueError(f"markup may contain at most {MAX_STRUCTURE_RAYS} structure marks")
    if sum(kinds[kind] for kind in POSITION_KINDS) > 1:
        raise ValueError("markup may contain at most one position")
    if kinds["conditional_path"] > 1:
        raise ValueError("markup may contain at most one conditional path")
    if watch_only and FORBIDDEN_WATCH_KINDS.intersection(kinds):
        forbidden = sorted(FORBIDDEN_WATCH_KINDS.intersection(kinds))
        raise ValueError(f"watch-only markup cannot contain executable objects: {forbidden}")

    drawings = [_compile_mark(mark) for mark in mark_list]
    _assert_server_can_draw(drawings)
    return {
        "schema": "tradingview_native_markup_v1",
        "profile": PROFILE_NAME,
        "authority": "visual_only_observe_only" if watch_only else "visual_only",
        "watch_only": watch_only,
        "drawing_count": len(drawings),
        "drawings": drawings,
        "visual_rules": {
            "zones_max": MAX_ZONES,
            "structure_rays_max": MAX_STRUCTURE_RAYS,
            "conditional_paths_max": 1,
            "positions_max": 0 if watch_only else 1,
            "giant_directional_arrows": False,
            "trade_box_authorized": not watch_only,
        },
        "native_tool_map": dict(NATIVE_TOOL_MAP),
    }


def _assert_server_can_draw(drawings: list[Mapping[str, Any]]) -> None:
    """Every emitted shape must exist in the MCP server's vocabulary.

    A payload naming a shape the server does not implement validates locally
    and then draws nothing, which is the worst possible failure: the run looks
    successful and the chart is empty. This module previously emitted
    horizontal_ray, path, long_position and short_position, none of which
    exist.
    """
    for drawing in drawings:
        shape = str(drawing.get("shape") or "")
        if shape == "composite":
            for part in drawing.get("parts") or []:
                part_shape = str(part.get("shape") or "")
                if part_shape not in SUPPORTED_SHAPES:
                    raise ValueError(
                        f"composite part uses unsupported shape {part_shape!r}; "
                        f"server supports {sorted(SUPPORTED_SHAPES)}"
                    )
            continue
        if shape not in SUPPORTED_SHAPES:
            raise ValueError(
                f"unsupported shape {shape!r}; server supports {sorted(SUPPORTED_SHAPES)}"
            )


def flatten_draw_calls(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand a compiled plan into individual ``draw_shape`` calls.

    Composites become their constituent parts, so a caller can iterate the
    result and issue one MCP call per entry without knowing which concepts
    happen to have native shapes.
    """
    calls: list[dict[str, Any]] = []
    for drawing in plan.get("drawings") or []:
        if str(drawing.get("shape")) == "composite":
            for part in drawing.get("parts") or []:
                call = {k: v for k, v in part.items() if k != "role"}
                call["semantic_kind"] = drawing.get("semantic_kind")
                calls.append(call)
        else:
            calls.append(dict(drawing))
    return calls


def _compile_mark(mark: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(mark.get("kind") or "")
    label = _label(mark.get("label"), kind)
    if kind in ZONE_KINDS:
        start = _time(mark.get("time_start"), "time_start")
        end = _time(mark.get("time_end"), "time_end")
        low = _price(mark.get("price_low"), "price_low")
        high = _price(mark.get("price_high"), "price_high")
        if end <= start:
            raise ValueError(f"{kind} time_end must be after time_start")
        if high <= low:
            raise ValueError(f"{kind} price_high must be above price_low")
        color = PALETTE[kind]
        return {
            "shape": "rectangle",
            "point": {"time": start, "price": high},
            "point2": {"time": end, "price": low},
            "text": label,
            "overrides": {
                "backgroundColor": color,
                "color": color,
                "fillBackground": True,
                "fontSize": 10,
                "horzLabelsAlign": "left",
                "linewidth": 1,
                "textColor": PALETTE["ink"],
                "transparency": 82,
                "vertLabelsAlign": "top",
            },
            "options": _native_options(z_order="bottom"),
            "semantic_kind": kind,
        }

    if kind in LINE_KINDS:
        time = _time(mark.get("time"), "time")
        price = _price(mark.get("price"), "price")
        color = PALETTE["ink"] if kind == "structure" else PALETTE["muted_ink"]
        return {
            # `horizontal_line`, not `horizontal_ray`: the server has no ray.
            "shape": "horizontal_line",
            "point": {"time": time, "price": price},
            "text": label,
            "overrides": {
                "bold": False,
                "fontsize": 10,
                "horzLabelsAlign": "left",
                "linecolor": color,
                "linestyle": 0 if kind == "structure" else 2,
                "linewidth": 1,
                "showPrice": True,
                "textcolor": color,
                "vertLabelsAlign": "top",
            },
            "options": _native_options(),
            "semantic_kind": kind,
        }

    if kind in SEGMENT_KINDS:
        # A BOS or CHoCH travelled from the swing it broke to the candle that
        # broke it. TradingView's trend line is the tool for that; a ray would
        # imply the level extends forever, which is a different claim.
        start_time = _time(mark.get("time_start"), "time_start")
        end_time = _time(mark.get("time_end"), "time_end")
        price = _price(mark.get("price"), "price")
        if end_time <= start_time:
            raise ValueError("structure_segment time_end must be after time_start")
        scope = str(mark.get("scope") or "external").lower()
        internal = scope == "internal"
        return {
            "shape": "trend_line",
            "point": {"time": start_time, "price": price},
            "point2": {"time": end_time, "price": price},
            "text": label,
            "overrides": {
                "bold": False,
                "fontsize": 9 if internal else 11,
                "linecolor": PALETTE["muted_ink"] if internal else PALETTE["ink"],
                # Internal structure dashed, swing structure solid: the single
                # most important visual distinction on an SMC chart.
                "linestyle": 2 if internal else 0,
                "linewidth": 1 if internal else 2,
                "showLabel": True,
                "textcolor": PALETTE["muted_ink"] if internal else PALETTE["ink"],
            },
            "options": _native_options(),
            "semantic_kind": kind,
            "structure_scope": scope,
        }

    if kind in POSITION_KINDS:
        # The server has no position tool, so a setup is decomposed into what
        # a trader would otherwise draw by hand: a risk box from entry to
        # stop, a reward box from entry to target, and one label. The
        # risk/reward figure is computed here and carried in the payload,
        # because unlike TradingView's own tool nothing downstream will
        # recompute it.
        entry = _price(mark.get("entry_price"), "entry_price")
        stop = _price(mark.get("stop_price"), "stop_price")
        targets = mark.get("target_prices")
        if not isinstance(targets, list) or not targets:
            raise ValueError(f"{kind} requires at least one target price")
        target = _price(targets[0], "target_prices[0]")
        if kind == "long_position" and not (stop < entry < target):
            raise ValueError("long_position requires stop < entry < target")
        if kind == "short_position" and not (target < entry < stop):
            raise ValueError("short_position requires target < entry < stop")
        start = _time(mark.get("time"), "time")
        end = _time(mark.get("time_end") or (start + 3600), "time_end")
        if end <= start:
            raise ValueError(f"{kind} time_end must be after time")
        risk = abs(entry - stop)
        reward = abs(target - entry)
        return {
            "shape": "composite",
            "text": label,
            "semantic_kind": kind,
            "native_support": False,
            "decomposition_note": (
                "TradingView MCP exposes no position tool; drawn as risk and "
                "reward rectangles plus a label."
            ),
            "risk_reward": round(reward / risk, 3) if risk else None,
            "parts": [
                {
                    "shape": "rectangle",
                    "point": {"time": start, "price": entry},
                    "point2": {"time": end, "price": stop},
                    "text": "",
                    "overrides": {
                        "backgroundColor": PALETTE["fvg"], "color": PALETTE["fvg"],
                        "fillBackground": True, "linewidth": 1, "transparency": 80,
                    },
                    "options": _native_options(z_order="bottom"),
                    "role": "risk",
                },
                {
                    "shape": "rectangle",
                    "point": {"time": start, "price": entry},
                    "point2": {"time": end, "price": target},
                    "text": "",
                    "overrides": {
                        "backgroundColor": PALETTE["htf_zone"], "color": PALETTE["htf_zone"],
                        "fillBackground": True, "linewidth": 1, "transparency": 80,
                    },
                    "options": _native_options(z_order="bottom"),
                    "role": "reward",
                },
                {
                    "shape": "text",
                    "point": {"time": start, "price": entry},
                    "text": label,
                    "overrides": {"bold": False, "color": PALETTE["ink"], "fontsize": 10},
                    "options": _native_options(),
                    "role": "label",
                },
            ],
        }

    if kind == "conditional_path":
        raw_points = mark.get("points")
        if not isinstance(raw_points, list) or not 2 <= len(raw_points) <= MAX_PATH_POINTS:
            raise ValueError(f"conditional_path requires 2-{MAX_PATH_POINTS} points")
        points = [
            {
                "time": _time(point.get("time"), f"points[{index}].time"),
                "price": _price(point.get("price"), f"points[{index}].price"),
            }
            for index, point in enumerate(raw_points)
        ]
        if any(right["time"] <= left["time"] for left, right in zip(points, points[1:])):
            raise ValueError("conditional_path points must move forward in time")
        # No path tool on the server: a projected route is drawn as connected
        # dashed trend-line segments, which is what it looks like anyway.
        return {
            "shape": "composite",
            "text": label,
            "semantic_kind": kind,
            "native_support": False,
            "decomposition_note": (
                "TradingView MCP exposes no path tool; drawn as connected "
                "dashed trend-line segments."
            ),
            "parts": [
                {
                    "shape": "trend_line",
                    "point": left,
                    "point2": right,
                    "text": label if index == 0 else "",
                    "overrides": {
                        "linecolor": PALETTE["muted_ink"],
                        "linestyle": 2,
                        "linewidth": 1,
                    },
                    "options": _native_options(),
                    "role": f"segment_{index + 1}",
                }
                for index, (left, right) in enumerate(zip(points, points[1:]))
            ],
        }

    if kind == "note":
        return {
            "shape": "text",
            "point": {
                "time": _time(mark.get("time"), "time"),
                "price": _price(mark.get("price"), "price"),
            },
            "text": label,
            "overrides": {
                "bold": False,
                "color": PALETTE["muted_ink"],
                "fontsize": 10,
            },
            "options": _native_options(),
            "semantic_kind": kind,
        }

    raise ValueError(f"unsupported HCN markup kind: {kind!r}")


def _native_options(*, z_order: str = "top") -> dict[str, Any]:
    return {
        "disableSave": False,
        "disableSelection": False,
        "disableUndo": False,
        "lock": False,
        "showInObjectsTree": True,
        "zOrder": z_order,
    }


def _label(value: Any, kind: str) -> str:
    label = " ".join(str(value or "").split())
    if not label:
        raise ValueError(f"{kind or 'mark'} requires a concise label")
    if len(label) > MAX_LABEL_CHARS:
        raise ValueError(f"label exceeds {MAX_LABEL_CHARS} characters: {label!r}")
    return label


def _time(value: Any, name: str) -> int:
    number = _finite(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be a positive Unix timestamp")
    return int(number)


def _price(value: Any, name: str) -> float:
    return _finite(value, name)


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


__all__ = [
    "COMPANION_TOOLS",
    "NATIVE_TOOL_MAP",
    "SUPPORTED_SHAPES",
    "flatten_draw_calls",
    "MAX_DRAWINGS",
    "MAX_PATH_POINTS",
    "MAX_STRUCTURE_RAYS",
    "MAX_ZONES",
    "PALETTE",
    "PROFILE_NAME",
    "compile_hcn_native_markup",
]
