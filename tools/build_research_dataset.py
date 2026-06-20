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
from tools.backtest_smc_elite import simulate_trade

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
        h1 = _htf_bias(_visible_htf_tail(precomputed["1h"], "1h", decision_time, config.lookback_bars), config)
        h4 = _htf_bias(_visible_htf_tail(precomputed["4h"], "4h", decision_time, config.lookback_bars), config)
        d1 = _htf_bias(_visible_htf_tail(precomputed["1d"], "1d", decision_time, config.lookback_bars), config)
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

        sim, _resume = simulate_trade(
            df=df, signal_index=index, direction=plan.direction,
            entry_low=plan.entry_low, entry_high=plan.entry_high,
            invalidation=plan.invalidation, target=plan.targets[0],
            entry_wait_bars=args.entry_wait_bars, max_hold_bars=args.max_hold_bars,
            cost_bps=args.cost_bps, entry_mode=args.entry_mode,
        )
        outcome = sim.get("outcome", "unknown")
        triggered = sim.get("entry_index") is not None and not outcome.startswith("missed") and outcome != "invalid_geometry"
        atr_pct = None
        close = float(df.at[index, "close"])
        htf_aligned = plan.direction in {"bullish", "bearish"} and alignment == plan.direction

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
            "planned_rr": plan.risk_reward,
            "htf_alignment": alignment,
            "htf_agreement_ratio": agreement_ratio,
            "htf_aligned": htf_aligned,
            "triggered": triggered,
            "outcome": outcome,
            "r_multiple": float(sim.get("r_multiple", 0.0)) if triggered else None,
            "mfe_r": float(sim.get("max_favorable_r", 0.0)) if triggered else None,
            "mae_r": float(sim.get("max_adverse_r", 0.0)) if triggered else None,
            "entry_index": sim.get("entry_index"),
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
