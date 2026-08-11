"""Clean multi-timeframe chart pack renderer.

These charts are evidence inputs for review and AI reasoning. They intentionally
contain candles only: no detector labels, no trade boxes, no entry/SL/TP.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle


DEFAULT_TIMEFRAMES = ("1d", "4h", "1h", "15m")
DISPLAY_WINDOW_BARS = {"1d": 180, "4h": 180, "1h": 240, "15m": 320, "5m": 360}


def render_clean_mtf_chart_pack(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    output_dir: str | Path,
    *,
    symbol: str,
    include_5m: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = list(DEFAULT_TIMEFRAMES)
    if include_5m:
        expected.append("5m")
    chart_paths: dict[str, str] = {}
    source_rows: dict[str, int] = {}
    displayed_rows: dict[str, int] = {}
    missing: list[str] = []
    for timeframe in expected:
        df = timeframe_dfs.get(timeframe)
        if df is None:
            missing.append(timeframe)
            continue
        path = output_dir / f"{symbol}_{timeframe}_clean.png"
        source_rows[timeframe] = len(df)
        display_limit = DISPLAY_WINDOW_BARS.get(timeframe)
        displayed_rows[timeframe] = min(len(df), display_limit) if display_limit else len(df)
        render_clean_candle_chart(
            df,
            path,
            symbol=symbol,
            timeframe=timeframe,
            max_display_bars=display_limit,
        )
        chart_paths[timeframe] = str(path)
    return {
        "schema": "clean_mtf_chart_pack_v1",
        "symbol": symbol,
        "chart_authority": "clean_candles_only",
        "contains_engine_labels": False,
        "contains_trade_box": False,
        "timeframes_requested": expected,
        "chart_paths": chart_paths,
        "source_rows": source_rows,
        "displayed_rows": displayed_rows,
        "missing_timeframes": missing,
    }


def render_clean_candle_chart(
    df: pd.DataFrame,
    output_path: str | Path,
    *,
    symbol: str,
    timeframe: str,
    max_display_bars: int | None = None,
) -> None:
    if df.empty:
        raise ValueError("Cannot render a clean chart from an empty dataframe.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = _normalize_df(df)
    source_rows = len(df)
    if max_display_bars is not None and max_display_bars > 0:
        df = df.tail(max_display_bars).reset_index(drop=True)
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    low = float(l.min())
    high = float(h.max())
    span = max(high - low, abs(high) * 0.01, 1e-9)

    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    ax.grid(color="#2a2e39", linewidth=0.5, alpha=0.55)
    body_floor = span * 1e-3
    for index in range(n):
        color = "#26a69a" if c[index] >= o[index] else "#ef5350"
        ax.plot([index, index], [l[index], h[index]], color=color, linewidth=0.7, zorder=2)
        ax.add_patch(
            Rectangle(
                (index - 0.34, min(o[index], c[index])),
                0.68,
                max(abs(c[index] - o[index]), body_floor),
                color=color,
                zorder=3,
                linewidth=0,
            )
        )
    ax.set_title(
        (
            f"{symbol} {timeframe} clean candles ({n} shown / {source_rows} source)"
            if n != source_rows
            else f"{symbol} {timeframe} clean candles ({n} candles)"
        ),
        color="#e0e0e0",
        fontsize=12,
        fontweight="bold",
        loc="left",
    )
    ax.text(
        0.01,
        0.015,
        "CLEAN EVIDENCE CHART - NO ENGINE LABELS - NO TRADE BOX",
        transform=ax.transAxes,
        color="#aab0be",
        fontsize=8,
        fontweight="bold",
        ha="left",
        va="bottom",
    )
    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks], color="#9598a1", fontsize=8)
    ax.tick_params(colors="#9598a1")
    for spine in ax.spines.values():
        spine.set_color("#2a2e39")
    ax.set_xlim(-1, n)
    ax.set_ylim(low - span * 0.08, high + span * 0.10)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={"index": "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out.sort_values("timestamp").reset_index(drop=True)
