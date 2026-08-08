"""Official AI SMC trader annotation renderer.

Only validated AI decisions may be rendered here. Debug detector charts remain
separate and must carry a debug-only label.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyArrowPatch
from matplotlib.patches import Rectangle

from smc_desk.brain.annotation_visual_critic import apply_visual_cleanup
from smc_desk.brain.ai_smc_consistency_validator import ValidationResult
from smc_desk.brain.annotation_geometry import effective_display_geometry


DEBUG_CHART_LABEL = "DEBUG ONLY - NOT OFFICIAL TRADE THESIS"
LABEL_LIMITS = {
    "context_chart": 5,
    "watch_chart": 7,
    "review_chart": 7,
    "trade_plan_chart": 8,
}
VISIBLE_LABEL_LIMITS = {
    "context_chart": 2,
    "watch_chart": 3,
    "review_chart": 3,
    "trade_plan_chart": 5,
}
VISIBLE_LEVEL_LIMITS = {
    "context_chart": 3,
    "watch_chart": 3,
    "review_chart": 3,
    "trade_plan_chart": 6,
}


def build_smc_trader_annotation_scene(result: ValidationResult) -> dict[str, Any]:
    decision = result.official_decision
    annotation = decision["annotation_plan"]
    chart_template = annotation["chart_template"]
    if result.status != "VALIDATED":
        if chart_template != "review_chart" or annotation.get("show_trade_box"):
            raise ValueError("Review-required decisions may only render review_chart without a trade box.")
    legacy_labels = list(annotation.get("labels") or [])
    labels = list(legacy_labels)
    label_limit = LABEL_LIMITS.get(chart_template, 7)
    if len(labels) > label_limit:
        labels = labels[:label_limit]
    if chart_template != "trade_plan_chart" and annotation.get("show_trade_box"):
        raise ValueError("Only trade_plan_chart may show trade boxes.")
    if chart_template == "trade_plan_chart" and decision.get("official_state") != "TRADE_PLAN_READY":
        raise ValueError("trade_plan_chart requires TRADE_PLAN_READY.")
    legacy_levels = list(annotation.get("levels") or [])
    annotation_plan_v2 = decision.get("annotation_plan_v2") or {}
    v2_present = isinstance(annotation_plan_v2, Mapping) and annotation_plan_v2.get("schema") == "professional_smc_annotation_plan_v2"
    drawing_objects = [
        _object_with_display_geometry(raw)
        for raw in (annotation_plan_v2.get("objects") or [])
        if isinstance(raw, Mapping)
    ] if v2_present else []
    if v2_present:
        labels = []
    visible_drawing_objects = _select_visible_drawing_objects(drawing_objects, chart_template)
    levels = _drawing_objects_to_levels(visible_drawing_objects) if v2_present else legacy_levels
    visible_labels = _select_visible_labels(labels, chart_template)
    visible_levels = _select_visible_levels(levels, chart_template)
    return {
        "schema": "smc_trader_annotation_scene_v1",
        "source": "ValidatedAISMCDecision" if result.status == "VALIDATED" else "ReviewRequiredAISMCDecision",
        "validation_status": result.status,
        "symbol": decision.get("symbol"),
        "official_state": decision.get("official_state"),
        "chart_template": chart_template,
        "show_trade_box": bool(annotation.get("show_trade_box")),
        "labels": labels,
        "legacy_labels": legacy_labels,
        "levels": levels,
        "legacy_levels": legacy_levels,
        "annotation_plan_v2": annotation_plan_v2 if v2_present else None,
        "drawing_objects": drawing_objects,
        "visible_drawing_objects": visible_drawing_objects,
        "drawing_object_count": len(drawing_objects),
        "visible_drawing_object_count": len(visible_drawing_objects),
        "level_source": "annotation_plan_v2" if v2_present else "annotation_plan",
        "visible_labels": visible_labels,
        "visible_levels": visible_levels,
        "label_count": len(labels),
        "label_limit": label_limit,
        "visible_label_count": len(visible_labels),
        "hidden_label_count": max(0, len(labels) - len(visible_labels)),
        "legacy_labels_suppressed": bool(v2_present and legacy_labels),
        "visible_level_count": len(visible_levels),
        "hidden_level_count": max(0, len(levels) - len(visible_levels)),
        "display_contract": "trader_markup_sparse",
        "debug_chart_label": DEBUG_CHART_LABEL,
    }


def build_debug_annotation_scene(debug_objects: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "smc_debug_annotation_scene_v1",
        "source": "debug_detector_objects",
        "official": False,
        "banner": DEBUG_CHART_LABEL,
        "debug_objects": dict(debug_objects or {}),
    }


def render_smc_trader_annotation_chart(
    df: pd.DataFrame,
    result: ValidationResult,
    output_path: str | Path,
    *,
    timeframe: str = "15m",
) -> dict[str, Any]:
    if df.empty:
        raise ValueError("Cannot render SMC trader annotation chart from an empty dataframe.")
    decision = result.official_decision
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = _normalize_df(df)
    scene = _resolve_scene_time_geometry(build_smc_trader_annotation_scene(result), df)
    scene = apply_visual_cleanup(scene, df)
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)

    levels = _scene_levels({**scene, "levels": scene["visible_levels"]})
    path_prices = _v2_path_prices(scene.get("visible_drawing_objects") or [])
    low_inputs = [float(l.min()), *[item["low"] for item in levels], *[item["high"] for item in levels], *path_prices]
    high_inputs = [float(h.max()), *[item["low"] for item in levels], *[item["high"] for item in levels], *path_prices]
    low = min(low_inputs)
    high = max(high_inputs)
    span = max(high - low, abs(high) * 0.01, 1e-9)

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.grid(color="#e9e9e9", linewidth=0.75, alpha=0.95)
    body_floor = span * 1e-3
    for index in range(n):
        color = "#26a69a" if c[index] >= o[index] else "#ef5350"
        ax.plot([index, index], [l[index], h[index]], color="#1e1e1e", linewidth=0.7, zorder=2)
        ax.add_patch(Rectangle((index - 0.34, min(o[index], c[index])), 0.68, max(abs(c[index] - o[index]), body_floor), color=color, zorder=3, linewidth=0))

    for level in _assign_level_label_positions(levels, low=low, high=high):
        x1, x2 = _level_x_span(level, n, scene["chart_template"])
        if _is_zone_kind(level["kind"]) and level["low"] != level["high"]:
            width = max(1.0, x2 - x1)
            ax.add_patch(
                Rectangle(
                    (x1, level["low"]),
                    width,
                    level["high"] - level["low"],
                    facecolor=level["color"],
                    edgecolor=level["edge_color"],
                    alpha=level["alpha"],
                    zorder=1,
                    linewidth=1.0,
                )
            )
            _inline_label(ax, (x1 + x2) / 2, level.get("label_y", level["high"]), level["label"], level["edge_color"])
            continue
        ax.plot([x1, x2], [level["low"], level["low"]], color=level["edge_color"], linestyle=level["linestyle"], linewidth=level["linewidth"], alpha=0.92, zorder=4)
        _inline_label(ax, (x1 + x2) / 2, level.get("label_y", level["low"]), level["label"], level["edge_color"])

    v2_trade_box = _first_v2_trade_box(scene.get("visible_drawing_objects") or [])
    if scene["chart_template"] == "trade_plan_chart":
        if v2_trade_box is not None:
            _draw_v2_trade_box(ax, v2_trade_box, n)
        else:
            _draw_trade_projection(ax, scene, levels, n)
    if scene.get("visible_drawing_objects"):
        _draw_v2_path_objects(ax, scene["visible_drawing_objects"], n)
    elif scene["level_source"] != "annotation_plan_v2" and scene["chart_template"] == "watch_chart":
        # Draw path arrows for watch thesis
        direction = decision.get("direction")
        active_range = decision.get("active_range") or {}
        range_high = _float(active_range.get("high"))
        range_low = _float(active_range.get("low"))
        if range_high is not None and range_low is not None:
            mid = (range_high + range_low) / 2.0
            x1 = max(0.0, n * 0.72)
            x2 = n + 4.0
            if direction == "bullish":
                ax.add_patch(
                    FancyArrowPatch(
                        (x1, mid),
                        (x1 + (x2 - x1) * 0.4, range_low + (mid - range_low) * 0.3),
                        connectionstyle="arc3,rad=-0.15",
                        arrowstyle="-",
                        color="#777777",
                        linewidth=1.2,
                        linestyle="dashed",
                        alpha=0.45,
                        zorder=5,
                    )
                )
                ax.add_patch(
                    FancyArrowPatch(
                        (x1 + (x2 - x1) * 0.4, range_low + (mid - range_low) * 0.3),
                        (x2, range_high),
                        connectionstyle="arc3,rad=0.15",
                        arrowstyle="-",
                        color="#777777",
                        linewidth=1.2,
                        linestyle="dashed",
                        alpha=0.35,
                        zorder=6,
                    )
                )
                ax.text(
                    x2,
                    range_high,
                    "possible path only",
                    color="#777777",
                    fontsize=7,
                    ha="right",
                    va="bottom",
                    alpha=0.75,
                    zorder=7,
                )
            elif direction == "bearish":
                ax.add_patch(
                    FancyArrowPatch(
                        (x1, mid),
                        (x1 + (x2 - x1) * 0.4, range_high - (range_high - mid) * 0.3),
                        connectionstyle="arc3,rad=0.15",
                        arrowstyle="-",
                        color="#777777",
                        linewidth=1.2,
                        linestyle="dashed",
                        alpha=0.45,
                        zorder=5,
                    )
                )
                ax.add_patch(
                    FancyArrowPatch(
                        (x1 + (x2 - x1) * 0.4, range_high - (range_high - mid) * 0.3),
                        (x2, range_low),
                        connectionstyle="arc3,rad=-0.15",
                        arrowstyle="-",
                        color="#777777",
                        linewidth=1.2,
                        linestyle="dashed",
                        alpha=0.35,
                        zorder=6,
                    )
                )
                ax.text(
                    x2,
                    range_low,
                    "possible path only",
                    color="#777777",
                    fontsize=7,
                    ha="right",
                    va="top",
                    alpha=0.75,
                    zorder=7,
                )

    title = f"{decision.get('symbol')} {timeframe}"
    subtitle = str(decision.get("official_state") or "").replace("_", " ")
    ax.set_title(title, color="#111111", fontsize=12, fontweight="bold", loc="left", pad=12)
    ax.text(
        0.008,
        1.005,
        subtitle,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        color="#666666",
        fontsize=7.5,
        fontweight="normal",
    )
    labels = scene["visible_labels"]
    label_text = "\n".join(f"{idx}. {label['text']}" for idx, label in enumerate(labels, start=1))
    if label_text and scene["level_source"] != "annotation_plan_v2" and scene["chart_template"] != "watch_chart":
        ax.text(
            0.008,
            0.92,
            label_text,
            transform=ax.transAxes,
            ha="left",
            va="top",
            color="#111111",
            fontsize=8,
            linespacing=1.35,
            bbox={"facecolor": "#ffffff", "edgecolor": "#dddddd", "alpha": 0.92, "boxstyle": "round,pad=0.4"},
        )
    elif scene["level_source"] != "annotation_plan_v2" and scene["chart_template"] == "watch_chart":
        ax.text(
            0.008,
            0.92,
            "WAIT FOR CONFIRMATION - watch only - no entry / SL / TP",
            transform=ax.transAxes,
            ha="left",
            va="top",
            color="#ef5350",
            fontsize=8,
            fontweight="bold",
            bbox={"facecolor": "#ffffff", "edgecolor": "#ef5350", "alpha": 0.95, "boxstyle": "round,pad=0.3"},
        )

    if scene["level_source"] != "annotation_plan_v2":
        footer = "TRADE PLAN READY - ENTRY / SL / TP / RR VALIDATED" if scene["chart_template"] == "trade_plan_chart" else "WATCH / REVIEW ONLY"
        footer_color = "#81c784" if scene["chart_template"] == "trade_plan_chart" else "#ef5350"
        ax.text(0.008, 0.015, footer, transform=ax.transAxes, ha="left", va="bottom", color=footer_color, fontsize=7.5)

    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks], color="#555555", fontsize=8)
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(colors="#555555")
    for spine in ax.spines.values():
        spine.set_color("#dddddd")
    ax.spines["left"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.set_xlim(-1, n + 8)
    ax.set_ylim(low - span * 0.14, high + span * 0.18)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return scene


def _resolve_scene_time_geometry(scene: Mapping[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    """Map V2 timestamp geometry into the rendered 15m chart index space."""
    out = dict(scene)
    stamps = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for key in ("drawing_objects", "visible_drawing_objects", "levels", "visible_levels"):
        raw_items = out.get(key) or []
        resolved: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            if item.get("start_time"):
                item["start_index"] = _timestamp_index(stamps, item.get("start_time"))
            if item.get("end_time"):
                item["end_index"] = _timestamp_index(stamps, item.get("end_time"))
            display = item.get("display_geometry")
            if isinstance(display, Mapping):
                resolved_display = dict(display)
                if resolved_display.get("start_time"):
                    resolved_display["start_index"] = _timestamp_index(stamps, resolved_display.get("start_time"))
                if resolved_display.get("end_time"):
                    resolved_display["end_index"] = _timestamp_index(stamps, resolved_display.get("end_time"))
                item["display_geometry"] = resolved_display
            resolved.append(item)
        out[key] = resolved
    return out


def _timestamp_index(stamps: pd.Series, value: Any) -> int | None:
    try:
        target = pd.Timestamp(value)
        if target.tzinfo is None:
            target = target.tz_localize("UTC")
        else:
            target = target.tz_convert("UTC")
    except (TypeError, ValueError):
        return None
    valid = stamps.notna()
    if not valid.any():
        return None
    visible = stamps[valid]
    if target < visible.min() or target > visible.max():
        return None
    deltas = (visible - target).abs()
    return int(deltas.idxmin())


def _scene_levels(scene: Mapping[str, Any]) -> list[dict[str, Any]]:
    colors = {
        "liquidity": "#81c784",
        "poi": "#9467bd",
        "order_block": "#8fbaf5",
        "fvg": "#98c9ff",
        "path": "#777777",
        "bos": "#111111",
        "choch": "#ef5350",
        "idm": "#111111",
        "structure": "#111111",
        "entry": "#fdd835",
        "stop": "#ef5350",
        "target": "#81c784",
        "invalidation": "#ffb74d",
    }
    styles = {
        "liquidity": (0, (2, 3)),
        "poi": "solid",
        "order_block": "solid",
        "fvg": (0, (4, 4)),
        "path": (0, (5, 4)),
        "bos": "solid",
        "choch": "solid",
        "idm": (0, (1, 2)),
        "structure": "solid",
        "entry": "solid",
        "stop": "solid",
        "target": (0, (2, 3)),
        "invalidation": (0, (6, 3)),
    }
    levels: list[dict[str, Any]] = []
    for raw in scene.get("levels", []) or []:
        kind = str(raw.get("kind") or "")
        price = _float(raw.get("price"))
        price_low = _float(raw.get("price_low"))
        price_high = _float(raw.get("price_high"))
        if price is not None:
            low = high = price
        elif price_low is not None and price_high is not None:
            low, high = sorted([price_low, price_high])
        else:
            continue
        start_index = _int(raw.get("start_index"))
        end_index = _int(raw.get("end_index"))
        if start_index is not None and end_index is not None and end_index < start_index:
            start_index, end_index = end_index, start_index
        kind_color = colors.get(kind, "#cfd2dc")
        levels.append({
            "kind": kind,
            "label": str(raw.get("label") or kind).upper(),
            "low": low,
            "high": high,
            "color": kind_color,
            "edge_color": kind_color,
            "alpha": _zone_alpha(kind),
            "linewidth": _line_width(kind),
            "linestyle": _line_style(raw.get("line_style"), styles.get(kind, "solid")),
            "start_index": start_index,
            "end_index": end_index,
            "source_object_type": raw.get("source_object_type"),
            "semantic_object_id": raw.get("semantic_object_id"),
        })
    return levels


def _select_visible_labels(labels: list[Mapping[str, Any]], chart_template: str) -> list[Mapping[str, Any]]:
    """Keep the rendered chart sparse; the full thesis carries the prose."""
    limit = VISIBLE_LABEL_LIMITS.get(chart_template, 3)
    if len(labels) <= limit:
        return labels
    priority = {
        "state": 0,
        "poi": 1,
        "order_block": 1,
        "fvg": 1,
        "bos": 2,
        "choch": 2,
        "structure": 2,
        "idm": 3,
        "sweep": 2,
        "displacement": 4,
        "liquidity": 5,
        "invalidation": 5,
        "entry": 6,
        "stop": 7,
        "target": 8,
        "context": 9,
    }
    indexed = list(enumerate(labels))
    indexed.sort(key=lambda item: (priority.get(str(item[1].get("kind") or ""), 20), item[0]))
    selected_indexes = sorted(index for index, _label in indexed[:limit])
    return [labels[index] for index in selected_indexes]


def _select_visible_levels(levels: list[Mapping[str, Any]], chart_template: str) -> list[Mapping[str, Any]]:
    limit = VISIBLE_LEVEL_LIMITS.get(chart_template, 3)
    if len(levels) <= limit:
        return levels
    priority = {
        "poi": 0,
        "order_block": 0,
        "fvg": 0,
        "bos": 1,
        "choch": 1,
        "structure": 1,
        "idm": 2,
        "entry": 1,
        "stop": 2,
        "target": 3,
        "invalidation": 4,
        "liquidity": 5,
    }
    indexed = list(enumerate(levels))
    indexed.sort(key=lambda item: (priority.get(str(item[1].get("kind") or ""), 20), item[0]))
    selected_indexes = sorted(index for index, _level in indexed[:limit])
    return [levels[index] for index in selected_indexes]


def _select_visible_drawing_objects(objects: list[Mapping[str, Any]], chart_template: str) -> list[Mapping[str, Any]]:
    limit = VISIBLE_LEVEL_LIMITS.get(chart_template, 3)
    if len(objects) <= limit:
        return objects
    priority = {
        "poi_zone": 0,
        "structure_segment": 1,
        "liquidity_line": 2,
        "trade_box": 3,
        "path_projection": 4,
    }
    indexed = list(enumerate(objects))
    indexed.sort(
        key=lambda item: (
            int(item[1].get("importance") or 2),
            priority.get(str(item[1].get("object_type") or ""), 20),
            item[0],
        )
    )
    selected_indexes = sorted(index for index, _obj in indexed[:limit])
    return [objects[index] for index in selected_indexes]


def _drawing_objects_to_levels(objects: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    for obj in objects:
        if obj.get("object_type") in {"path_projection", "trade_box"}:
            continue
        levels.append(
            {
                "label": obj.get("label"),
                "kind": obj.get("kind"),
                "price": obj.get("price"),
                "price_low": obj.get("price_low"),
                "price_high": obj.get("price_high"),
                "timeframe": obj.get("timeframe"),
                "start_index": obj.get("start_index"),
                "end_index": obj.get("end_index"),
                "start_time": obj.get("start_time"),
                "end_time": obj.get("end_time"),
                "line_style": obj.get("line_style"),
                "semantic_object_id": obj.get("semantic_object_id"),
                "source_object_type": obj.get("object_type"),
            }
        )
    return levels


def _object_with_display_geometry(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Keep provenance nested while rendering only the derived display span."""
    item = dict(raw)
    for key, value in effective_display_geometry(raw).items():
        item[key] = value
    return item


