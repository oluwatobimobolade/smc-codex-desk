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

ZONE_KINDS = {"htf_zone", "order_block", "fvg"}
LINE_KINDS = {"structure", "liquidity"}
FORBIDDEN_WATCH_KINDS = {
    "entry",
    "stop",
    "target",
    "trade_plan",
    "long_position",
    "short_position",
}

PALETTE = {
    "ink": "#111827",
    "muted_ink": "#6B7280",
    "order_block": "#9CA3AF",
    "fvg": "#F4C2C2",
    "htf_zone": "#BFE8F2",
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
    if kinds["structure"] > MAX_STRUCTURE_RAYS:
        raise ValueError(f"markup may contain at most {MAX_STRUCTURE_RAYS} structure rays")
    if kinds["conditional_path"] > 1:
        raise ValueError("markup may contain at most one conditional path")
    if watch_only and FORBIDDEN_WATCH_KINDS.intersection(kinds):
        forbidden = sorted(FORBIDDEN_WATCH_KINDS.intersection(kinds))
        raise ValueError(f"watch-only markup cannot contain executable objects: {forbidden}")

    drawings = [_compile_mark(mark) for mark in mark_list]
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
            "giant_directional_arrows": False,
            "trade_box_authorized": not watch_only,
        },
    }


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
            "shape": "horizontal_ray",
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
        return {
            "shape": "path",
            "points": points,
            "text": label,
            "overrides": {
                "lineColor": PALETTE["muted_ink"],
                "lineStyle": 2,
                "lineWidth": 1,
            },
            "options": _native_options(),
            "semantic_kind": kind,
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
    "MAX_DRAWINGS",
    "MAX_PATH_POINTS",
    "MAX_STRUCTURE_RAYS",
    "MAX_ZONES",
    "PALETTE",
    "PROFILE_NAME",
    "compile_hcn_native_markup",
]
