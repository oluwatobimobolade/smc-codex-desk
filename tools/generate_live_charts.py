#!/usr/bin/env python3
"""Generate annotated SMC chart recreations from fresh Bitstamp BTCUSD data.
Produces 4 charts: 1D, 4H, 1H, 15m — with swings, equal highs/lows, FVGs,
order blocks, premium/discount, liquidity sweeps, BOS/CHoCH markers."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np

from smc_desk.engine import load_ohlcv_csv, analyze_dataframe, detect_swings, detect_equal_levels, detect_fvgs, detect_structure_events, detect_liquidity_sweeps, detect_order_blocks
from smc_desk.mtf import precompute_htf_series, slice_precomputed_htf, build_mtf_snapshot, derive_htf_consensus_bias, snapshot_to_dict
from smc_desk.rules import load_rule_config

OUTPUT_DIR = ROOT / "journal" / "2026-06-18" / "BTCUSD" / "annotated_charts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load fresh data
df_fresh = load_ohlcv_csv(str(ROOT / "data/ohlcv/bitstamp/BTCUSD/BTCUSD_15m_live_20260615_now.csv"))
df_full = load_ohlcv_csv(str(ROOT / "data/ohlcv/bitstamp/BTCUSD/BTCUSD_15m_20260201_20260618.csv"))
df_full["timestamp"] = pd.to_datetime(df_full["timestamp"])
df_fresh["timestamp"] = pd.to_datetime(df_fresh["timestamp"])
if df_fresh["timestamp"].dt.tz is not None:
    df_fresh["timestamp"] = df_fresh["timestamp"].dt.tz_convert(None)
combined = pd.concat([df_full, df_fresh]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

cfg = load_rule_config()
precomputed = precompute_htf_series(combined)
decision_time = pd.Timestamp(combined["timestamp"].iloc[-1])
last_close = float(combined["close"].iloc[-1])

snap = build_mtf_snapshot(combined, decision_time, cfg, precomputed=precomputed)
snap_dict = snapshot_to_dict(snap)

def plot_candlesticks(ax, df_slice, title, show_volume=False):
    timestamps = pd.to_datetime(df_slice["timestamp"])
    width = 0.3
    for i in range(len(df_slice)):
        o, h, l, c = df_slice.iloc[i][["open","high","low","close"]]
        color = "#26a69a" if c >= o else "#ef5350"
        ax.plot([timestamps.iloc[i], timestamps.iloc[i]], [l, h], color=color, linewidth=0.6, zorder=1)
        bottom = min(o, c)
        top = max(o, c)
        ax.bar(timestamps.iloc[i], top - bottom, bottom=bottom, width=width, color=color, edgecolor=color, zorder=2)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.tick_params(axis="x", labelsize=7, rotation=30)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(True, alpha=0.2)

def annotate_smc(ax, df_slice, swings, zones, events, config, show_premium_discount=True):
    timestamps = pd.to_datetime(df_slice["timestamp"])

    # Premium/discount range
    if show_premium_discount and len(swings) >= 4:
        recent = swings[-8:]
        range_low = min(s.price for s in recent)
        range_high = max(s.price for s in recent)
        midpoint = (range_low + range_high) / 2.0
        ax.axhspan(midpoint, range_high, alpha=0.06, color="red", label=f"Premium ({range_high:.0f}-{midpoint:.0f})")
        ax.axhspan(range_low, midpoint, alpha=0.06, color="green", label=f"Discount ({midpoint:.0f}-{range_low:.0f})")
        ax.axhline(y=midpoint, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)

    # Swings
    for s in swings[-12:]:
        if s.index < len(df_slice):
            t = timestamps.iloc[s.index]
            if s.kind == "high":
                ax.scatter(t, s.price, marker="v", color="blue", s=20, zorder=5, alpha=0.7)
            else:
                ax.scatter(t, s.price, marker="^", color="orange", s=20, zorder=5, alpha=0.7)

    # Equal highs/lows (liquidity)
    for z in zones:
        if z.kind == "liquidity":
            ax.axhspan(z.low, z.high, alpha=0.15, color="purple", zorder=0)
            ax.text(timestamps.iloc[0], z.high, f" {z.label}", fontsize=6, color="purple", va="bottom")

    # FVGs
    for z in zones:
        if z.kind == "fvg" and z.status != "mitigated":
            color = "green" if z.direction == "bullish" else "red"
            ax.axhspan(z.low, z.high, alpha=0.12, color=color, zorder=0)
            mid_t = timestamps.iloc[min(z.end_index or 0, len(df_slice)-1)]
            ax.text(mid_t, (z.low + z.high) / 2, f" FVG({z.status[:3]})", fontsize=5, color=color, va="center")

    # Order blocks
    for z in zones:
        if z.kind == "order_block" and z.status != "mitigated":
            color = "green" if z.direction == "bullish" else "red"
            ax.axhspan(z.low, z.high, alpha=0.15, color=color, zorder=0)
            mid_t = timestamps.iloc[min(z.end_index or 0, len(df_slice)-1)]
            ax.text(mid_t, z.high, f" OB({z.status[:3]},{z.score:.2f})", fontsize=5, color=color, va="bottom")

    # Structure events (BOS/CHoCH)
    for e in events:
        if e.label in ("BOS", "CHoCH") and e.index < len(df_slice):
            t = timestamps.iloc[e.index]
            marker = "D" if e.label == "CHoCH" else "s"
            color = "blue" if e.direction == "bullish" else "red"
            ax.scatter(t, e.price, marker=marker, color=color, s=40, zorder=6, edgecolors="black", linewidth=0.5)
            ax.annotate(f"{e.label}", xy=(t, e.price), fontsize=5, color=color,
                       xytext=(5, 5), textcoords="offset points")

    # Liquidity sweeps
    for e in events:
        if e.label == "Liquidity Sweep" and e.index < len(df_slice):
            t = timestamps.iloc[e.index]
            ax.scatter(t, e.price, marker="*", color="gold", s=60, zorder=6, edgecolors="black", linewidth=0.5)
            ax.annotate(f"Sweep", xy=(t, e.price), fontsize=5, color="goldenrod",
                       xytext=(5, -10), textcoords="offset points")

# === 1D Chart ===
htf_1d = slice_precomputed_htf(precomputed["1d"], "1d", decision_time)
if not htf_1d.empty:
    fig, ax = plt.subplots(figsize=(16, 8))
    df_1d = htf_1d.tail(60).reset_index(drop=True)
    plot_candlesticks(ax, df_1d, f"BTCUSD Daily — {snap_dict['1d']['bias'].upper()} bias (last structure: {snap_dict['1d']['last_structure_label']})")
    swings_1d = detect_swings(df_1d, cfg)
    zones_1d = detect_equal_levels(swings_1d, cfg) + detect_fvgs(df_1d, cfg)
    events_1d = detect_structure_events(df_1d, swings_1d, cfg) + detect_liquidity_sweeps(df_1d, swings_1d, cfg)
    annotate_smc(ax, df_1d, swings_1d, zones_1d, events_1d, cfg)
    ax.legend(fontsize=6, loc="upper right")
    ax.axvline(x=decision_time, color="orange", linestyle=":", linewidth=1, alpha=0.7, label="Now")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "BTCUSD_1D_annotated.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved 1D chart: {OUTPUT_DIR / 'BTCUSD_1D_annotated.png'}")

# === 4H Chart ===
htf_4h = slice_precomputed_htf(precomputed["4h"], "4h", decision_time)
if not htf_4h.empty:
    fig, ax = plt.subplots(figsize=(16, 8))
    df_4h = htf_4h.tail(80).reset_index(drop=True)
    plot_candlesticks(ax, df_4h, f"BTCUSD 4H — {snap_dict['4h']['bias'].upper()} bias (last structure: {snap_dict['4h']['last_structure_label']})")
    swings_4h = detect_swings(df_4h, cfg)
    zones_4h = detect_equal_levels(swings_4h, cfg) + detect_fvgs(df_4h, cfg)
    events_4h = detect_structure_events(df_4h, swings_4h, cfg) + detect_liquidity_sweeps(df_4h, swings_4h, cfg)
    annotate_smc(ax, df_4h, swings_4h, zones_4h, events_4h, cfg)
    ax.legend(fontsize=6, loc="upper right")
    ax.axvline(x=decision_time, color="orange", linestyle=":", linewidth=1, alpha=0.7)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "BTCUSD_4H_annotated.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved 4H chart: {OUTPUT_DIR / 'BTCUSD_4H_annotated.png'}")

# === 1H Chart ===
htf_1h = slice_precomputed_htf(precomputed["1h"], "1h", decision_time)
if not htf_1h.empty:
    fig, ax = plt.subplots(figsize=(16, 8))
    df_1h = htf_1h.tail(100).reset_index(drop=True)
    plot_candlesticks(ax, df_1h, f"BTCUSD 1H — {snap_dict['1h']['bias'].upper()} bias (last structure: {snap_dict['1h']['last_structure_label']})")
    swings_1h = detect_swings(df_1h, cfg)
    zones_1h = detect_equal_levels(swings_1h, cfg) + detect_fvgs(df_1h, cfg)
    events_1h = detect_structure_events(df_1h, swings_1h, cfg) + detect_liquidity_sweeps(df_1h, swings_1h, cfg)
    annotate_smc(ax, df_1h, swings_1h, zones_1h, events_1h, cfg)
    ax.legend(fontsize=6, loc="upper right")
    ax.axvline(x=decision_time, color="orange", linestyle=":", linewidth=1, alpha=0.7)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "BTCUSD_1H_annotated.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved 1H chart: {OUTPUT_DIR / 'BTCUSD_1H_annotated.png'}")

# === 15m Chart (execution) ===
fig, ax = plt.subplots(figsize=(16, 8))
df_15m = combined.tail(250).reset_index(drop=True)
plot_candlesticks(ax, df_15m, f"BTCUSD 15m Execution — Last: {last_close:.2f}")
swings_15m = detect_swings(df_15m, cfg)
zones_15m = detect_equal_levels(swings_15m, cfg) + detect_fvgs(df_15m, cfg)
struct_events_15m = detect_structure_events(df_15m, swings_15m, cfg)
sweep_events_15m = detect_liquidity_sweeps(df_15m, swings_15m, cfg)
all_events_15m = sorted(struct_events_15m + sweep_events_15m, key=lambda e: e.index)[-18:]
obs_15m = detect_order_blocks(df_15m, struct_events_15m, cfg)
all_zones_15m = zones_15m + obs_15m
annotate_smc(ax, df_15m, swings_15m, all_zones_15m, all_events_15m, cfg)

# Run the full 15m analysis and mark the trade plan
consensus_bias = derive_htf_consensus_bias(snap_dict)
bias_hint = consensus_bias if consensus_bias in ("bullish", "bearish") else None
analysis, _ = analyze_dataframe(df=combined, symbol="BTCUSD", timeframe="15m", config=cfg, bias_hint=bias_hint, input_type="ohlcv")
plan = analysis.trade_plan

if plan.selected_poi:
    ax.axhspan(plan.selected_poi.low, plan.selected_poi.high, alpha=0.25, color="blue", zorder=0)
    ax.text(df_15m["timestamp"].iloc[0], plan.selected_poi.high, f" POI: {plan.selected_poi.label} ({plan.selected_poi.low:.0f}-{plan.selected_poi.high:.0f})", fontsize=6, color="blue", va="bottom")

if plan.invalidation:
    ax.axhline(y=plan.invalidation, color="red", linestyle="--", linewidth=0.8, alpha=0.6, label=f"Stop: {plan.invalidation:.0f}")
if plan.targets:
    for t in plan.targets[:2]:
        ax.axhline(y=t, color="green", linestyle="--", linewidth=0.8, alpha=0.6, label=f"Target: {t:.0f}")

ax.axvline(x=decision_time, color="orange", linestyle=":", linewidth=1, alpha=0.7, label=f"Now: {decision_time.strftime('%H:%M')}")
ax.legend(fontsize=6, loc="upper right")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "BTCUSD_15m_annotated.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved 15m chart: {OUTPUT_DIR / 'BTCUSD_15m_annotated.png'}")

# === Summary panel ===
fig, ax = plt.subplots(figsize=(14, 6))
ax.axis("off")
summary_text = [
    f"BTCUSD LIVE SMC ANALYSIS — {decision_time.strftime('%Y-%m-%d %H:%M UTC')}",
    f"Last close: {last_close:.2f}  (Bitstamp spot)",
    "",
    "HTF CONTEXT:",
    f"  Daily:  {snap_dict['1d']['bias'].upper():8s}  structure={snap_dict['1d']['last_structure_label']}  close={snap_dict['1d']['last_close']:.0f}",
    f"  4H:     {snap_dict['4h']['bias'].upper():8s}  structure={snap_dict['4h']['last_structure_label']}  close={snap_dict['4h']['last_close']:.0f}",
    f"  1H:     {snap_dict['1h']['bias'].upper():8s}  structure={snap_dict['1h']['last_structure_label']}  close={snap_dict['1h']['last_close']:.0f}",
    f"  Alignment: {snap_dict['alignment'].upper()}  (agreement: {snap_dict['agreement_ratio']:.0%})",
    "",
    "15m EXECUTION:",
    f"  Verdict: {plan.verdict} / Grade {plan.setup_grade}",
    f"  Direction: {plan.direction}",
    f"  Confluence: {plan.confluence_score:.2f}",
    f"  Risk: {plan.risk_pct:.1f}%",
    "",
    "CHECKLIST:",
]
for key, value in plan.checklist.items():
    summary_text.append(f"  [{'x' if value else ' '}] {key.replace('_', ' ')}")

if plan.selected_poi:
    summary_text += ["", f"POI: {plan.selected_poi.label} {plan.selected_poi.low:.0f}-{plan.selected_poi.high:.0f} ({plan.selected_poi.status}, score {plan.selected_poi.score:.2f})"]
if plan.entry_low and plan.entry_high:
    summary_text += [f"Entry zone: {plan.entry_low:.0f} - {plan.entry_high:.0f}"]
if plan.invalidation:
    summary_text.append(f"Stop: {plan.invalidation:.0f}")
if plan.targets:
    summary_text.append(f"Target: {plan.targets[0]:.0f}")
if plan.risk_reward:
    summary_text.append(f"R:R: {plan.risk_reward}:1")

missing = [k.replace('_', ' ') for k, v in plan.checklist.items() if not v]
summary_text += ["", f"MISSING FOR EXECUTE ({len(missing)}):", f"  {', '.join(missing)}"]
summary_text += ["", "WARNING: Research analysis only. NOT a trade recommendation."]

ax.text(0.05, 0.95, "\n".join(summary_text), transform=ax.transAxes, fontsize=9,
        verticalalignment="top", fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.8))
plt.savefig(OUTPUT_DIR / "BTCUSD_summary.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved summary: {OUTPUT_DIR / 'BTCUSD_summary.png'}")

print(f"\nAll annotated charts saved to {OUTPUT_DIR}")
print(f"TradingView screenshots (for your visual reference) are in journal/2026-06-18/BTCUSD/")