def _assign_level_label_positions(levels: list[dict[str, Any]], *, low: float, high: float) -> list[dict[str, Any]]:
    if not levels:
        return []
    span = max(high - low, abs(high) * 0.01, 1e-9)
    groups: dict[float, list[dict[str, Any]]] = {}
    positioned = [dict(level) for level in levels]
    for level in positioned:
        key = round(float(level["high"] if level["kind"] == "poi" and level["low"] != level["high"] else level["low"]), 8)
        groups.setdefault(key, []).append(level)
    for price, group in groups.items():
        if len(group) == 1:
            group[0]["label_y"] = price
            continue
        offset_step = span * 0.018
        midpoint = (len(group) - 1) / 2.0
        for index, level in enumerate(group):
            level["label_y"] = price + (index - midpoint) * offset_step
    return positioned


def _is_zone_kind(kind: str) -> bool:
    return kind in {"poi", "order_block", "fvg"}


def _level_x_span(level: Mapping[str, Any], n: int, chart_template: str) -> tuple[float, float]:
    start = level.get("start_index")
    end = level.get("end_index")
    if start is not None and end is not None:
        left = max(-0.5, min(float(start), n + 6.0))
        right = max(left + 1.0, min(float(end), n + 6.0))
        if _is_zone_kind(str(level.get("kind") or "")) and right - left < 4.0:
            # Preserve the certified origin while giving a one-candle POI enough
            # local width to be legible. The cap keeps it far from a full-width ray.
            local_width = max(6.0, min(12.0, n * 0.10))
            right = min(n - 0.5, left + local_width)
        return left, right
    if _is_zone_kind(str(level.get("kind") or "")):
        width = max(6.0, min(24.0, n * 0.18))
        right = n + 4.0 if chart_template == "trade_plan_chart" else n - 1.0
        return max(0.0, right - width), right
    if level.get("kind") in {"bos", "choch", "structure", "idm"}:
        width = max(8.0, min(28.0, n * 0.22))
        right = max(width + 1.0, n * 0.68)
        return right - width, right
    width = max(10.0, min(32.0, n * 0.28))
    right = n - 1.0
    return max(0.0, right - width), right


