from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class OverlayStats:
    boxes: int
    lines: int
    labels: int


def _timestamp_ms(value: str) -> int:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    else:
        ts = ts.tz_convert(timezone.utc)
    return int(ts.timestamp() * 1000)


def _future_ms(decision_time: str, days: int = 3) -> int:
    ts = pd.Timestamp(decision_time)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    else:
        ts = ts.tz_convert(timezone.utc)
    return int((ts + timedelta(days=days)).timestamp() * 1000)


def _pine_string(value: str) -> str:
    return json.dumps(str(value))


def _color_for_zone(zone: dict[str, Any]) -> tuple[str, int]:
    if zone.get("kind") == "liquidity":
        return "color.purple", 86
    if zone.get("direction") == "bullish":
        return "color.lime", 86
    if zone.get("direction") == "bearish":
        return "color.red", 86
    return "color.gray", 88


def _line_color(name: str) -> str:
    lowered = name.lower()
    if "invalid" in lowered or "stop" in lowered:
        return "color.red"
    if "bearish" in lowered or "bear" in lowered:
        return "color.red"
    if "bullish" in lowered or "bull" in lowered:
        return "color.lime"
    if "target" in lowered or "liquidity" in lowered:
        return "color.lime"
    if "entry" in lowered or "poi" in lowered:
        return "color.blue"
    return "color.gray"


def _is_visible_zone(zone: dict[str, Any]) -> bool:
    return (
        zone.get("kind") in {"fvg", "order_block", "liquidity"}
        and zone.get("low") is not None
        and zone.get("high") is not None
        and zone.get("status") != "mitigated"
    )


def _rank_zone(zone: dict[str, Any]) -> tuple[float, int]:
    return (float(zone.get("score") or zone.get("confidence") or 0.0), int(zone.get("end_index") or 0))


def _zone_start_time(case: dict[str, Any], zone: dict[str, Any]) -> str:
    # The compact case payload stores candle indices but not every candle's
    # timestamp. Anchor boxes at the decision time and extend right so the
    # current actionable zones are precise in price without pretending to know
    # a historical x-coordinate that is not in the case.
    return case["decision_time"]


def _selected_poi(case: dict[str, Any]) -> dict[str, Any] | None:
    return case.get("machine_analysis", {}).get("trade_plan", {}).get("selected_poi")


def _zones_for_overlay(case: dict[str, Any], max_zones: int = 12) -> list[dict[str, Any]]:
    zones = [zone for zone in case.get("machine_analysis", {}).get("zones", []) if _is_visible_zone(zone)]
    selected = _selected_poi(case)
    if selected:
        selected_label = selected.get("label")
        zones = [zone for zone in zones if zone.get("label") != selected_label or zone.get("low") != selected.get("low")]
        zones.insert(0, {**selected, "_selected": True})
    rest = zones[:1] + sorted(zones[1:], key=_rank_zone, reverse=True)
    return rest[:max_zones]


def _plan_lines(case: dict[str, Any]) -> list[dict[str, Any]]:
    plan = case.get("machine_analysis", {}).get("trade_plan", {})
    lines: list[dict[str, Any]] = []
    seen_prices: set[float] = set()

    def add(label: str, price: float) -> None:
        rounded = round(float(price), 5)
        if rounded in seen_prices:
            return
        seen_prices.add(rounded)
        lines.append({"label": label, "price": rounded})

    selected = plan.get("selected_poi")
    if selected and selected.get("low") is not None and selected.get("high") is not None:
        mid = (float(selected["low"]) + float(selected["high"])) / 2.0
        add("POI midpoint", mid)
    if plan.get("invalidation") is not None:
        add("Execution SL / stop", float(plan["invalidation"]))
    if plan.get("structural_invalidation") is not None:
        add("Structural invalidation", float(plan["structural_invalidation"]))
    for index, target in enumerate(plan.get("targets") or [], start=1):
        add(f"Target {index}", float(target))
    if plan.get("liquidity_target") is not None:
        add("Liquidity target", float(plan["liquidity_target"]))
    return lines


def _events_for_overlay(case: dict[str, Any], max_events: int = 16) -> list[dict[str, Any]]:
    events = [
        event
        for event in case.get("machine_analysis", {}).get("events", [])
        if event.get("label") in {"BOS", "CHoCH", "Liquidity Sweep"}
        and event.get("timestamp")
        and event.get("price") is not None
    ]
    return events[-max_events:]


