#!/usr/bin/env python3
"""Generate multi-timeframe SMC evidence chart packs from a backtest run.

Each chart recreates the Daily / 4H / 1H context plus the 15m execution
window for a trade or near miss. HTF panels use only candles fully closed
at the decision time. The 15m panel may show outcome candles after the
decision, but its SMC annotations are calculated only from data visible at
the decision time.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import StrMethodFormatter

from smc_desk.engine import (
    detect_equal_levels,
    detect_fvgs,
    detect_liquidity_sweeps,
    detect_order_blocks,
    detect_structure_events,
    detect_swings,
    load_ohlcv_csv,
)
from smc_desk.mtf import build_mtf_snapshot, precompute_htf_series, slice_precomputed_htf, snapshot_to_dict
from smc_desk.rules import load_rule_config
from smc_desk.visual_geometry import select_display_events, structure_origin_index, zone_lifecycle


PANEL_SPECS = [
    ("1d", "Daily", 35),
    ("4h", "4H", 60),
    ("1h", "1H", 90),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate annotated MTF charts from a backtest run.")
    parser.add_argument("--run-dir", required=True, help="Backtest run folder containing trades.csv and near_misses.json.")
    parser.add_argument("--ohlcv", required=True, help="15m OHLCV CSV used for the backtest.")
    parser.add_argument("--max-near-misses", type=int, default=3, help="How many top near misses to chart.")
    parser.add_argument("--max-trades", type=int, default=10, help="Max trade candidates to chart.")
    return parser.parse_args()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _timestamp_or_none(value: Any) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    try:
        return pd.Timestamp(value)
    except (TypeError, ValueError):
        return None


def _safe_name(value: Any) -> str:
    text = str(value or "unknown")
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _dedupe_legend(ax: plt.Axes) -> None:
    handles, labels = ax.get_legend_handles_labels()
    seen: set[str] = set()
    clean_handles = []
    clean_labels = []
    for handle, label in zip(handles, labels):
        if not label or label.startswith("_") or label in seen:
            continue
        seen.add(label)
        clean_handles.append(handle)
        clean_labels.append(label)
    if clean_handles:
        ax.legend(clean_handles, clean_labels, fontsize=6, loc="best", framealpha=0.85)


def _set_date_locator(ax: plt.Axes, span_days: float) -> None:
    if span_days >= 6:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, int(span_days / 7))))
    elif span_days >= 1:
        span_hours = span_days * 24
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(span_hours / 6))))
    else:
        span_minutes = max(span_days * 24 * 60, 15)
        interval = max(15, int(span_minutes / 6 / 15) * 15)
        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))


def plot_ohlcv(ax: plt.Axes, df_slice: pd.DataFrame, title: str, reference_time: pd.Timestamp | None = None) -> None:
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.grid(True, alpha=0.18, linewidth=0.6)
    ax.tick_params(axis="x", labelsize=7, rotation=30)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_ylabel("Price", fontsize=8)

    if df_slice.empty:
        ax.text(0.5, 0.5, "No closed candles visible", transform=ax.transAxes, ha="center", va="center", fontsize=9)
        return

    ts = pd.to_datetime(df_slice["timestamp"], utc=False)
    xs = mdates.date2num(ts)
    if len(xs) > 1:
        width = float(pd.Series(xs).diff().dropna().median()) * 0.62
    else:
        width = 0.02

    y_min = float(df_slice["low"].min())
    y_max = float(df_slice["high"].max())
    body_floor = max((y_max - y_min) * 0.0015, 0.01)

    for x, row in zip(xs, df_slice.itertuples(index=False)):
        o = float(row.open)
        h = float(row.high)
        l = float(row.low)
        c = float(row.close)
        color = "#089981" if c >= o else "#f23645"
        ax.vlines(x, l, h, color=color, linewidth=0.8, alpha=0.95)
        bottom = min(o, c)
        height = max(abs(c - o), body_floor)
        rect = Rectangle((x - width / 2, bottom), width, height, facecolor=color, edgecolor=color, linewidth=0.6)
        ax.add_patch(rect)

    left = xs[0]
    right_candidates = [xs[-1]]
    if reference_time is not None:
        right_candidates.append(mdates.date2num(reference_time))
    right = max(right_candidates)
    pad = max((right - left) * 0.025, width * 2)
    ax.set_xlim(left - pad, right + pad)
    _set_date_locator(ax, right - left)
    y_pad = max((y_max - y_min) * 0.08, 1.0)
    ax.set_ylim(y_min - y_pad, y_max + y_pad)


def annotate_smc(ax: plt.Axes, df_slice: pd.DataFrame, cfg: Any, visible_until: pd.Timestamp | None = None) -> None:
    if df_slice.empty:
        return

    working = df_slice.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=False)
    if visible_until is not None:
        working = working.loc[working["timestamp"] <= visible_until].copy()
    working = working.reset_index(drop=True)
    if len(working) < max(8, cfg.pivot_window * 2 + 1):
        return

    ts = pd.to_datetime(working["timestamp"], utc=False)
    swings = detect_swings(working, cfg)
    zones = detect_equal_levels(swings, cfg) + detect_fvgs(working, cfg)
    events = detect_structure_events(working, swings, cfg) + detect_liquidity_sweeps(working, swings, cfg)
    order_blocks = detect_order_blocks(working, [event for event in events if event.label in {"BOS", "CHoCH"}], cfg)

    for zone in (zones + order_blocks)[-16:]:
        color = "#089981" if zone.direction == "bullish" else "#f23645"
        lifecycle = zone_lifecycle(working, zone, events)
        if not lifecycle.is_active:
            continue
        start = lifecycle.activation_index
        end = lifecycle.end_index
        if zone.kind in {"fvg", "order_block"}:
            ax.fill_between(ts.iloc[start : end + 1], zone.low, zone.high, alpha=0.10, color=color)
        elif zone.kind == "liquidity":
            level = zone.high if zone.direction == "bearish" else zone.low
            ax.plot([ts.iloc[start], ts.iloc[end]], [level, level], color="#9467bd", linestyle="--", linewidth=0.8)

    for swing in swings[-14:]:
        if 0 <= swing.index < len(working):
            marker = "v" if swing.kind == "high" else "^"
            color = "#2962ff" if swing.kind == "high" else "#ff9800"
            ax.scatter(ts.iloc[swing.index], swing.price, marker=marker, color=color, s=18, zorder=5, alpha=0.75)

    for event in select_display_events(events)[-18:]:
        if 0 <= event.index < len(working):
            t = ts.iloc[event.index]
            if event.label == "CHoCH":
                ax.scatter(t, event.price, marker="D", color="#2962ff", s=36, zorder=6, label="CHoCH")
            elif event.label == "BOS":
                color = "#089981" if event.direction == "bullish" else "#f23645"
                ax.scatter(t, event.price, marker="s", color=color, s=32, zorder=6, label="BOS")
            elif event.label == "Liquidity Sweep":
                ax.scatter(t, event.price, marker="*", color="#f6c343", edgecolors="#111111", linewidth=0.4, s=58, zorder=6, label="Sweep")
            if event.label in {"BOS", "CHoCH"} and event.broken_level is not None:
                origin = structure_origin_index(event, swings, working)
                if origin is not None:
                    ax.plot([ts.iloc[origin], t], [event.broken_level, event.broken_level], color="#2962ff" if event.direction == "bullish" else "#f23645", linestyle="--", linewidth=0.8)


def mark_vertical(ax: plt.Axes, when: pd.Timestamp | None, label: str, color: str) -> None:
    if when is None:
        return
    ax.axvline(x=when, color=color, linestyle=":", linewidth=1.05, alpha=0.9, label=label)


def overlay_plan_levels(ax: plt.Axes, row: dict[str, Any], decision_time: pd.Timestamp) -> None:
    entry_low = _float_or_none(row.get("entry_low"))
    entry_high = _float_or_none(row.get("entry_high"))
    stop = _float_or_none(row.get("invalidation"))
    target = _float_or_none(row.get("target"))
    htf_low = _float_or_none(row.get("htf_poi_low"))
    htf_high = _float_or_none(row.get("htf_poi_high"))
    htf_tf = str(row.get("htf_poi_timeframe") or "")
    htf_state = str(row.get("htf_poi_state") or "")

    verdict = str(row.get("verdict") or "")
    actionable = verdict in {"Execute", "Watch", "Watch Retrace"} and entry_low is not None and entry_high is not None
    if actionable:
        ax.vlines(decision_time, min(entry_low, entry_high), max(entry_low, entry_high), color="#2962ff", linewidth=4.0, alpha=0.85, label="Entry zone")
        if stop is not None:
            ax.scatter(decision_time, stop, marker="_", color="#f23645", s=110, linewidths=1.3, label="Stop")
        if target is not None:
            ax.scatter(decision_time, target, marker="_", color="#089981", s=110, linewidths=1.3, label="Target")
    if htf_low is not None and htf_high is not None:
        ax.vlines(decision_time, min(htf_low, htf_high), max(htf_low, htf_high), color="#9467bd", linewidth=3.0, alpha=0.7, label="HTF POI")
        ax.annotate(f"HTF {htf_tf} {htf_state}", xy=(decision_time, max(htf_low, htf_high)), xytext=(4, 4), textcoords="offset points", fontsize=8, color="#9467bd")


def _decision_index_for_time(df: pd.DataFrame, decision_time: pd.Timestamp) -> int | None:
    timestamps = pd.to_datetime(df["timestamp"], utc=False)
    matches = df.index[timestamps == decision_time]
    if len(matches):
        return int(matches[0])
    return None


def _htf_panel_data(precomputed: dict[str, pd.DataFrame], tf: str, decision_time: pd.Timestamp, bars: int) -> pd.DataFrame:
    return slice_precomputed_htf(precomputed[tf], tf, decision_time).tail(bars).reset_index(drop=True)


def _snapshot_caption(df: pd.DataFrame, cfg: Any, precomputed: dict[str, pd.DataFrame], decision_time: pd.Timestamp) -> str:
    snapshot = snapshot_to_dict(build_mtf_snapshot(df, decision_time, cfg, precomputed=precomputed))
    return (
        "HTF context at decision: "
        f"1H={snapshot['1h']['bias']} | 4H={snapshot['4h']['bias']} | 1D={snapshot['1d']['bias']} | "
        f"alignment={snapshot['alignment']} ({snapshot['agreement_ratio']:.2f})"
    )


def _render_pack(
    *,
    chart_path: Path,
    df: pd.DataFrame,
    precomputed: dict[str, pd.DataFrame],
    cfg: Any,
    decision_time: pd.Timestamp,
    execution_slice: pd.DataFrame,
    title: str,
    subtitle: str,
    plan_row: dict[str, Any],
    signal_time: pd.Timestamp | None = None,
    entry_time: pd.Timestamp | None = None,
    exit_time: pd.Timestamp | None = None,
    note: str | None = None,
) -> None:
    fig, axes = plt.subplots(
        4,
        1,
        figsize=(18, 13.5),
        gridspec_kw={"height_ratios": [1.0, 1.0, 1.0, 1.45]},
        constrained_layout=False,
    )
    fig.patch.set_facecolor("white")
    fig.suptitle(title, fontsize=14, fontweight="bold", x=0.01, y=0.992, ha="left")
    fig.text(0.01, 0.965, subtitle, fontsize=9, ha="left")
    fig.text(0.01, 0.946, _snapshot_caption(df, cfg, precomputed, decision_time), fontsize=9, ha="left")

    for ax, (tf, label, bars) in zip(axes[:3], PANEL_SPECS):
        panel_df = _htf_panel_data(precomputed, tf, decision_time, bars)
        plot_ohlcv(ax, panel_df, f"{label} context - closed candles only", reference_time=decision_time)
        annotate_smc(ax, panel_df, cfg)
        mark_vertical(ax, decision_time, "Decision", "#ff9800")
        _dedupe_legend(ax)

    exec_title = "15m execution - annotations use candles visible at decision"
    plot_ohlcv(axes[3], execution_slice, exec_title, reference_time=decision_time)
    annotate_smc(axes[3], execution_slice, cfg, visible_until=decision_time)
    overlay_plan_levels(axes[3], plan_row, decision_time)
    mark_vertical(axes[3], signal_time or decision_time, "Signal", "#ff9800")
    mark_vertical(axes[3], entry_time, "Entry", "#2962ff")
    mark_vertical(axes[3], exit_time, "Exit", "#089981")
    if note:
        axes[3].text(
            0.01,
            0.98,
            note,
            transform=axes[3].transAxes,
            fontsize=8,
            va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8d8", edgecolor="#d8bd51", alpha=0.92),
        )
    _dedupe_legend(axes[3])

    fig.text(
        0.01,
        0.012,
        "Evidence rule: HTF panels include only fully closed candles at decision time; 15m outcome candles may be shown for replay review.",
        fontsize=8,
        ha="left",
        color="#555555",
    )
    plt.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _trade_execution_slice(df: pd.DataFrame, trade: dict[str, str], summary: dict[str, Any]) -> pd.DataFrame:
    signal_index = _int_or_none(trade.get("signal_index")) or 0
    entry_index = _int_or_none(trade.get("entry_index"))
    exit_index = _int_or_none(trade.get("exit_index"))
    entry_wait = int(summary.get("entry_wait_bars") or 24)
    end_index = exit_index if exit_index is not None else min(len(df) - 1, signal_index + max(entry_wait + 16, 48))
    start_index = max(0, signal_index - 90)
    return df.iloc[start_index : min(len(df), end_index + 8)].reset_index(drop=True)


def _near_miss_execution_slice(df: pd.DataFrame, decision_index: int) -> pd.DataFrame:
    start_index = max(0, decision_index - 90)
    end_index = min(len(df), decision_index + 32)
    return df.iloc[start_index:end_index].reset_index(drop=True)


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir)
    trades_file = run_dir / "trades.csv"
    decisions_file = run_dir / "decisions.csv"
    near_misses_file = run_dir / "near_misses.json"
    charts_dir = run_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_rule_config()
    df = load_ohlcv_csv(args.ohlcv)
    precomputed = precompute_htf_series(df)
    summary = _load_json(run_dir / "summary.json", {})
    trades = [row for row in _load_csv_rows(trades_file) if row.get("signal_index")]
    decision_rows = {
        int(row["decision_index"]): row
        for row in _load_csv_rows(decisions_file)
        if row.get("decision_index")
    }
    near_misses = _load_json(near_misses_file, [])
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir.resolve()),
        "ohlcv": str(Path(args.ohlcv).resolve()),
        "annotation_rule": "HTF panels use close_time <= decision_time; 15m annotations use candles <= decision_time.",
        "charts": [],
    }

    for i, trade in enumerate(trades[: args.max_trades], start=1):
        signal_index = _int_or_none(trade.get("signal_index"))
        if signal_index is None or signal_index >= len(df):
            continue
        signal_time = _timestamp_or_none(trade.get("signal_time")) or pd.Timestamp(df.at[signal_index, "timestamp"])
        entry_time = _timestamp_or_none(trade.get("entry_time"))
        exit_time = _timestamp_or_none(trade.get("exit_time"))
        outcome = trade.get("outcome") or "candidate"
        r_multiple = trade.get("r_multiple") or "0"
        title = (
            f"{summary.get('symbol', 'BTCUSD')} MTF evidence - trade {i:02d} - "
            f"{trade.get('direction', '?')} {outcome} {r_multiple}R"
        )
        subtitle = (
            f"Signal {signal_time} | verdict={trade.get('verdict', '?')} | "
            f"grade={trade.get('setup_grade', '?')} | conf={trade.get('confluence_score', '?')}"
        )
        note = trade.get("notes") or None
        chart_path = charts_dir / f"trade_{i:02d}_mtf_{_safe_name(outcome)}_{_safe_name(r_multiple)}R.png"
        _render_pack(
            chart_path=chart_path,
            df=df,
            precomputed=precomputed,
            cfg=cfg,
            decision_time=signal_time,
            execution_slice=_trade_execution_slice(df, trade, summary),
            title=title,
            subtitle=subtitle,
            plan_row=trade,
            signal_time=signal_time,
            entry_time=entry_time,
            exit_time=exit_time,
            note=note,
        )
        manifest["charts"].append(
            {
                "type": "trade",
                "path": str(chart_path.resolve()),
                "signal_time": signal_time.isoformat(),
                "outcome": outcome,
                "r_multiple": r_multiple,
            }
        )
        print(f"  {chart_path.name}")

    for i, near_miss in enumerate(near_misses[: args.max_near_misses], start=1):
        decision_index = _int_or_none(near_miss.get("decision_index"))
        decision_time = _timestamp_or_none(near_miss.get("decision_time") or near_miss.get("time"))
        if decision_index is None and decision_time is not None:
            decision_index = _decision_index_for_time(df, decision_time)
        if decision_index is None or decision_index >= len(df):
            continue
        if decision_time is None:
            decision_time = pd.Timestamp(df.at[decision_index, "timestamp"])

        plan_row = decision_rows.get(decision_index, {})
        missing = near_miss.get("missing_checks") or plan_row.get("blockers", "")
        if isinstance(missing, list):
            missing_text = ", ".join(str(item) for item in missing[:5])
        else:
            missing_text = str(missing)
        title = (
            f"{summary.get('symbol', 'BTCUSD')} MTF evidence - near miss {i:02d} - "
            f"{near_miss.get('direction', '?')} {near_miss.get('verdict', '?')}"
        )
        subtitle = (
            f"Decision {decision_time} | grade={near_miss.get('setup_grade', '?')} | "
            f"conf={near_miss.get('confluence_score', 0):.2f} | POI={near_miss.get('selected_poi', '?')}"
        )
        note = f"Missing: {missing_text}" if missing_text else None
        chart_path = charts_dir / f"near_miss_{i:02d}_mtf_conf{near_miss.get('confluence_score', 0):.2f}.png"
        _render_pack(
            chart_path=chart_path,
            df=df,
            precomputed=precomputed,
            cfg=cfg,
            decision_time=decision_time,
            execution_slice=_near_miss_execution_slice(df, decision_index),
            title=title,
            subtitle=subtitle,
            plan_row=plan_row,
            signal_time=decision_time,
            note=note,
        )
        manifest["charts"].append(
            {
                "type": "near_miss",
                "path": str(chart_path.resolve()),
                "decision_time": decision_time.isoformat(),
                "verdict": near_miss.get("verdict"),
                "confluence_score": near_miss.get("confluence_score"),
                "missing_checks": missing,
            }
        )
        print(f"  {chart_path.name}")

    manifest_path = charts_dir / "chart_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nCharts saved to {charts_dir}")
    print(f"Chart manifest saved to {manifest_path}")


if __name__ == "__main__":
    main()