def _inline_label(ax: Any, x: float, price: float, text: str, color: str) -> None:
    ax.text(
        x,
        price,
        f" {text} ",
        color=color,
        fontsize=8,
        fontweight="bold",
        ha="center",
        va="center",
        zorder=8,
        bbox={"facecolor": "#ffffff", "edgecolor": "none", "alpha": 0.8, "pad": 1.2},
    )


def _draw_trade_projection(ax: Any, scene: Mapping[str, Any], levels: list[Mapping[str, Any]], n: int) -> None:
    entry = _first_level(levels, {"entry"})
    stop = _first_level(levels, {"stop"})
    target = _first_level(levels, {"target"})
    if not entry or not stop or not target:
        return
    x1 = max(0.0, n * 0.72)
    x2 = n + 5.0
    entry_price = entry["low"]
    stop_price = stop["low"]
    target_price = target["low"]
    top = max(entry_price, stop_price)
    bottom = min(entry_price, stop_price)
    ax.add_patch(Rectangle((x1, bottom), x2 - x1, top - bottom, color="#ef5350", alpha=0.18, zorder=0, linewidth=0))
    top = max(entry_price, target_price)
    bottom = min(entry_price, target_price)
    ax.add_patch(Rectangle((x1, bottom), x2 - x1, top - bottom, color="#26a69a", alpha=0.18, zorder=0, linewidth=0))
    ax.add_patch(
        FancyArrowPatch(
            (x1, entry_price),
            (x1 + (x2 - x1) * 0.55, target_price),
            connectionstyle="arc3,rad=-0.2",
            arrowstyle="->",
            color="#d6d8de",
            linewidth=1.0,
            alpha=0.7,
            mutation_scale=10,
            zorder=6,
        )
    )