def build_tradingview_pine_overlay(case: dict[str, Any]) -> tuple[str, OverlayStats]:
    symbol = case.get("symbol") or "SMC"
    exchange = case.get("exchange") or ""
    decision_time = case["decision_time"]
    right = _future_ms(decision_time)
    left_default = _timestamp_ms(decision_time)
    lines: list[str] = [
        "//@version=6",
        f'indicator("SMC Desk Overlay - {symbol}", overlay = true, max_lines_count = 500, max_boxes_count = 500, max_labels_count = 500)',
        "",
        "// Generated by smc-codex-desk. Research support only; not financial advice.",
        f"// Case: {case.get('case_id')}",
        f"// Source: {exchange}:{symbol}".rstrip(":"),
        f"// Decision time: {decision_time}",
        "",
        "var line[] smcLines = array.new_line()",
        "var box[] smcBoxes = array.new_box()",
        "var label[] smcLabels = array.new_label()",
        "",
        "clearOverlay() =>",
        "    while array.size(smcLines) > 0",
        "        line.delete(array.pop(smcLines))",
        "    while array.size(smcBoxes) > 0",
        "        box.delete(array.pop(smcBoxes))",
        "    while array.size(smcLabels) > 0",
        "        label.delete(array.pop(smcLabels))",
        "",
        "if barstate.islast",
        "    clearOverlay()",
    ]
    box_count = 0
    line_count = 0
    label_count = 0

    for zone in _zones_for_overlay(case):
        color, transparency = _color_for_zone(zone)
        low = float(zone["low"])
        high = float(zone["high"])
        top = max(low, high)
        bottom = min(low, high)
        left = _timestamp_ms(_zone_start_time(case, zone)) if zone.get("start_index") is not None else left_default
        label = zone.get("label") or zone.get("kind") or "zone"
        selected_prefix = "SELECTED POI - " if zone.get("_selected") else ""
        text = f"{selected_prefix}{label} {bottom:.2f}-{top:.2f}"
        border = "color.blue" if zone.get("_selected") else color
        lines.append(
            "    array.push(smcBoxes, box.new(left = {left}, top = {top}, right = {right}, bottom = {bottom}, "
            "xloc = xloc.bar_time, extend = extend.right, bgcolor = color.new({color}, {transparency}), "
            "border_color = {border}, text = {text}, text_color = color.white, text_size = size.tiny))".format(
                left=left,
                top=round(top, 5),
                right=right,
                bottom=round(bottom, 5),
                color=color,
                transparency=transparency,
                border=border,
                text=_pine_string(text),
            )
        )
        box_count += 1

    for plan_line in _plan_lines(case):
        price = round(float(plan_line["price"]), 5)
        label = plan_line["label"]
        color = _line_color(label)
        lines.append(
            "    array.push(smcLines, line.new(x1 = {left}, y1 = {price}, x2 = {right}, y2 = {price}, "
            "xloc = xloc.bar_time, extend = extend.right, color = {color}, style = line.style_dashed, width = 2))".format(
                left=left_default,
                right=right,
                price=price,
                color=color,
            )
        )
        lines.append(
            "    array.push(smcLabels, label.new(x = {right}, y = {price}, xloc = xloc.bar_time, text = {text}, "
            "style = label.style_label_left, color = color.new({color}, 10), textcolor = color.white, size = size.tiny))".format(
                right=right,
                price=price,
                text=_pine_string(f"{label}: {price:.2f}"),
                color=color,
            )
        )
        line_count += 1
        label_count += 1

    for event in _events_for_overlay(case):
        price = round(float(event["price"]), 5)
        label = f"{event.get('label')} {event.get('direction')}"
        color = "color.orange" if event.get("label") == "Liquidity Sweep" else _line_color(event.get("direction") or "")
        style = "label.style_label_up" if event.get("direction") == "bullish" else "label.style_label_down"
        lines.append(
            "    array.push(smcLabels, label.new(x = {x}, y = {price}, xloc = xloc.bar_time, text = {text}, "
            "style = {style}, color = color.new({color}, 0), textcolor = color.white, size = size.tiny))".format(
                x=_timestamp_ms(event["timestamp"]),
                price=price,
                text=_pine_string(label),
                style=style,
                color=color,
            )
        )
        label_count += 1

    lines.extend(
        [
            "",
            "// Guardrail: this overlay visualizes deterministic SMC Desk levels.",
            "// The model should explain these levels; it should not invent extra levels from pixels.",
        ]
    )
    return "\n".join(lines) + "\n", OverlayStats(boxes=box_count, lines=line_count, labels=label_count)


def write_tradingview_overlay(case_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    pine, stats = build_tradingview_pine_overlay(case)
    target = output_path or case_path.with_name("tradingview_overlay.pine")
    target.write_text(pine, encoding="utf-8")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_path": str(case_path.resolve()),
        "pine_path": str(target.resolve()),
        "boxes": stats.boxes,
        "lines": stats.lines,
        "labels": stats.labels,
        "installation_note": "Paste this Pine Script into TradingView Pine Editor and add it to the chart. Public TradingView pages do not expose the Charting Library Drawings API directly.",
    }
    manifest_path = target.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
