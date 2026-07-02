"""Trade-plan chart renderer.

The renderer is intentionally strict: it refuses to draw entry/stop/target
boxes unless the final SMC narrative authority explicitly marks the trade plan
as ready. This prevents watch states from becoming fake trade calls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle


def render_trade_plan_chart(
    df: pd.DataFrame,
    narrative_authority: Mapping[str, Any],
    output_path: str | Path,
    *,
    timeframe: str = "15m",
) -> None:
    if narrative_authority.get("official_trade_plan_state") != "TRADE_PLAN_READY" or not narrative_authority.get("show_trade_box"):
        raise ValueError("Trade-plan chart requested before TRADE_PLAN_READY.")
    entry = _float(narrative_authority.get("entry"))
    stop = _float(narrative_authority.get("stop_loss"))
    take_profit = [_float(item.get("price") if isinstance(item, Mapping) else item) for item in narrative_authority.get("take_profit", []) or []]
    take_profit = [item for item in take_profit if item is not None]
    if df.empty or entry is None or stop is None or not take_profit:
        raise ValueError("Trade-plan chart requires dataframe, entry, stop_loss, and take_profit.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = df.reset_index(drop=True).copy()
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    low = min(float(l.min()), stop, entry, *take_profit)
    high = max(float(h.max()), stop, entry, *take_profit)
    span = max(high - low, 1.0)

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.62)
    up, dn = "#26a69a", "#ef5350"
    body_floor = span * 1e-3
    for i in range(n):
        col = up if c[i] >= o[i] else dn
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
        ax.add_patch(Rectangle((i - 0.34, min(o[i], c[i])), 0.68, max(abs(c[i] - o[i]), body_floor), color=col, zorder=3, linewidth=0))

    ax.axhline(entry, color="#fdd835", linewidth=1.2, label="Entry")
    ax.axhline(stop, color="#ef5350", linewidth=1.2, label="Stop loss")
    for index, target in enumerate(take_profit, start=1):
        ax.axhline(target, color="#81c784", linestyle=(0, (2, 3)), linewidth=1.1)
        ax.text(n + 0.7, target, f" TP{index}", color="#81c784", fontsize=8, fontweight="bold", va="center")
    ax.text(n + 0.7, entry, " ENTRY", color="#fdd835", fontsize=8, fontweight="bold", va="center")
    ax.text(n + 0.7, stop, " SL", color="#ef5350", fontsize=8, fontweight="bold", va="center")
    ax.set_title(f"{narrative_authority.get('symbol')} {timeframe} - TRADE PLAN READY", color="#e0e0e0", fontsize=12, fontweight="bold", loc="left")
    ax.set_xlim(-1, n + 16)
    ax.set_ylim(low - span * 0.12, high + span * 0.12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
