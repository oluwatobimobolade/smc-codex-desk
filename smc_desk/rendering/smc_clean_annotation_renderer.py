"""Clean official SMC annotation renderer.

Official charts are narrative-authority charts, not detector dumps. Raw BOS,
CHoCH, minor swings, duplicate FVGs, weak POIs, and far historical POIs belong
only in debug charts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle


DEPRECATED_DEBUG_ONLY = {
    "legacy_annotation_renderer",
    "raw_detector_story_chart",
    "old_target_selector",
    "old_trade_plan_builder",
    "old_thesis_writer",
}

HIDDEN_FROM_OFFICIAL_CHART = [
    "raw BOS labels",
    "raw CHoCH labels",
    "minor swings",
    "detector FVG clutter",
    "weak POIs",
    "duplicate labels",
    "far historical POIs",
]


def build_clean_annotation_scene(official_decision: Mapping[str, Any], *, mode: str | None = None) -> dict[str, Any]:
    chart_mode = _mode(official_decision, mode)
    steps = [str(step) for step in official_decision.get("reasoning_steps", []) or []]
    numbered = [{"number": index, "text": step} for index, step in enumerate(steps[:8], start=1)]
    show_trade_box = bool(official_decision.get("show_trade_box"))
    scene = {
        "schema": "smc_clean_annotation_scene_v1",
        "source": "OfficialSMCDecision",
        "mode": chart_mode,
        "symbol": official_decision.get("symbol"),
        "official_model": official_decision.get("official_model"),
        "official_state": official_decision.get("official_state"),
        "official_trade_plan_state": official_decision.get("official_trade_plan_state") or official_decision.get("trade_plan_state"),
        "show_trade_box": show_trade_box,
        "numbered_reasoning_labels": numbered,
        "hidden_from_official_chart": list(HIDDEN_FROM_OFFICIAL_CHART),
        "deprecated_debug_only_sources": sorted(DEPRECATED_DEBUG_ONLY),
        "debug_chart_label": "DEBUG ONLY - NOT OFFICIAL TRADE THESIS",
    }
    assert_clean_annotation_scene(scene, official_decision)
    return scene


def assert_clean_annotation_scene(scene: Mapping[str, Any], official_decision: Mapping[str, Any]) -> None:
    if scene.get("source") != "OfficialSMCDecision":
        raise AssertionError("Official chart must use only OfficialSMCDecision.")
    if not scene.get("numbered_reasoning_labels"):
        raise AssertionError("Official chart must expose numbered SMC reasoning labels.")
    if scene.get("show_trade_box") and scene.get("official_trade_plan_state") != "TRADE_PLAN_READY":
        raise AssertionError("Only TRADE_PLAN_READY may show official entry/SL/TP/RR.")
    if scene.get("mode") != "trade_plan_chart" and scene.get("show_trade_box"):
        raise AssertionError("Watch/context charts cannot show trade boxes.")
    hidden = " ".join(scene.get("hidden_from_official_chart", []))
    for forbidden in ("raw BOS", "raw CHoCH", "minor swings"):
        if forbidden not in hidden:
            raise AssertionError(f"Official chart did not hide {forbidden}.")
    if official_decision.get("official_trade_plan_state") != "TRADE_PLAN_READY":
        if official_decision.get("entry") is not None or official_decision.get("stop_loss") is not None or official_decision.get("targets"):
            raise AssertionError("Watch-only OfficialSMCDecision cannot carry executable trade levels.")


def render_smc_clean_annotation_chart(
    df: pd.DataFrame,
    official_decision: Mapping[str, Any],
    output_path: str | Path,
    *,
    mode: str | None = None,
    timeframe: str = "15m",
) -> dict[str, Any]:
    if df.empty:
        raise ValueError("Cannot render clean SMC chart from an empty dataframe.")
    scene = build_clean_annotation_scene(official_decision, mode=mode)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = df.reset_index(drop=True).copy()
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)

    levels = _levels(official_decision, scene["mode"])
    low = min([float(l.min()), *[item["price"] for item in levels]]) if levels else float(l.min())
    high = max([float(h.max()), *[item["price"] for item in levels]]) if levels else float(h.max())
    span = max(high - low, 1.0)

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.58)

    up, dn = "#26a69a", "#ef5350"
    body_floor = span * 1e-3
    for index in range(n):
        color = up if c[index] >= o[index] else dn
        ax.plot([index, index], [l[index], h[index]], color=color, linewidth=0.7, zorder=2)
        ax.add_patch(Rectangle((index - 0.34, min(o[index], c[index])), 0.68, max(abs(c[index] - o[index]), body_floor), color=color, zorder=3, linewidth=0))

    active_poi = official_decision.get("active_poi") or official_decision.get("official_active_poi") or {}
    p_low = _float(active_poi.get("price_low"))
    p_high = _float(active_poi.get("price_high"))
    if p_low is not None and p_high is not None:
        lo, hi = sorted([p_low, p_high])
        ax.add_patch(Rectangle((n * 0.66, lo), n * 0.29, hi - lo, color="#9467bd", alpha=0.23, zorder=1, linewidth=0))
        _right_label(ax, n, hi, f"POI {active_poi.get('zone_label')}", "#c39be8")

    for level in levels:
        color = level["color"]
        ax.axhline(level["price"], color=color, linestyle=level["linestyle"], linewidth=1.1, alpha=0.86, zorder=4)
        _right_label(ax, n, level["price"], level["label"], color)

    title = f"{official_decision.get('symbol')} {timeframe} | Official SMC {scene['mode']} | {official_decision.get('official_model')}"
    ax.set_title(title, color="#e0e0e0", fontsize=12, fontweight="bold", loc="left")
    ax.text(
        0.008,
        0.985,
        f"state {official_decision.get('official_state')}  ·  trade box {str(scene['show_trade_box']).lower()}  ·  source OfficialSMCDecision",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#aab0be",
        fontsize=9,
        fontweight="bold",
    )

    labels = scene["numbered_reasoning_labels"]
    panel = "\n".join(f"{item['number']}. {item['text']}" for item in labels[:7])
    ax.text(
        0.008,
        0.92,
        panel,
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#e7e9ef",
        fontsize=8,
        linespacing=1.35,
        bbox={"facecolor": "#151922", "edgecolor": "#3a3f4b", "alpha": 0.8, "boxstyle": "round,pad=0.4"},
    )

    if scene["mode"] != "trade_plan_chart":
        footer = "WATCH / REVIEW ONLY - NO ENTRY - NO STOP LOSS - NO TAKE PROFIT TRADE BOX"
        footer_color = "#ef5350"
    else:
        footer = "TRADE PLAN READY - ENTRY / SL / TP / RR AUTHORIZED BY NARRATIVE AUTHORITY"
        footer_color = "#81c784"
    ax.text(0.008, 0.015, footer, transform=ax.transAxes, ha="left", va="bottom", color=footer_color, fontsize=8, fontweight="bold")
    ax.text(0.5, -0.085, "Detector clutter hidden from official chart · Debug charts are separate", transform=ax.transAxes, ha="center", va="top", color="#9598a1", fontsize=8)

    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks], color="#9598a1", fontsize=8)
    ax.tick_params(colors="#9598a1")
    for spine in ax.spines.values():
        spine.set_color("#2a2e39")
    ax.set_xlim(-1, n + 24)
    ax.set_ylim(low - span * 0.14, high + span * 0.18)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return scene


def _mode(decision: Mapping[str, Any], mode: str | None) -> str:
    if mode:
        return mode
    template = str(decision.get("chart_template") or "watch_chart")
    if template == "trade_plan_chart":
        return "trade_plan_chart"
    if template == "review_chart":
        return "review_chart"
    return "watch_chart"


def _levels(decision: Mapping[str, Any], mode: str) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    if mode == "trade_plan_chart":
        entry = _float(decision.get("entry"))
        stop = _float(decision.get("stop_loss"))
        if entry is not None:
            levels.append({"price": entry, "label": "ENTRY", "color": "#fdd835", "linestyle": "solid"})
        if stop is not None:
            levels.append({"price": stop, "label": "SL", "color": "#ef5350", "linestyle": "solid"})
        for index, target in enumerate(decision.get("targets", []) or decision.get("take_profit", []) or [], start=1):
            price = _float(target.get("price") if isinstance(target, Mapping) else target)
            if price is not None:
                levels.append({"price": price, "label": f"TP{index}", "color": "#81c784", "linestyle": (0, (2, 3))})
        return levels

    invalidation = decision.get("invalidation") or decision.get("official_invalidation") or {}
    price = _float(invalidation.get("price"))
    if price is not None:
        levels.append({"price": price, "label": "INVALIDATION (not SL)", "color": "#ffb74d", "linestyle": (0, (6, 3))})
    for draw in decision.get("official_liquidity_draw", []) or []:
        price = _float(draw.get("price"))
        if price is not None:
            label = str(draw.get("label") or "LIQUIDITY DRAW")
            levels.append({"price": price, "label": f"{label} (not TP)", "color": "#81c784", "linestyle": (0, (2, 3))})
    return levels


def _right_label(ax: Any, n: int, price: float, text: str, color: str) -> None:
    ax.text(n + 0.8, price, f" {text}", color=color, fontsize=8, fontweight="bold", va="center", zorder=8)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

