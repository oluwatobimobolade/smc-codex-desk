from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.perception.ontology import Direction, ConfirmationStatus


def _safe_decimal(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _idx_for_timestamp(df: pd.DataFrame, ts_str: str) -> int:
    n = len(df)
    ts = pd.to_datetime(ts_str)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    # Normalize the dataframe timestamp column to tz-aware UTC to avoid
    # dtype comparison errors (datetime64[us] vs Timestamp).
    col = pd.to_datetime(df["timestamp"], utc=True)
    matches = df.index[col == ts]
    if len(matches) > 0:
        return int(matches[0])
    future = df.index[col >= ts]
    if len(future) > 0:
        return int(future[0])
    return n - 1


def _cognitive_bias(cognitive_output: dict[str, Any], timeframe: str) -> str:
    # The chart must agree with the V6 hierarchy for *this* timeframe, not the
    # top-level directional bias timeframe. A 15m chart saying "bullish" when
    # the 15m external structure is bearish is the exact bug WP-0023 fixes.
    hierarchy = cognitive_output.get("structure_hierarchy") or {}
    if timeframe in hierarchy:
        return str(hierarchy[timeframe].get("external_bias", "neutral"))
    roles = cognitive_output.get("timeframe_roles") or {}
    return str(roles.get("directional_bias") or roles.get("setup_bias") or "neutral")


def _active_poi(cognitive_output: dict[str, Any]) -> dict[str, Any] | None:
    watch = cognitive_output.get("watch_state") or {}
    active = watch.get("active_poi")
    if isinstance(active, dict) and active.get("poi_id"):
        return active
    return None


def _dealing_range(cognitive_output: dict[str, Any], timeframe: str) -> dict[str, Any] | None:
    hierarchy = cognitive_output.get("structure_hierarchy") or {}
    tf_h = hierarchy.get(timeframe) or {}
    dr = tf_h.get("dealing_range")
    if isinstance(dr, dict) and dr.get("range_high") and dr.get("range_low"):
        return dr
    return None


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

def render_v2_story_chart(
    df: pd.DataFrame,
    snapshot: PerceptionSnapshot,
    cognitive_output: dict[str, Any],
    timeframe: str,
    output_path: str,
    mode: str = "story",
) -> None:
    """Render a V6-cognitive-aligned story chart.

    The story chart title, bias label, and active POI are taken from the
    colleague brain's final cognitive output so the visual story never
    contradicts the cognitive state (e.g. no legacy "bias bullish" banner
    when the V6 hierarchy says bearish).  Debug mode overlays additional
    raw perception objects for inspection.
    """
    n = len(df)
    if n == 0:
        raise ValueError("Cannot render an empty dataframe.")

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)

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

    is_debug = mode == "debug"
    watch = cognitive_output.get("watch_state") or {}
    final_state = watch.get("final_state") or cognitive_output.get("final_state") or "UNKNOWN"
    final_action = cognitive_output.get("final_action") or watch.get("final_action") or "NO_SIGNAL"
    model_direction = str(watch.get("direction") or cognitive_output.get("direction") or "neutral")
    bias = _cognitive_bias(cognitive_output, timeframe)
    symbol = cognitive_output.get("symbol", "")
    hierarchy = cognitive_output.get("structure_hierarchy") or {}
    tf_h = hierarchy.get(timeframe) or {}
    depth_status = str(tf_h.get("depth_status") or "")
    shallow_daily = timeframe == "1d" and depth_status.startswith("shallow_context")
    visible_low = float(l.min())
    visible_high = float(h.max())
    visible_span = max(visible_high - visible_low, 1.0)
    y_low = visible_low - visible_span * 0.12
    y_high = visible_high + visible_span * 0.12
    note_lines: list[str] = []

    def _in_visible_window(price: float | None, *, generous: bool = False) -> bool:
        if price is None:
            return False
        pad = visible_span * (0.55 if generous else 0.25)
        return (visible_low - pad) <= price <= (visible_high + pad)

    def _add_note(text: str, *, priority: bool = False) -> None:
        if text and text not in note_lines:
            if priority:
                note_lines.insert(0, text)
            else:
                note_lines.append(text)

    def _plot_level(price: float | None, label: str, color: str, *, linestyle: str = "--", linewidth: float = 1.0) -> None:
        nonlocal y_low, y_high
        if price is None:
            return
        if is_debug or _in_visible_window(price, generous=True):
            ax.axhline(price, color=color, linestyle=linestyle, linewidth=linewidth, alpha=0.82, zorder=5)
            _label(n + 0.65, price, f" {label}", color, 8, "bold")
            y_low = min(y_low, price - visible_span * 0.05)
            y_high = max(y_high, price + visible_span * 0.05)
        else:
            _add_note(f"{label} off-screen at {price:,.2f}")

    readiness = cognitive_output.get("execution_readiness") or {}
    move_quality = cognitive_output.get("inducement_continuation") or {}
    if readiness.get("state"):
        _add_note(f"Readiness: {readiness.get('state')} ({readiness.get('confidence')})")
    if move_quality.get("state"):
        _add_note(f"Move quality: {move_quality.get('state')} ({move_quality.get('confidence')})")

    # --- dealing range / premium-discount shading from V6 hierarchy ---
    dr = _dealing_range(cognitive_output, timeframe)
    if dr:
        rh = _safe_decimal(dr.get("range_high"))
        rl = _safe_decimal(dr.get("range_low"))
        eq = _safe_decimal(dr.get("equilibrium_50")) or ((rh + rl) / 2 if rh is not None and rl is not None else None)
        if rh is not None and rl is not None and eq is not None:
            if is_debug or (_in_visible_window(rh, generous=True) and _in_visible_window(rl, generous=True)):
                ax.axhspan(eq, rh, color=dn, alpha=0.05)
                ax.axhspan(rl, eq, color=up, alpha=0.05)
                ax.axhline(eq, color="#787b86", linestyle="--", linewidth=0.8)
                ax.text(0, eq, "  EQ50", color="#9598a1", fontsize=7, va="bottom")
                y_low = min(y_low, rl - visible_span * 0.05)
                y_high = max(y_high, rh + visible_span * 0.05)
            else:
                _add_note(f"Active range {rl:,.2f}-{rh:,.2f} is wider than visible chart; not stretching scale.")

    protected_high = _safe_decimal(tf_h.get("protected_high"))
    protected_low = _safe_decimal(tf_h.get("protected_low"))
    _plot_level(protected_high, "protected high", "#ffb74d", linestyle=(0, (5, 3)), linewidth=1.1)
    _plot_level(protected_low, "protected low", "#81c784", linestyle=(0, (5, 3)), linewidth=1.1)

    if is_debug:
        # Debug mode intentionally exposes the detector firehose.
        for scale in ["local", "internal", "external"]:
            for sw in snapshot.swings.get(scale, []):
                ix = _idx_for_timestamp(df, str(sw.pivot_time))
                price = float(sw.price_low if sw.direction == Direction.BULLISH else sw.price_high)
                color = up if sw.direction == Direction.BULLISH else dn
                marker = "^" if sw.direction == Direction.BULLISH else "v"
                s = 45 if sw.evidence.is_external else 25
                alpha = 0.85 if sw.evidence.is_external else 0.45
                ax.scatter([ix], [price], s=s, color=color, marker=marker, zorder=4, alpha=alpha)
        for brk in snapshot.structure_breaks:
            ix_cand = _idx_for_timestamp(df, str(brk.candidate_at))
            level = float(brk.evidence.broken_price)
            col = up if brk.direction == Direction.BULLISH else dn
            confirmed = brk.confirmation_status == ConfirmationStatus.CONFIRMED
            label_text = f"{brk.break_type}"
            if not confirmed:
                label_text += " (PROBE)"
                ls = ":"
                end_ix = n - 1
            else:
                ls = "-"
                end_ix = _idx_for_timestamp(df, str(brk.confirmed_at))
            ax.plot([max(0, ix_cand - 5), end_ix], [level, level], color=col, linestyle=ls, linewidth=1.2, zorder=5)
            _label(ix_cand, level, f" {label_text}", col, 8, "bold")
        for fvg in snapshot.fvgs:
            ix = _idx_for_timestamp(df, str(fvg.pivot_time))
            col = up if fvg.direction == Direction.BULLISH else dn
            low, high = float(fvg.price_low), float(fvg.price_high)
            ax.add_patch(Rectangle((ix, low), (n - 1) - ix, high - low, color=col, alpha=0.18, zorder=1, linewidth=0))
            _label(ix, high, " FVG", col, 7, "normal", va="bottom")
        for ob in snapshot.order_blocks:
            ix = _idx_for_timestamp(df, str(ob.pivot_time))
            col = "#3179f5" if ob.direction == Direction.BULLISH else "#ff9800"
            low, high = float(ob.price_low), float(ob.price_high)
            ax.add_patch(Rectangle((ix, low), (n - 1) - ix, high - low, color=col, alpha=0.18, zorder=1, linewidth=0))
            _label(ix, high, " OB", col, 7, "normal", va="bottom")
        seen_levels: list[float] = []
        for liq in snapshot.liquidity_levels:
            lvl = float(liq.price_high) if liq.direction == Direction.BEARISH else float(liq.price_low)
            if any(abs(lvl - p) <= max(lvl, 1e-9) * 0.0012 for p in seen_levels):
                continue
            seen_levels.append(lvl)
            ax.axhline(lvl, color="#b39ddb", linestyle=(0, (4, 3)), linewidth=0.9, alpha=0.65, zorder=4)

    # --- active POI band at right edge ---
    active_poi = _active_poi(cognitive_output)
    if active_poi and not shallow_daily:
        p_low = _safe_decimal(active_poi.get("price_low"))
        p_high = _safe_decimal(active_poi.get("price_high"))
        valid_active = (
            active_poi.get("validity_status") == "VALID_ACTIVE_SETUP_POI"
            and active_poi.get("scope") == "active_setup"
        )
        if not valid_active:
            _add_note(
                f"{active_poi.get('timeframe', '')} {active_poi.get('kind', 'POI')} "
                f"{active_poi.get('price_low')}-{active_poi.get('price_high')} is not active: "
                f"{active_poi.get('rejection_reason') or active_poi.get('validity_status')}",
                priority=True,
            )
        elif p_low is not None and p_high is not None and _in_visible_window(p_low, generous=True) and _in_visible_window(p_high, generous=True):
            ax.add_patch(Rectangle((n - 0.15, min(p_low, p_high)), 0.7, abs(p_high - p_low),
                                   color="#9467bd", alpha=0.22, zorder=5, linewidth=0))
            _label(n + 0.65, max(p_low, p_high),
                   f" ACTIVE POI {active_poi.get('timeframe', '')} {active_poi.get('kind', '')}",
                   "#9467bd", 8, "bold", va="bottom")
            y_low = min(y_low, min(p_low, p_high) - visible_span * 0.05)
            y_high = max(y_high, max(p_low, p_high) + visible_span * 0.05)
        elif p_low is not None and p_high is not None:
            _add_note(
                f"Valid {active_poi.get('timeframe', '')} {active_poi.get('kind', 'POI')} "
                f"{p_low:,.2f}-{p_high:,.2f} is off-screen; chart scale not stretched."
            )
    elif active_poi and shallow_daily:
        _add_note("Daily context is shallow; lower-timeframe POI hidden from Daily authority chart.")
    else:
        selection = watch.get("poi_selection") if isinstance(watch.get("poi_selection"), dict) else {}
        parent = (selection.get("parent_scope_pois") or [])[:1]
        if parent:
            item = parent[0]
            _add_note(
                f"Parent {item.get('timeframe', '')} {item.get('kind', 'POI')} "
                f"{item.get('price_low')}-{item.get('price_high')} is not active: {item.get('rejection_reason')}",
                priority=True,
            )

    # --- current price ---
    last_px = float(c[-1])
    ax.axhline(last_px, color="#cfd2dc", linestyle=(0, (1, 2)), linewidth=0.8, alpha=0.55, zorder=5)
    _label(n + 0.65, last_px, f" {last_px:,.0f}", "#cfd2dc", 8, "bold")

    # --- axes / ticks ---
    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(pd.to_datetime(df["timestamp"].iloc[t]))[5:16] for t in ticks], color="#9598a1", fontsize=8)
    ax.tick_params(colors="#9598a1")
    for spine in ax.spines.values():
        spine.set_color("#2a2e39")
    ax.set_xlim(-1, n + 13)
    ax.set_ylim(y_low, y_high)

    # --- titles and banners from V6 cognitive output ---
    depth_banner_parts: list[str] = []
    if depth_status:
        depth_banner_parts.append(str(depth_status))
    truth = cognitive_output.get("truth_report") or {}
    for summary in truth.get("timeframe_summaries", []):
        if summary.get("timeframe") == timeframe and summary.get("candle_count"):
            depth_banner_parts.append(f"bars={summary['candle_count']}")
            break
    depth_banner = " | ".join(depth_banner_parts) if depth_banner_parts else ""

    phase = str(tf_h.get("structure_phase") or "unknown phase")
    title = f"{symbol} {timeframe} - model {model_direction} | {timeframe} bias {bias} | {phase} | {final_state}"
    ax.set_title(title, color="#e0e0e0", fontsize=12, fontweight="bold", loc="left")

    rr = f"  ·  action {final_action}"
    bias_line = f"model {model_direction}  ·  {timeframe} bias {bias}{rr}"
    if depth_banner:
        bias_line += f"  ·  {depth_banner}"
    if shallow_daily:
        bias_line += "  ·  Daily context shallow; lower-timeframe thesis only"
    ax.text(0.008, 0.985, bias_line, transform=ax.transAxes,
            ha="left", va="top", color="#9598a1", fontsize=9, fontweight="bold")

    if note_lines:
        ax.text(
            0.008,
            0.92,
            "\n".join(f"- {line}" for line in note_lines[:4]),
            transform=ax.transAxes,
            ha="left",
            va="top",
            color="#d7ccc8",
            fontsize=8,
            linespacing=1.3,
            bbox={"facecolor": "#151922", "edgecolor": "#3a3f4b", "alpha": 0.72, "boxstyle": "round,pad=0.35"},
        )

    authority = cognitive_output.get("authority") or {}
    if authority.get("live_execution") == "disabled":
        ax.text(0.008, 0.015, "OBSERVE-ONLY  ·  NO EXECUTION AUTHORITY",
                transform=ax.transAxes, ha="left", va="bottom", color="#ef5350",
                fontsize=8, fontweight="bold", alpha=0.85)

    legend = (
        "Official story chart · Debug annotations hidden · protected levels / active range / valid POI only · Observe-only, no execution signal"
        if not is_debug
        else "Debug chart · raw swings / BOS / CHoCH / FVG / OB / liquidity shown"
    )
    ax.text(0.5, -0.085, legend, transform=ax.transAxes, ha="center", va="top", color="#9598a1", fontsize=8)

    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


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
