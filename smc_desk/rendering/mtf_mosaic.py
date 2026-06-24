import matplotlib.pyplot as plt
import pandas as pd
from typing import Dict, Any, Optional

def render_mtf_mosaic(
    timeframe_dfs: Dict[str, pd.DataFrame],
    timeframe_snapshots: Dict[str, Any],
    output_path: str,
    title: str = "MTF Mosaic View"
) -> None:
    """
    Renders a 2x2 grid of different timeframes for multi-timeframe analysis.
    Supported timeframes are typically: 15m, 1h, 4h, 1d.
    """
    timeframes = ["15m", "1h", "4h", "1d"]
    fig, axes = plt.subplots(2, 2, figsize=(20, 10))
    fig.patch.set_facecolor("#0e1117")
    
    # Flatten axes
    axes = axes.flatten()
    
    for i, tf in enumerate(timeframes):
        ax = axes[i]
        ax.set_facecolor("#0e1117")
        ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.6)
        
        df = timeframe_dfs.get(tf)
        if df is None or len(df) == 0:
            ax.text(0.5, 0.5, f"No Data for {tf}", color="gray", ha="center", va="center")
            continue
            
        # Draw basic candlesticks for the timeframe
        o = df["open"].to_numpy(float)
        h = df["high"].to_numpy(float)
        l = df["low"].to_numpy(float)
        c = df["close"].to_numpy(float)
        n = len(df)
        
        up, dn = "#26a69a", "#ef5350"
        body_floor = (float(h.max()) - float(l.min())) * 1e-3
        from matplotlib.patches import Rectangle
        
        # Display at most 100 bars for clarity in MTF grid
        display_n = min(100, n)
        start_idx = n - display_n
        
        for idx in range(start_idx, n):
            plot_idx = idx - start_idx
            col = up if c[idx] >= o[idx] else dn
            ax.plot([plot_idx, plot_idx], [l[idx], h[idx]], color=col, linewidth=0.8, zorder=2)
            lo_b, hi_b = min(o[idx], c[idx]), max(o[idx], c[idx])
            ax.add_patch(Rectangle((plot_idx - 0.3, lo_b), 0.6, max(hi_b - lo_b, body_floor), color=col, zorder=3, linewidth=0))
            
        ax.set_title(f"{tf} Timeframe", color="#ececec", fontsize=10, loc="left")
        ax.set_xlim(-1, display_n)
        ax.margins(y=0.1)
        ax.axis("off")
        
    plt.suptitle(title, color="#ececec", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight", facecolor="#0e1117")
    plt.close(fig)
