"""Professional SMC watch-chart renderer.

This renderer consumes the final SMC narrative authority, not raw detector
events. It is deliberately sparse: no trade box, no TP/SL labels, no detector
firehose.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle


def render_watch_chart(
    df: pd.DataFrame,
    narrative_authority: Mapping[str, Any],
    output_path: str | Path,
    *,
    timeframe: str = "15m",
) -> None:
    if df.empty:
        raise ValueError("Cannot render watch chart from an empty dataframe.")
    if narrative_authority.get("show_trade_box"):
        raise ValueError("watch_chart_renderer cannot render trade boxes.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = df.reset_index(drop=True).copy()
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    visible_low = float(l.min())
    visible_high = float(h.max())
    span = max(visible_high - visible_low, 1.0)

    levels = _authority_levels(narrative_authority)
    for level in levels:
        price = _float(level.get("price"))
        if price is not None:
            visible_low = min(visible_low, price)
            visible_high = max(visible_high, price)
    span = max(visible_high - visible_low, 1.0)
    y_low = visible_low - span * 0.12
    y_high = visible_high + span * 0.16

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.62)

    up, dn = "#26a69a", "#ef5350"
    body_floor = span * 1e-3
    for i in range(n):
        col = up if c[i] >= o[i] else dn
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
        lo_b, hi_b = min(o[i], c[i]), max(o[i], c[i])
        ax.add_patch(Rectangle((i - 0.34, lo_b), 0.68, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))

    active_poi = narrative_authority.get("official_active_poi") or {}
    p_low = _float(active_poi.get("price_low"))
    p_high = _float(active_poi.get("price_high"))
    if p_low is not None and p_high is not None:
        lo, hi = sorted([p_low, p_high])
        ax.add_patch(Rectangle((n * 0.68, lo), n * 0.28, hi - lo, color="#9467bd", alpha=0.24, zorder=1, linewidth=0))
        _right_label(ax, n, hi, f"WATCH ZONE {active_poi.get('zone_label')}", "#c39be8")

    for level in levels:
        price = _float(level.get("price"))
        if price is None:
            continue
        if level.get("kind") == "invalidation":
            color = "#ffb74d"
            label = f"INVALIDATION {level.get('label')} (not SL)"
            linestyle = (0, (6, 3))
            linewidth = 1.2
        else:
            color = "#81c784"
            label = f"LIQUIDITY DRAW {level.get('label')} (not TP)"
            linestyle = (0, (2, 3))
            linewidth = 1.0
        ax.axhline(price, color=color, linestyle=linestyle, linewidth=linewidth, alpha=0.85, zorder=4)
        _right_label(ax, n, price, label, color)

    last_px = float(c[-1])
    ax.axhline(last_px, color="#cfd2dc", linestyle=(0, (1, 2)), linewidth=0.8, alpha=0.55, zorder=4)
    _right_label(ax, n, last_px, f"LAST {last_px:,.4g}", "#cfd2dc")

    symbol = narrative_authority.get("symbol", "")
    model = str(narrative_authority.get("official_model") or "model")
    state = str(narrative_authority.get("official_state") or "WATCH_ONLY")
    bias = str(narrative_authority.get("official_bias") or "neutral")
    title = f"{symbol} {timeframe} - {model.replace('_', ' ')} | {state}"
    ax.set_title(title, color="#e0e0e0", fontsize=12, fontweight="bold", loc="left")
    ax.text(
        0.008,
        0.985,
        f"bias {bias}  ·  chart template watch_chart  ·  trade box false",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#aab0be",
        fontsize=9,
        fontweight="bold",
    )

    panel_lines = _panel_lines(narrative_authority)
    ax.text(
        0.008,
        0.92,
        "\n".join(panel_lines[:8]),
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#e7e9ef",
        fontsize=8,
        linespacing=1.35,
        bbox={"facecolor": "#151922", "edgecolor": "#3a3f4b", "alpha": 0.78, "boxstyle": "round,pad=0.4"},
    )
    ax.text(
        0.008,
        0.015,
        "WATCH ONLY  ·  NO ENTRY  ·  NO STOP LOSS  ·  NO TAKE PROFIT TRADE BOX",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        color="#ef5350",
        fontsize=8,
        fontweight="bold",
        alpha=0.9,
    )
    ax.text(
        0.5,
        -0.085,
        "Official watch chart · Narrative authority only · Debug detector labels hidden",
        transform=ax.transAxes,
        ha="center",
        va="top",
        color="#9598a1",
        fontsize=8,
    )

    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks], color="#9598a1", fontsize=8)
    ax.tick_params(colors="#9598a1")
    for spine in ax.spines.values():
        spine.set_color("#2a2e39")
    ax.set_xlim(-1, n + 22)
    ax.set_ylim(y_low, y_high)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def _authority_levels(authority: Mapping[str, Any]) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    invalidation = authority.get("official_invalidation") or {}
    if invalidation.get("price") not in {None, ""}:
        levels.append({"kind": "invalidation", "price": invalidation.get("price"), "label": invalidation.get("condition") or invalidation.get("price")})
    for draw in authority.get("official_liquidity_draw", []) or []:
        if draw.get("price") not in {None, ""}:
            levels.append({"kind": "liquidity", "price": draw.get("price"), "label": f"{draw.get('timeframe')} {draw.get('label')}"})
    return levels


def _panel_lines(authority: Mapping[str, Any]) -> list[str]:
    active = authority.get("official_active_poi") or {}
    confirmation = authority.get("official_confirmation_needed") or {}
    invalidation = authority.get("official_invalidation") or {}
    lines = [
        f"State: {authority.get('official_state')}",
        f"Model: {authority.get('official_model')}",
    ]
    if active:
        lines.append(f"Watch zone: {active.get('zone_label')}")
    if confirmation:
        lines.append(f"Confirmation: {confirmation.get('summary')}")
    if invalidation:
        lines.append(f"Invalidation: {invalidation.get('condition')}")
    draws = authority.get("official_liquidity_draw", []) or []
    if draws:
        lines.append("Liquidity draw: " + ", ".join(_draw_text(draw) for draw in draws[:3]))
    lines.append("Trade plan: WATCH_ONLY")
    return lines


def _draw_text(draw: Mapping[str, Any]) -> str:
    if draw.get("price") not in {None, ""}:
        return f"{draw.get('timeframe')} {draw.get('price')}"
    return str(draw.get("label") or "liquidity")


def _right_label(ax: Any, n: int, price: float, text: str, color: str) -> None:
    ax.text(n + 0.8, price, f" {text}", color=color, fontsize=8, fontweight="bold", va="center", zorder=8)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
