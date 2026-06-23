from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
from PIL import Image

from .models import AnalysisResult
from .visual_geometry import (
    event_display_confidence,
    has_actionable_plan,
    plan_levels,
    select_display_events,
    structure_origin_index,
    zone_display_confidence,
    zone_lifecycle,
    zone_visual_key,
)


def render_annotated_chart(df: pd.DataFrame, analysis: AnalysisResult, output_path: str) -> None:
    """Compatibility entry point for the one canonical SMC annotation renderer."""
    render_smc_annotated(
        df,
        analysis,
        output_path,
        min_conf="medium",
        title=(
            f"{analysis.symbol} {analysis.timeframe} SMC Analysis | "
            f"{analysis.trade_plan.verdict} Grade {analysis.trade_plan.setup_grade}"
        ),
    )


def render_smc_annotated(
    df: pd.DataFrame,
    analysis: AnalysisResult,
    output_path: str,
    config=None,
    min_conf: str = "medium",
    title: str | None = None,
    show_swings: bool = True,
    show_medium_labels: bool = False,
) -> None:
    """Professional SMC annotation, drawn manually so every mark lands on the exact candle.

    Uses the engine's significance/robustness heuristic (not a claim of real-market accuracy):
    HIGH objects are solid + labelled, MEDIUM remain faint and unlabeled by default, LOW are
    dropped. This keeps the detailed view inspectable instead of turning it into a wall of
    text. Conventions: FVG/OB shaded boxes, liquidity pools as EQH/EQL lines, BOS/CHoCH at
    the broken level, sweep markers, and premium/discount with a 50% equilibrium line.
    """
    import numpy as np
    from matplotlib.patches import Rectangle

    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    n = len(df)
    if n == 0:
        raise ValueError("Cannot render an empty OHLCV dataframe.")
    rank = {"low": 0, "medium": 1, "high": 2}; minr = rank[min_conf]

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#0e1117"); ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.6)
    up, dn = "#26a69a", "#ef5350"
    body_floor = (float(h.max()) - float(l.min())) * 1e-3
    for i in range(n):
        col = up if c[i] >= o[i] else dn
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
        lo_b, hi_b = min(o[i], c[i]), max(o[i], c[i])
        ax.add_patch(Rectangle((i - 0.34, lo_b), 0.68, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))

    # label de-confliction: nudge overlapping labels apart
    yr = float(h.max() - l.min()) or 1.0
    _placed: list[tuple[float, float]] = []

    def _label(x, y, text, color, size, weight="normal", va="center"):
        step = yr * 0.022
        yy = float(y)
        for _ in range(14):
            if not any(abs(px - x) < n * 0.06 and abs(py - yy) < step * 0.85 for px, py in _placed):
                break
            yy += step
        _placed.append((float(x), yy))
        ax.text(x, yy, text, color=color, fontsize=size, fontweight=weight, va=va, zorder=9)

    # faint swing points
    if show_swings:
        for sw in analysis.swings:
            if 0 <= sw.index < n:
                ax.scatter([sw.index], [sw.price], s=7, color="#5c6b7a", marker="o", zorder=4, alpha=0.45)

    _liq_levels: list[float] = []  # de-dup stacked EQH/EQL lines
    selected = analysis.trade_plan.selected_poi
    selected_key = zone_visual_key(selected) if selected is not None else None
    selected_drawn = False

    # premium / discount + equilibrium
    rl = float(analysis.metrics.get("range_low") or l.min()); rh = float(analysis.metrics.get("range_high") or h.max())
    eq = (rl + rh) / 2.0
    ax.axhspan(eq, rh, color="#ef5350", alpha=0.04); ax.axhspan(rl, eq, color="#26a69a", alpha=0.04)
    ax.axhline(eq, color="#787b86", linestyle="--", linewidth=0.8)
    ax.text(0, eq, " equilibrium (50%)", color="#9598a1", fontsize=7, va="bottom")

    # Zones run from confirmation to resolution. Active zones end exactly at
    # the decision candle; mitigated/swept zones are omitted from this live view.
    for z in analysis.zones:
        g = zone_display_confidence(analysis, df, z)
        is_selected = selected_key == zone_visual_key(z)
        if rank[g] < minr and not is_selected:
            continue
        lifecycle = zone_lifecycle(df, z, analysis.events)
        if not lifecycle.is_active:
            continue
        alpha = 0.26 if is_selected else 0.22 if g == "high" else 0.09
        si = lifecycle.activation_index
        ei = lifecycle.end_index
        if z.kind == "liquidity":
            lvl = z.high if z.direction == "bearish" else z.low
            if any(abs(lvl - p) <= max(lvl, 1e-9) * 0.0012 for p in _liq_levels):
                continue  # merge near-duplicate liquidity lines
            _liq_levels.append(lvl)
            ax.plot([si, ei], [lvl, lvl], color="#b39ddb", linestyle=(0, (4, 3)),
                    linewidth=1.1 if g == "high" else 0.8, alpha=0.95 if g == "high" else 0.5, zorder=4)
            if g == "high" or is_selected or (g == "medium" and show_medium_labels):
                _label(ei, lvl, "  EQH" if z.direction == "bearish" else "  EQL",
                   "#b39ddb", 8, "bold" if g == "high" else "normal")
            selected_drawn = selected_drawn or is_selected
            continue
        if z.kind == "fvg":
            col, lab = (up if z.direction == "bullish" else dn), "FVG"
        elif z.kind == "order_block":
            col, lab = ("#3179f5" if z.direction == "bullish" else "#ff9800"), "OB"
        else:
            continue
        width = max(ei - si, 0.55)
        ax.add_patch(Rectangle((si, z.low), width, z.high - z.low, color=col, alpha=alpha, zorder=1, linewidth=0))
        if g == "high" or is_selected or (g == "medium" and show_medium_labels):
            prefix = "SELECTED " if is_selected else ""
            _label(si, z.high, f" {prefix}{lab}", col, 8, "bold", va="bottom")
        selected_drawn = selected_drawn or is_selected

    # events — structure breaks, plus sweeps that raided prominent liquidity
    for ev in select_display_events(analysis.events):
        ti = int(ev.index)
        if not (0 <= ti < n):
            continue
        g = event_display_confidence(analysis, df, ev)
        col = up if ev.direction == "bullish" else dn
        if ev.label == "Liquidity Sweep":
            # Show a sweep when it raided a PROMINENT level: the swept high/low was the local
            # extreme over the prior ~12 bars (real resting liquidity), not a micro-wiggle.
            # This surfaces the meaningful raids a trader marks and hides hyperactive sweeps.
            lvl = ev.swept_level if ev.swept_level is not None else ev.price
            lo = max(0, ti - 12)
            tol = yr * 0.002
            if ev.direction == "bearish":
                prominent = ti > lo and lvl >= float(h[lo:ti].max()) - tol
            else:
                prominent = ti > lo and lvl <= float(l[lo:ti].min()) + tol
            if rank[g] < minr and not prominent:
                continue
            mk = "v" if ev.direction == "bearish" else "^"
            ax.scatter([ti], [lvl], marker=mk, color="#ffd54f", s=72, zorder=7, edgecolors="#0e1117", linewidths=0.6)
            if g == "high" or prominent or (g == "medium" and show_medium_labels):
                _label(ti, lvl, " sweep", "#ffd54f", 8, "bold")
        else:  # BOS / CHoCH: source protected swing to the breaking candle.
            if rank[g] < minr:
                continue
            origin = structure_origin_index(ev, analysis.swings, df)
            if origin is not None and ev.broken_level is not None:
                ax.plot([origin, ti], [ev.broken_level, ev.broken_level], color=col,
                        linestyle=(0, (3, 2)), linewidth=1.0, alpha=0.85, zorder=4)
            if g == "high" or (g == "medium" and show_medium_labels):
                _label(ti, ev.price, f" {ev.label}", col, 9 if g == "high" else 7,
                       "bold" if g == "high" else "normal")

    # A trade plan is state at the decision candle, not a historical ray. Draw
    # it as a right-edge decision tag; its selected POI retains its own lifecycle.
    plan = analysis.trade_plan

    def _right_edge_band(low: float, high: float, color: str, label: str, alpha: float) -> None:
        bottom, top = min(low, high), max(low, high)
        ax.add_patch(Rectangle((n - 0.15, bottom), 0.7, top - bottom, color=color, alpha=alpha, zorder=5, linewidth=0))
        _label(n + 0.65, top, f" {label}", color, 8, "bold", va="bottom")

    if plan.selected_htf_poi is not None:
        htf_poi = plan.selected_htf_poi
        _right_edge_band(
            htf_poi.zone.low,
            htf_poi.zone.high,
            "#9467bd",
            f"HTF {htf_poi.timeframe} {htf_poi.state}",
            0.18,
        )
    if has_actionable_plan(plan):
        if not selected_drawn and plan.entry_low is not None and plan.entry_high is not None:
            _right_edge_band(plan.entry_low, plan.entry_high, "#3179f5", "Entry", 0.24)
        short = {"Execution SL": "Exec SL", "Structural invalidation": "Struct invalid"}
        for level in plan_levels(plan):
            color = "#d62728" if "invalid" in level.label.lower() or "sl" in level.label.lower() else "#2ca02c"
            ax.plot([n - 0.15, n + 0.55], [level.price, level.price], linestyle=":" if "Target" in level.label else "--",
                    color=color, linewidth=1.2, zorder=6)
            _label(n + 0.65, level.price, f" {short.get(level.label, level.label)}", color, 8, "bold")

    # current price reference (live decision anchor)
    last_px = float(c[-1])
    ax.axhline(last_px, color="#cfd2dc", linestyle=(0, (1, 2)), linewidth=0.8, alpha=0.55, zorder=5)
    _label(n + 0.65, last_px, f" {last_px:,.0f}", "#cfd2dc", 8, "bold")

    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks], color="#9598a1", fontsize=8)
    ax.tick_params(colors="#9598a1")
    for spine in ax.spines.values():
        spine.set_color("#2a2e39")
    ax.set_xlim(-1, n + 13)
    ax.set_title(title or f"{analysis.symbol} {analysis.timeframe} — SMC marked (high=labelled · medium=faint)",
                 color="#e0e0e0", fontsize=12, fontweight="bold")
    rr = f"  ·  R:R {plan.risk_reward:.1f}" if plan.risk_reward else ""
    ax.text(0.008, 0.985, f"bias {plan.direction}  ·  {plan.verdict}{rr}", transform=ax.transAxes,
            ha="left", va="top", color="#9598a1", fontsize=9, fontweight="bold")
    legend = ("BOS/CHoCH = structure break   ·   ▲▼ = liquidity sweep   ·   "
              "box = FVG / OB   ·   dashed = EQH/EQL liquidity   ·   shading = premium/discount")
    ax.text(0.5, -0.085, legend, transform=ax.transAxes, ha="center", va="top", color="#9598a1", fontsize=8)
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def render_raw_chart(df: pd.DataFrame, symbol: str, timeframe: str, output_path: str) -> None:
    """Render candles only for blind vision evaluation.

    The paired annotated chart is an explanation aid. A vision model must be
    evaluated on this raw image, otherwise it is simply reading the answer.
    """
    plot_df = df.copy().set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    fig, _axes = mpf.plot(
        plot_df,
        type="candle",
        style="yahoo",
        volume=True,
        returnfig=True,
        figsize=(16, 9),
        title=f"{symbol} {timeframe} Raw OHLCV",
        tight_layout=True,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def render_bias_comparison_chart(
    df: pd.DataFrame,
    analysis: AnalysisResult,
    output_path: str,
    user_direction: str | None = None,
    user_entry: float | None = None,
    user_stop: float | None = None,
    user_target: float | None = None,
) -> None:
    plot_df = df.copy()
    plot_df = plot_df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    fig, axes = mpf.plot(
        plot_df,
        type="candle",
        style="charles",
        volume=False,
        returnfig=True,
        figsize=(16, 9),
        title=f"{analysis.symbol} {analysis.timeframe} Bias Comparison",
        tight_layout=True,
    )
    price_ax = axes[0]

    plan = analysis.trade_plan
    decision_x = plot_df.index[-1]

    def decision_tag(price: float, label: str, color: str, marker: str = "_") -> None:
        price_ax.scatter(decision_x, price, marker=marker, color=color, s=120, linewidths=1.3, zorder=6)
        price_ax.annotate(label, xy=(decision_x, price), xytext=(5, 0), textcoords="offset points", color=color, fontsize=8, va="center")

    if has_actionable_plan(plan):
        if plan.entry_low is not None and plan.entry_high is not None:
            price_ax.vlines(decision_x, plan.entry_low, plan.entry_high, color="red", linewidth=4.0, alpha=0.8)
        for level in plan_levels(plan):
            decision_tag(level.price, f"Model {level.label}", "red")

    if user_entry is not None:
        decision_tag(user_entry, "User entry", "blue")
    if user_stop is not None:
        decision_tag(user_stop, "User stop", "blue")
    if user_target is not None:
        decision_tag(user_target, "User target", "blue")

    title = f"Model: {plan.direction}"
    if user_direction:
        title += f" | User: {user_direction}"
    price_ax.text(plot_df.index[-1], float(plot_df["high"].max()), title, fontsize=10, color="black")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def render_screenshot_review(image_path: str, analysis: AnalysisResult, output_path: str) -> None:
    image = Image.open(image_path)
    fig, axes = plt.subplots(1, 2, figsize=(16, 9), gridspec_kw={"width_ratios": [3, 2]})
    axes[0].imshow(image)
    axes[0].set_title("Source Screenshot")
    axes[0].axis("off")

    text_lines = [
        f"{analysis.symbol} {analysis.timeframe}",
        "",
        f"Direction: {analysis.trade_plan.direction}",
        f"Entry: {analysis.trade_plan.entry_low} - {analysis.trade_plan.entry_high}",
        f"Execution SL: {analysis.trade_plan.invalidation}",
        f"Structural invalidation: {analysis.trade_plan.structural_invalidation}",
        f"Stop quality: {analysis.trade_plan.stop_quality} ({analysis.trade_plan.stop_buffer_atr} ATR)",
        f"Targets: {', '.join(str(target) for target in analysis.trade_plan.targets) or 'N/A'}",
        "",
        "Thesis:",
        analysis.trade_plan.thesis,
        "",
        "Warnings:",
    ]
    if analysis.trade_plan.warnings:
        text_lines.extend(f"- {warning}" for warning in analysis.trade_plan.warnings)
    else:
        text_lines.append("- None")
    axes[1].axis("off")
    axes[1].text(0.0, 1.0, "\n".join(text_lines), va="top", wrap=True, fontsize=10, family="monospace")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
