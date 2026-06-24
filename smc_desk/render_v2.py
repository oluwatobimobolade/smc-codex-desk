import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle
from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.perception.ontology import Direction

def render_v2_snapshot(df: pd.DataFrame, snapshot: PerceptionSnapshot, output_path: str | None = None, title: str = "SMC Perception V2", scale: str = "15m"):
    """Render the exact ontological truth of the V2 perception engine."""
    import numpy as np

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    
    if n == 0:
        return

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.6)
    
    up, dn = "#26a69a", "#ef5350"
    body_floor = (float(h.max()) - float(l.min())) * 1e-3
    
    # 1. Draw Candlesticks
    for i in range(n):
        col = up if c[i] >= o[i] else dn
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
        lo_b, hi_b = min(o[i], c[i]), max(o[i], c[i])
        ax.add_patch(Rectangle((i - 0.34, lo_b), 0.68, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))

    # Helper function to find index by timestamp
    def _idx(ts_str: str) -> int:
        ts = pd.to_datetime(ts_str)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        idx = df.index[df['timestamp'] == ts]
        if len(idx) > 0:
            return idx[0]
        # fallback
        try:
            return df[df['timestamp'] >= ts].index[0]
        except IndexError:
            return n - 1
            
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

    # 2. Draw Swings
    if scale in snapshot.swings:
        for sw in snapshot.swings[scale]:
            ix = _idx(sw.pivot_time)
            price = float(sw.price_low if sw.direction == Direction.BULLISH else sw.price_high)
            color = up if sw.direction == Direction.BULLISH else dn
            marker = "^" if sw.direction == Direction.BULLISH else "v"
            # Thicker for external
            s = 40 if sw.evidence.is_external else 15
            alpha = 0.8 if sw.evidence.is_external else 0.4
            ax.scatter([ix], [price], s=s, color=color, marker=marker, zorder=4, alpha=alpha)

    # 3. Draw FVGs
    for fvg in snapshot.fvgs:
        ix = _idx(fvg.pivot_time)
        col = up if fvg.direction == Direction.BULLISH else dn
        low, high = float(fvg.price_low), float(fvg.price_high)
        ax.add_patch(Rectangle((ix, low), (n - 1) - ix, high - low, color=col, alpha=0.15, zorder=1, linewidth=0))
        _label(ix, high, " FVG", col, 8, "normal", va="bottom")

    # 4. Draw Structure Breaks
    for brk in snapshot.structure_breaks:
        ix_cand = _idx(brk.candidate_at)
        level = float(brk.evidence.broken_price)
        col = up if brk.direction == Direction.BULLISH else dn
        
        # Draw line from broken level
        label_text = f"{brk.break_type}"
        if not brk.confirmed_at:
            label_text += " (PROBE)"
            ls = ":"
            end_ix = n - 1
        else:
            ls = "-"
            end_ix = _idx(brk.confirmed_at)
            
        ax.plot([ix_cand - 5, end_ix], [level, level], color=col, linestyle=ls, linewidth=1.5, zorder=5)
        _label(ix_cand, level, f" {label_text}", col, 9, "bold")

    ax.set_title(title, color="#ececec", fontsize=11, loc="left", pad=12)
    ax.set_xlim(-1, n)
    ax.margins(y=0.1)
    ax.axis("off")
    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=120, bbox_inches="tight", facecolor="#0e1117")
        plt.close(fig)
        return None
    return fig, ax

def render_raw_chart(df: pd.DataFrame, output_path: str, title: str = "Raw Chart") -> None:
    """Render the raw candlesticks with no annotations."""
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    
    if n == 0:
        return

    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.6)
    
    up, dn = "#26a69a", "#ef5350"
    body_floor = (float(h.max()) - float(l.min())) * 1e-3
    
    for i in range(n):
        col = up if c[i] >= o[i] else dn
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.7, zorder=2)
        lo_b, hi_b = min(o[i], c[i]), max(o[i], c[i])
        ax.add_patch(Rectangle((i - 0.34, lo_b), 0.68, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))

    ax.set_title(title, color="#ececec", fontsize=11, loc="left", pad=12)
    ax.set_xlim(-1, n)
    ax.margins(y=0.1)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight", facecolor="#0e1117")
    plt.close(fig)
