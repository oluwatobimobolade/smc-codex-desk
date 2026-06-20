from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
from PIL import Image

from .models import AnalysisResult


ZONE_COLORS = {
    ("fvg", "bullish"): "#2ca02c",
    ("fvg", "bearish"): "#d62728",
    ("order_block", "bullish"): "#17becf",
    ("order_block", "bearish"): "#ff7f0e",
    ("liquidity", "bullish"): "#1f77b4",
    ("liquidity", "bearish"): "#9467bd",
}


def _segment(index: pd.DatetimeIndex, start: int | None, end: int | None) -> pd.DatetimeIndex:
    if len(index) == 0:
        return index
    left = max(start or 0, 0)
    right = min(end if end is not None else len(index) - 1, len(index) - 1)
    return index[left : right + 1]


def render_annotated_chart(df: pd.DataFrame, analysis: AnalysisResult, output_path: str) -> None:
    plot_df = df.copy()
    plot_df = plot_df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    fig, axes = mpf.plot(
        plot_df,
        type="candle",
        style="yahoo",
        volume=True,
        returnfig=True,
        figsize=(16, 9),
        title=(
            f"{analysis.symbol} {analysis.timeframe} SMC Analysis | "
            f"{analysis.trade_plan.verdict} Grade {analysis.trade_plan.setup_grade}"
        ),
        tight_layout=True,
    )
    price_ax = axes[0]

    for zone in analysis.zones:
        color = ZONE_COLORS.get((zone.kind, zone.direction), "#7f7f7f")
        segment = _segment(plot_df.index, zone.start_index, zone.end_index)
        if len(segment) >= 2:
            price_ax.fill_between(segment, zone.low, zone.high, alpha=0.10, color=color)
            anchor = segment[-1]
        else:
            anchor = plot_df.index[min(zone.end_index or len(plot_df.index) - 1, len(plot_df.index) - 1)]
            price_ax.axhspan(zone.low, zone.high, alpha=0.08, color=color)
        suffix = f" {zone.status}" if zone.status != "unknown" else ""
        price_ax.text(anchor, zone.high, f"{zone.label}{suffix} ({zone.score:.2f})", fontsize=8, color=color)

    for event in analysis.events:
        timestamp = pd.to_datetime(event.timestamp)
        marker = "^" if event.direction == "bullish" else "v"
        color = "#006400" if event.direction == "bullish" else "#8b0000"
        price_ax.scatter(timestamp, event.price, marker=marker, color=color, s=35)
        if event.label == "Liquidity Sweep":
            label = f"Sweep {event.direction}"
        else:
            label = f"{event.label} {event.direction} {event.displacement_score:.1f}x"
        price_ax.text(timestamp, event.price, label, fontsize=8, color=color)

    plan = analysis.trade_plan
    if plan.entry_low is not None and plan.entry_high is not None:
        price_ax.axhspan(plan.entry_low, plan.entry_high, alpha=0.14, color="#1f77b4")
        price_ax.text(plot_df.index[-1], plan.entry_high, f"POI / Entry {plan.entry_type}", fontsize=8, color="#1f77b4")
    if plan.invalidation is not None:
        price_ax.axhline(plan.invalidation, linestyle="--", color="#d62728", linewidth=1.2)
    if plan.structural_invalidation is not None and plan.structural_invalidation != plan.invalidation:
        price_ax.axhline(plan.structural_invalidation, linestyle=":", color="#9467bd", linewidth=1.0)
    for target in plan.targets:
        price_ax.axhline(target, linestyle=":", color="#2ca02c", linewidth=1.1)

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
    if plan.entry_low is not None and plan.entry_high is not None:
        price_ax.axhspan(plan.entry_low, plan.entry_high, alpha=0.12, color="red")
    if plan.invalidation is not None:
        price_ax.axhline(plan.invalidation, linestyle="--", color="red", linewidth=1.2)
    if plan.structural_invalidation is not None and plan.structural_invalidation != plan.invalidation:
        price_ax.axhline(plan.structural_invalidation, linestyle=":", color="#9467bd", linewidth=1.0)
    if plan.targets:
        price_ax.axhline(plan.targets[0], linestyle=":", color="red", linewidth=1.2)

    if user_entry is not None:
        price_ax.axhline(user_entry, linestyle="-", color="blue", linewidth=1.2)
    if user_stop is not None:
        price_ax.axhline(user_stop, linestyle="--", color="blue", linewidth=1.2)
    if user_target is not None:
        price_ax.axhline(user_target, linestyle=":", color="blue", linewidth=1.2)

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