def _first_v2_trade_box(objects: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return next((obj for obj in objects if obj.get("object_type") == "trade_box"), None)


def _draw_v2_trade_box(ax: Any, obj: Mapping[str, Any], n: int) -> None:
    entry = _float(obj.get("entry_price"))
    stop = _float(obj.get("stop_price"))
    targets = [_float(value) for value in (obj.get("target_prices") or [])]
    targets = [value for value in targets if value is not None]
    if entry is None or stop is None or not targets:
        return
    start = _int(obj.get("start_index"))
    end = _int(obj.get("end_index"))
    x1 = max(0.0, float(start if start is not None else int(n * 0.72)))
    x2 = max(x1 + 6.0, float(end if end is not None else n + 5))
    x2 = min(x2, n + 6.0)
    primary_target = targets[0]
    ax.add_patch(Rectangle((x1, min(entry, stop)), x2 - x1, abs(entry - stop), color="#ef5350", alpha=0.16, zorder=0, linewidth=0))
    ax.add_patch(Rectangle((x1, min(entry, primary_target)), x2 - x1, abs(entry - primary_target), color="#26a69a", alpha=0.16, zorder=0, linewidth=0))
    for price, label, color, style in (
        (entry, "ENTRY", "#d6a700", "solid"),
        (stop, "SL", "#ef5350", "solid"),
    ):
        ax.plot([x1, x2], [price, price], color=color, linestyle=style, linewidth=1.0, zorder=6)
        _inline_label(ax, x2, price, label, color)
    for idx, target in enumerate(targets, start=1):
        ax.plot([x1, x2], [target, target], color="#26a69a", linestyle=(0, (2, 3)), linewidth=1.0, zorder=6)
        _inline_label(ax, x2, target, f"TP{idx}", "#26a69a")


def _draw_v2_path_objects(ax: Any, objects: list[Mapping[str, Any]], n: int) -> None:
    for obj in objects:
        if obj.get("object_type") != "path_projection":
            continue
        start = _int(obj.get("start_index"))
        end = _int(obj.get("end_index"))
        price_low = _float(obj.get("price_low"))
        price_high = _float(obj.get("price_high"))
        if start is None or end is None or price_low is None or price_high is None:
            continue
        left = max(-0.5, min(float(start), n + 6.0))
        right = max(left + 1.0, min(float(end), n + 6.0))
        ax.add_patch(
            FancyArrowPatch(
                (left, price_low),
                (right, price_high),
                connectionstyle="arc3,rad=0.15",
                arrowstyle="->",
                color="#777777",
                linewidth=1.05,
                linestyle=(0, (5, 4)),
                alpha=0.5,
                mutation_scale=9,
                zorder=5,
            )
        )
        _inline_label(ax, right, price_high, str(obj.get("label") or "PATH"), "#777777")


def _v2_path_prices(objects: list[Mapping[str, Any]]) -> list[float]:
    prices: list[float] = []
    for obj in objects:
        if obj.get("object_type") != "path_projection":
            continue
        for key in ("price", "price_low", "price_high"):
            value = _float(obj.get(key))
            if value is not None:
                prices.append(value)
    return prices


def _first_level(levels: list[Mapping[str, Any]], kinds: set[str]) -> Mapping[str, Any] | None:
    return next((level for level in levels if level.get("kind") in kinds), None)


def _zone_alpha(kind: str) -> float:
    if kind == "fvg":
        return 0.14
    if kind == "order_block":
        return 0.20
    if kind == "poi":
        return 0.20
    return 0.18


def _line_width(kind: str) -> float:
    if kind in {"bos", "choch", "structure"}:
        return 1.05
    if kind == "idm":
        return 0.85
    return 1.0


def _line_style(raw: Any, fallback: Any) -> Any:
    if raw == "dotted":
        return (0, (1, 2))
    if raw == "dashed":
        return (0, (4, 4))
    if raw == "solid":
        return "solid"
    return fallback


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={"index": "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out.sort_values("timestamp").reset_index(drop=True)


def _right_label(ax: Any, n: int, price: float, text: str, color: str) -> None:
    ax.text(n + 0.8, price, f" {text}", color=color, fontsize=8, fontweight="bold", va="center", zorder=8)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
