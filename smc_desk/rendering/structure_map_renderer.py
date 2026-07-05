"""Sparse structure map renderer for the formal MTF structure graph.

This renders a clean, minimal chart that shows ONLY what the formal
structure graph certifies: parent-range shading, external vs internal
structure breaks, certified liquidity, and no trade boxes. No AI
interpretation, no detector firehose, no unconfirmed probes.

The output is visual proof that the graph's invariants are grounded
in actual candle structure.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


def render_structure_map(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    graph: Mapping[str, Any],
    output_path: Path,
    *,
    symbol: str = "",
) -> None:
    entry_tf = "15m"
    df = timeframe_dfs.get(entry_tf)
    if df is None or df.empty:
        entry_tf = next(iter(timeframe_dfs))
        df = timeframe_dfs.get(entry_tf)
    if df is None or df.empty:
        return

    df = _normalize(df)
    o, h, l, c = df["open"].to_numpy(float), df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    n = len(df)
    low, high = float(l.min()), float(h.max())
    span = max(high - low, abs(high) * 0.01, 1e-9)

    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.4)

    # Candles
    body_floor = span * 1e-3
    for i in range(n):
        color = "#26a69a" if c[i] >= o[i] else "#ef5350"
        ax.plot([i, i], [l[i], h[i]], color=color, linewidth=0.5, zorder=2, alpha=0.7)
        ax.add_patch(mpatches.Rectangle(
            (i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), body_floor),
            color=color, zorder=3, linewidth=0, alpha=0.7))

    # Active range shading (gray parent context rectangle)
    ar = graph.get("active_range") or {}
    if ar.get("status") == "RESOLVED" and ar.get("high") and ar.get("low"):
        ax.axhspan(float(ar["low"]), float(ar["high"]), facecolor="#3a3e4a", alpha=0.18, zorder=1)
        ax.axhline(float(ar["high"]), color="#5a5e6a", linewidth=0.8, linestyle="--", zorder=4)
        ax.axhline(float(ar["low"]), color="#5a5e6a", linewidth=0.8, linestyle="--", zorder=4)
        eq = ar.get("equilibrium")
        if eq:
            ax.axhline(float(eq), color="#5a5e6a", linewidth=0.5, linestyle=":", zorder=4)

    # Structure breaks
    tf_nodes = graph.get("timeframes") or {}
    for tf, node in tf_nodes.items():
        if not isinstance(node, Mapping):
            continue
        _render_structure_breaks(ax, df, node, tf, n)

    # Parent-child context status
    pc = graph.get("parent_child_context") or {}
    pc_text = pc.get("thesis_sentence", "")
    if pc.get("has_conflict"):
        ax.text(0.5, 1.014, f"MIXED: {pc_text[:120]}",
                transform=ax.transAxes, color="#f0b062", fontsize=8, fontweight="bold",
                ha="center", va="bottom", zorder=10)

    # Invariant status
    inv = graph.get("invariants") or {}
    inv_status = inv.get("status", "NOT_COMPUTED")
    inv_color = "#26a69a" if inv_status == "PASS" else "#f0b062" if inv_status == "REVIEW_REQUIRED" else "#ef5350"
    ax.text(0.99, 1.014, f"GRAPH INVARIANTS: {inv_status}",
            transform=ax.transAxes, color=inv_color, fontsize=8, fontweight="bold",
            ha="right", va="bottom", zorder=10)

    ax.set_title(f"{symbol} {entry_tf} Formal Structure Map ({n} candles)",
                 color="#e0e0e0", fontsize=11, fontweight="bold", loc="left")
    ax.text(0.01, 0.015, "FORMAL STRUCTURE MAP — NO AI INTERPRETATION — NO TRADE BOX",
            transform=ax.transAxes, color="#9598a1", fontsize=7, ha="left", va="bottom")

    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks],
                       color="#9598a1", fontsize=7)
    ax.tick_params(colors="#9598a1")
    for spine in ax.spines.values():
        spine.set_color("#2a2e39")
    ax.set_xlim(-1, n)
    ax.set_ylim(low - span * 0.10, high + span * 0.14)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


def _render_structure_breaks(ax, df: pd.DataFrame, node: Mapping[str, Any], timeframe: str, total_bars: int) -> None:
    ext = node.get("latest_external_break")
    if isinstance(ext, Mapping):
        price = ext.get("broken_price")
        if price is not None:
            color = "#26a69a" if ext.get("direction") == "bullish" else "#ef5350"
            label = f"{timeframe} {ext.get('break_type', '')} {'EXT' if ext.get('scope') == 'external' else ''} {float(price):.1f}"
            ax.axhline(float(price), color=color, linewidth=1.2, linestyle="-", alpha=0.9, zorder=5)
            ax.text(total_bars - 1, float(price), label, color=color, fontsize=6, ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="#0e1117", edgecolor=color, alpha=0.7), zorder=6)

    internal = node.get("latest_internal_break")
    if isinstance(internal, Mapping):
        price = internal.get("broken_price")
        if price is not None:
            color = "#26a69a" if internal.get("direction") == "bullish" else "#ef5350"
            label = f"{timeframe} {internal.get('break_type', '')} INT {float(price):.1f}"
            ax.axhline(float(price), color=color, linewidth=0.6, linestyle="--", alpha=0.6, zorder=5)
            ax.text(total_bars - 1, float(price), label, color=color, fontsize=5, ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.1", facecolor="#0e1117", edgecolor=color, alpha=0.5), zorder=6)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().tail(300)
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={"index": "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out.sort_values("timestamp").reset_index(drop=True)
