#!/usr/bin/env python3
"""Build a research dataset: every engine setup + its mechanical outcome.

The live engine almost never fires a full "Execute" (the gates are strict by
design), so a normal backtest yields 1-3 trades — far too few to learn from.
This harness removes the *gate* (not the analysis): at every decision bar it
runs the real deterministic engine, and whenever the engine proposes a valid
POI geometry (entry/stop/target), it simulates the mechanical outcome forward
using the *same* entry/exit logic as the production backtester.

Result: thousands of rows of ``features -> realized R``. That is the substrate
for measuring which SMC components actually carry expectancy (calibrate step).

No future leakage: the engine only ever sees ``df.iloc[:index+1]`` and HTF
candles closed at or before the decision time. The forward simulation looks
ahead only to *label* the row, never to inform the decision.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import (
    analyze_dataframe,
    detect_structure_events,
    detect_swings,
    infer_trend,
    load_ohlcv_csv,
)
from smc_desk.mtf import TF_TO_DURATION, derive_htf_consensus_bias, precompute_htf_series
from smc_desk.rules import load_rule_config
from tools.backtest_management import simulate_managed_trade

CHECKLIST_KEYS = [
    "directional_bias",
    "fresh_or_partial_poi",
    "premium_discount_aligned",
    "liquidity_sweep",
    "displacement_break",
    "sweep_before_break",
    "price_at_or_near_poi",
    "stop_has_volatility_buffer",
    "risk_reward_floor",
]


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR (Average True Range) for volatility normalization."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ADX (Average Directional Index) for trend strength."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    return adx


def _premium_discount_ratio(price: float, range_low: float, range_high: float) -> float:
    """Compute where price sits in the dealing range (0.0 = low, 1.0 = high)."""
    if range_high <= range_low:
        return 0.5
    return max(0.0, min(1.0, (price - range_low) / (range_high - range_low)))


def _structure_event_density(events: list, lookback_bars: int = 50) -> int:
    """Count BOS/CHoCH events in the last N bars."""
    if not events:
        return 0
    recent = [e for e in events if e.label in {"BOS", "CHoCH"}]
    if not recent:
        return 0
    # Events are sorted by index; take the last lookback_bars worth
    max_index = max(e.index for e in recent)
    cutoff = max_index - lookback_bars
    return sum(1 for e in recent if e.index >= cutoff)


def _sweep_depth_atr(sweep_event, atr_value: float) -> float:
    """Compute sweep depth normalized by ATR."""
    if not sweep_event or atr_value <= 0:
        return 0.0
    # Sweep depth = how far the wick went past the swept level
    swept_level = sweep_event.swept_level
    if swept_level is None:
        return 0.0
    depth = abs(sweep_event.price - swept_level)
    return depth / atr_value


def _poi_age_bars(poi, decision_index: int) -> int:
    """Compute how many bars old the POI is."""
    if not poi or poi.start_index is None:
        return 0
    return max(0, decision_index - poi.start_index)


def _competing_poi_count(analysis, selected_poi) -> int:
    """Count how many POIs survived filtering (competing for selection)."""
    if not analysis or not analysis.zones:
        return 0
    poi_zones = [z for z in analysis.zones if z.kind in {"fvg", "order_block"}]
    return len(poi_zones)


def _body_ratio_at_decision(df: pd.DataFrame, index: int) -> float:
    """Compute candle body ratio at decision bar (0.0 = doji, 1.0 = full body)."""
    if index < 0 or index >= len(df):
        return 0.0
    row = df.iloc[index]
    body = abs(row["close"] - row["open"])
    range_val = row["high"] - row["low"]
    if range_val <= 0:
        return 0.0
    return body / range_val


def _range_pct_at_decision(df: pd.DataFrame, index: int) -> float:
    """Compute candle range as percentage of close."""
    if index < 0 or index >= len(df):
        return 0.0
    row = df.iloc[index]
    range_val = row["high"] - row["low"]
    if row["close"] <= 0:
        return 0.0
    return range_val / row["close"]


def _is_killzone(hour: int) -> bool:
    """Check if hour is in a killzone (London 7-10 UTC or NY 12-15 UTC)."""
    return (7 <= hour < 10) or (12 <= hour < 15)


def _minute_of_session(hour: int, minute: int) -> int:
    """Compute minutes since session open."""
    # Asia: 00:00, London: 07:00, NY: 12:00
    if 0 <= hour < 7:
        return hour * 60 + minute
    elif 7 <= hour < 12:
        return (hour - 7) * 60 + minute
    elif 12 <= hour < 21:
        return (hour - 12) * 60 + minute
    else:
        return (hour - 21) * 60 + minute


def _htf_bias(htf_df, config) -> str:
    """Cheap HTF bias: swings + structure on the last lookback bars only.

    Matches the production bias definition (last BOS/CHoCH direction, else
    inferred trend) without the full FVG/OB/trade-plan cost of analyze_dataframe.
    """
    if htf_df is None or len(htf_df) < 5:
        return "neutral"
    sub = htf_df.tail(config.lookback_bars).reset_index(drop=True).copy()
    sub["timestamp"] = pd.to_datetime(sub["timestamp"], utc=False)
    swings = detect_swings(sub, config)
    events = [e for e in detect_structure_events(sub, swings, config) if e.label in {"BOS", "CHoCH"}]
    if events and events[-1].direction in {"bullish", "bearish"}:
        return events[-1].direction
    return infer_trend(swings)


def _visible_htf_tail(
    htf_df: pd.DataFrame,
    target_tf: str,
    decision_time: pd.Timestamp,
    lookback_bars: int,
) -> pd.DataFrame:
    """Return only the visible HTF tail needed for bias calculation.

    The replay loop may call this thousands of times. Slicing the whole
    historical HTF dataframe and then taking a tail is correct but slow; this
    preserves the same closed-candle rule while only materializing the analysis
    window the engine actually uses.
    """
    if htf_df.empty:
        return htf_df
    if "_close_visible_at" in htf_df.columns:
        close_times = htf_df["_close_visible_at"]
    else:
        close_times = pd.to_datetime(htf_df["timestamp"], utc=False) + TF_TO_DURATION[target_tf]
    visible = htf_df.loc[close_times <= decision_time]
    return visible.tail(lookback_bars).reset_index(drop=True)


def _alignment(biases: list[str]) -> tuple[str, float]:
    nb = sum(1 for b in biases if b == "bullish")
    ne = sum(1 for b in biases if b == "bearish")
    n = len(biases) or 1
    if nb == len(biases):
        a = "bullish"
    elif ne == len(biases):
        a = "bearish"
    elif nb >= ne and nb > 0:
        a = "bullish"
    elif ne > nb:
        a = "bearish"
    else:
        a = "neutral"
    return a, round(max(nb, ne) / n, 4)


def session_for(hour: int) -> str:
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 16:
        return "london_ny_overlap"
    if 16 <= hour < 21:
        return "newyork"
    return "after_hours"


def _htf_swing_prices(tail: pd.DataFrame, config) -> list[float]:
    """Swing high/low prices from a visible HTF tail, for swept-level confluence."""
    if tail is None or len(tail) < 5:
        return []
    sub = tail.copy()
    sub["timestamp"] = pd.to_datetime(sub["timestamp"], utc=False)
    return [float(s.price) for s in detect_swings(sub, config)]


def _distance_to_htf_liquidity(
    direction: str,
    entry_price: float,
    tail_1h: pd.DataFrame,
    tail_4h: pd.DataFrame,
    config
) -> float | None:
    """Find absolute price distance to the nearest opposing HTF swing."""
    if direction not in {"bullish", "bearish"} or entry_price <= 0:
        return None
        
    prices = set()
    for tail in (tail_1h, tail_4h):
        if tail is not None and len(tail) >= 5:
            sub = tail.copy()
            sub["timestamp"] = pd.to_datetime(sub["timestamp"], utc=False)
            swings = detect_swings(sub, config)
            if direction == "bullish":
                # Looking for swing highs above entry
                prices.update(s.price for s in swings if s.kind == "high" and s.price > entry_price)
            else:
                # Looking for swing lows below entry
                prices.update(s.price for s in swings if s.kind == "low" and s.price < entry_price)
                
    if not prices:
        return None
        
    if direction == "bullish":
        nearest = min(prices)
        return float(nearest - entry_price)
    else:
        nearest = max(prices)
        return float(entry_price - nearest)


def _round_proximity(price: float) -> float:
    """Relative distance to the nearest round number, scale-robust (0.0 = exactly round).

    Works across price scales (BTC ~$60k, XRP ~$0.5) by snapping to round steps at the
    price's own order of magnitude. A swept level sitting on a round number is more
    significant liquidity (psychological + resting orders).
    """
    if price <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(price))
    best = 1.0
    for step in (mag, mag / 2.0, mag / 4.0, mag / 5.0, mag / 10.0):
        nearest = round(price / step) * step
        best = min(best, abs(price - nearest) / price)
    return best


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(args.ohlcv)
    if len(df) <= args.warmup_bars + args.max_hold_bars:
        raise ValueError("Not enough candles for warmup plus max hold window.")

    last_decision_index = len(df) - args.max_hold_bars - 1
    if args.limit_bars is not None:
        last_decision_index = min(last_decision_index, args.warmup_bars + args.limit_bars)
    if args.decision_end:
        decision_end = pd.Timestamp(args.decision_end)
        end_candidates = df.index[pd.to_datetime(df["timestamp"], utc=False) <= decision_end]
        if len(end_candidates):
            last_decision_index = min(last_decision_index, int(end_candidates[-1]))

    first_decision_index = args.warmup_bars
    if args.decision_start:
        decision_start = pd.Timestamp(args.decision_start)
        start_candidates = df.index[pd.to_datetime(df["timestamp"], utc=False) >= decision_start]
        if len(start_candidates):
            first_decision_index = max(first_decision_index, int(start_candidates[0]))
        else:
            return []

    precomputed = precompute_htf_series(df)
    rows: list[dict[str, Any]] = []
    index = first_decision_index
    decisions_seen = 0
    while index <= last_decision_index:
        if args.max_decisions is not None and decisions_seen >= args.max_decisions:
            break
        decision_time = pd.Timestamp(df.at[index, "timestamp"])
        decisions_seen += 1
        tail_1h = _visible_htf_tail(precomputed["1h"], "1h", decision_time, config.lookback_bars)
        tail_4h = _visible_htf_tail(precomputed["4h"], "4h", decision_time, config.lookback_bars)
        tail_1d = _visible_htf_tail(precomputed["1d"], "1d", decision_time, config.lookback_bars)
        h1 = _htf_bias(tail_1h, config)
        h4 = _htf_bias(tail_4h, config)
        d1 = _htf_bias(tail_1d, config)
        alignment, agreement_ratio = _alignment([h1, h4, d1])

        consensus_bias = derive_htf_consensus_bias(
            {
                "1h": {"bias": h1},
                "4h": {"bias": h4},
                "1d": {"bias": d1},
            }
        )
        bias_hint = (
            consensus_bias
            if args.use_htf_bias == "on" and consensus_bias in {"bullish", "bearish"}
            else None
        )
        history = df.iloc[: index + 1].copy()
        analysis, _ = analyze_dataframe(
            df=history, symbol=args.symbol, timeframe=args.timeframe, config=config,
            bias_hint=bias_hint, notes="research", input_type="ohlcv", poi_selection=args.poi_selection,
        )
        plan = analysis.trade_plan
        poi = plan.selected_poi

        # Only sample bars where the engine actually proposes a tradeable geometry.
        if not (poi and plan.entry_low is not None and plan.invalidation is not None and plan.targets):
            index += args.decision_step
            continue

        sim, _resume = simulate_managed_trade(
            df=df, signal_index=index, direction=plan.direction,
            entry_low=plan.entry_low, entry_high=plan.entry_high,
            invalidation=plan.invalidation, target=plan.targets[0],
            entry_wait_bars=args.entry_wait_bars, max_hold_bars=args.max_hold_bars,
            cost_bps=args.cost_bps, entry_mode=args.entry_mode,
            breakeven_r=1.5, time_exit_bars=48
        )
        outcome = sim.get("outcome", "unknown")
        triggered = sim.get("entry_index") is not None and not outcome.startswith("missed") and outcome != "invalid_geometry"
        close = float(df.at[index, "close"])
        htf_aligned = plan.direction in {"bullish", "bearish"} and alignment == plan.direction

        # --- Enriched continuous features ---
        atr_series = _compute_atr(history, period=14)
        atr_at_decision = float(atr_series.iloc[index]) if index < len(atr_series) and not pd.isna(atr_series.iloc[index]) else 0.0
        atr_pct = atr_at_decision / max(close, 1e-9) if atr_at_decision > 0 else 0.0
        
        adx_series = _compute_adx(history, period=14)
        adx_at_decision = float(adx_series.iloc[index]) if index < len(adx_series) and not pd.isna(adx_series.iloc[index]) else 0.0
        
        range_low = float(analysis.metrics.get("range_low", 0.0))
        range_high = float(analysis.metrics.get("range_high", 0.0))
        pd_ratio = _premium_discount_ratio(close, range_low, range_high)
        
        poi_age = _poi_age_bars(poi, index)
        competing_pois = _competing_poi_count(analysis, poi)
        
        # Find the triggering structure event (most recent BOS/CHoCH before decision)
        triggering_event = None
        for event in reversed(analysis.events):
            if event.label in {"BOS", "CHoCH"} and event.index <= index:
                triggering_event = event
                break
        
        displacement_score = float(triggering_event.displacement_score) if triggering_event else 0.0
        break_strength = str(triggering_event.strength) if triggering_event else "unknown"
        
        # Find most recent sweep event
        sweep_event = None
        for event in reversed(analysis.events):
            if event.label == "Liquidity Sweep" and event.index <= index:
                sweep_event = event
                break
        
        sweep_depth = _sweep_depth_atr(sweep_event, atr_at_decision)
        sweep_recency = max(0, index - sweep_event.index) if sweep_event else 999
        
        structure_density = _structure_event_density(analysis.events, lookback_bars=50)
        body_ratio = _body_ratio_at_decision(df, index)
        range_pct = _range_pct_at_decision(df, index)
        
        # Time features
        hour_utc = decision_time.hour
        day_of_week = decision_time.dayofweek
        minute_of_session = _minute_of_session(hour_utc, decision_time.minute)
        is_killzone = _is_killzone(hour_utc)

        # --- Liquidity SIGNIFICANCE of the swept level (Phase 2 entry-quality test) ---
        # Characterize the sweep that motivated THIS trade (direction-matched, else most
        # recent). The thesis: sweeping *significant* liquidity (multi-touch equal levels,
        # HTF swings, round numbers) precedes stronger reversals than sweeping a random
        # 15m wiggle. No leakage: zones/events/HTF tails are all <= decision bar.
        dir_sweep = None
        for event in reversed(analysis.events):
            if event.label == "Liquidity Sweep" and event.index <= index and event.direction == plan.direction:
                dir_sweep = event
                break
        sig_sweep = dir_sweep or sweep_event
        swept_level = float(sig_sweep.swept_level) if (sig_sweep and sig_sweep.swept_level is not None) else None
        swept_touch_count = 0
        swept_is_equal_cluster = False
        swept_htf_confluence = 0
        swept_round_prox = 1.0
        liquidity_significance = 0.0
        if swept_level is not None and swept_level > 0:
            tol = swept_level * 0.0025  # 0.25% "same level" tolerance, scale-robust
            for z in analysis.zones:
                if z.kind == "liquidity" and (z.low - tol) <= swept_level <= (z.high + tol):
                    swept_is_equal_cluster = True
                    swept_touch_count = max(swept_touch_count, int(z.touched_count or 0))
            for tail in (tail_1h, tail_4h, tail_1d):
                prices = _htf_swing_prices(tail, config)
                if any(abs(p - swept_level) <= tol for p in prices):
                    swept_htf_confluence += 1
            swept_round_prox = _round_proximity(swept_level)
            touch_term = min(1.0, swept_touch_count / 5.0)
            htf_term = swept_htf_confluence / 3.0
            round_term = 1.0 if swept_round_prox <= 0.001 else (0.5 if swept_round_prox <= 0.0025 else 0.0)
            liquidity_significance = round(0.45 * htf_term + 0.40 * touch_term + 0.15 * round_term, 3)

        # --- Distance to HTF Liquidity ---
        approx_entry = (float(plan.entry_low) + float(plan.entry_high)) / 2.0 if (plan.entry_low and plan.entry_high) else float(close)
        dist_htf_raw = _distance_to_htf_liquidity(plan.direction, approx_entry, tail_1h, tail_4h, config)
        
        dist_htf_atr = None
        if dist_htf_raw is not None and atr_at_decision > 0:
            dist_htf_atr = dist_htf_raw / atr_at_decision
            
        dist_htf_r = None
        risk_per_r = None
        if plan.invalidation is not None:
            risk_per_r = abs(approx_entry - float(plan.invalidation))
            if risk_per_r > 0 and dist_htf_raw is not None:
                dist_htf_r = dist_htf_raw / risk_per_r

        row: dict[str, Any] = {
            "symbol": args.symbol,
            "decision_index": index,
            "decision_time": decision_time.isoformat(),
            "session": session_for(decision_time.hour),
            "direction": plan.direction,
            "verdict": plan.verdict,
            "setup_grade": plan.setup_grade,
            "confluence_score": round(float(plan.confluence_score), 3),
            "poi_kind": poi.kind,
            "poi_status": poi.status,
            "poi_score": round(float(poi.score), 3),
            "poi_low": round(float(poi.low), 2),
            "poi_high": round(float(poi.high), 2),
            "poi_width_pct": round((float(poi.high) - float(poi.low)) / max(close, 1e-9) * 100, 4),
            "poi_age_bars": poi_age,
            "poi_competing_count": competing_pois,
            "planned_rr": plan.risk_reward,
            "htf_alignment": alignment,
            "htf_agreement_ratio": agreement_ratio,
            "htf_aligned": htf_aligned,
            "htf_1h_bias": h1,
            "htf_4h_bias": h4,
            "htf_1d_bias": d1,
            "htf_trend_strength": agreement_ratio,
            "triggered": triggered,
            "outcome": outcome,
            "r_multiple": float(sim.get("r_multiple", 0.0)) if triggered else None,
            "mfe_r": float(sim.get("max_favorable_r", 0.0)) if triggered else None,
            "mae_r": float(sim.get("max_adverse_r", 0.0)) if triggered else None,
            "entry_index": sim.get("entry_index"),
            # --- Exact-cost accounting: recompute realized R at ANY bps downstream ---
            #   r_net(target_bps) = r_multiple + (entry_price/risk_per_r) * (cost_bps - target_bps) / 10000
            "entry_price": sim.get("entry_price"),
            "stop_price": float(plan.invalidation) if plan.invalidation is not None else None,
            "risk_per_r": (abs(float(sim["entry_price"]) - float(plan.invalidation))
                           if (triggered and sim.get("entry_price") is not None and plan.invalidation is not None)
                           else None),
            "cost_bps": float(args.cost_bps),
            # --- Enriched continuous features ---
            "displacement_score": round(displacement_score, 3),
            "break_strength": break_strength,
            "atr_at_decision": round(atr_at_decision, 4),
            "atr_pct": round(atr_pct, 6),
            "adx_at_decision": round(adx_at_decision, 3),
            "premium_discount_ratio": round(pd_ratio, 3),
            "sweep_depth_atr": round(sweep_depth, 3),
            "sweep_recency_bars": sweep_recency,
            "structure_event_density": structure_density,
            "body_ratio_at_decision": round(body_ratio, 3),
            "range_pct_at_decision": round(range_pct, 6),
            "hour_utc": hour_utc,
            "day_of_week": day_of_week,
            "minute_of_session": minute_of_session,
            "is_killzone": is_killzone,
            # --- Liquidity significance of the swept level (Phase 2) ---
            "swept_level": round(swept_level, 5) if swept_level is not None else None,
            "swept_is_equal_cluster": swept_is_equal_cluster,
            "swept_touch_count": swept_touch_count,
            "swept_htf_confluence": swept_htf_confluence,
            "swept_round_prox": round(swept_round_prox, 5),
            "liquidity_significance": liquidity_significance,
            "dist_htf_atr": round(dist_htf_atr, 3) if dist_htf_atr is not None else None,
            "dist_htf_r": round(dist_htf_r, 3) if dist_htf_r is not None else None,
        }
        for key in CHECKLIST_KEYS:
            row[f"chk_{key}"] = bool(plan.checklist.get(key, False))
        rows.append(row)
        index += args.decision_step

    return rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build SMC research dataset (features + mechanical outcomes, gates off).")
    p.add_argument("--ohlcv", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--rules")
    p.add_argument("--output", required=True, help="Output CSV path.")
    p.add_argument("--use-htf-bias", choices=["off", "on"], default="on")
    p.add_argument("--poi-selection", choices=["balanced", "nearest", "best_location"], default="balanced")
    p.add_argument("--entry-wait-bars", type=int, default=24)
    p.add_argument("--max-hold-bars", type=int, default=96)
    p.add_argument("--cost-bps", type=float, default=4.0)
    p.add_argument("--entry-mode", choices=["boundary", "midpoint"], default="boundary")
    p.add_argument("--warmup-bars", type=int, default=400)
    p.add_argument("--decision-step", type=int, default=4)
    p.add_argument("--limit-bars", type=int)
    p.add_argument("--decision-start", help="Only emit decisions at or after this timestamp/date.")
    p.add_argument("--decision-end", help="Only emit decisions at or before this timestamp/date.")
    p.add_argument("--max-decisions", type=int, help="Cap sampled decision bars for quick research passes.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.decision_step % 96 == 0:
        print(
            "WARNING: --decision-step is a multiple of 96 15m bars, so every sampled decision "
            "lands at the same UTC time of day. Use a non-divisor such as 193 for session-balanced research.",
            file=sys.stderr,
        )
    rows = build_rows(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        out.write_text("", encoding="utf-8")
        print("No rows produced.")
        return
    fieldnames = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    triggered = sum(1 for r in rows if r["triggered"])
    print(f"[{args.symbol}] wrote {len(rows)} setups ({triggered} triggered) to {out}  @ {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
