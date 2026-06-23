#!/usr/bin/env python3
"""Simulate managed trades with dynamic rules.

This module replaces the basic `simulate_trade` with a managed version that
includes logic like trailing to breakeven after a certain R, and time-based exits,
which are crucial to protecting the win rate and achieving 65%+ win rate at 3R.
"""
from __future__ import annotations
from typing import Any
import pandas as pd

def simulate_managed_trade(
    df: pd.DataFrame,
    signal_index: int,
    direction: str,
    entry_low: float | None,
    entry_high: float | None,
    invalidation: float | None,
    target: float | None,
    entry_wait_bars: int,
    max_hold_bars: int,
    cost_bps: float,
    entry_mode: str,
    breakeven_r: float = 1.5,
    time_exit_bars: int = 48, # 12 hours on a 15m chart
) -> tuple[dict[str, Any], int]:
    from tools.backtest_smc_elite import _invalid_geometry, choose_entry_price, _timestamp
    
    if entry_low is None or entry_high is None or invalidation is None or target is None:
        return {"outcome": "invalid_geometry", "notes": "missing entry, stop, or target"}, signal_index + 1

    entry_low, entry_high = sorted([float(entry_low), float(entry_high)])
    entry_price = choose_entry_price(direction, entry_low, entry_high, entry_mode)
    initial_stop = float(invalidation)
    target = float(target)
    geometry_issue = _invalid_geometry(direction, entry_price, initial_stop, target)
    if geometry_issue:
        return {"outcome": "invalid_geometry", "entry_price": entry_price, "notes": geometry_issue}, signal_index + 1

    entry_index: int | None = None
    entry_search_end = min(len(df) - 1, signal_index + entry_wait_bars)
    for index in range(signal_index + 1, entry_search_end + 1):
        low = float(df.at[index, "low"])
        high = float(df.at[index, "high"])
        if low <= entry_high and high >= entry_low:
            entry_index = index
            break

    if entry_index is None:
        return {
            "entry_price": entry_price,
            "outcome": "missed_entry",
            "notes": f"entry zone not touched within {entry_wait_bars} bars",
        }, entry_search_end + 1

    risk = entry_price - initial_stop if direction == "bullish" else initial_stop - entry_price
    if risk <= 0:
        return {"entry_price": entry_price, "outcome": "invalid_geometry", "notes": "non-positive risk"}, entry_index + 1

    max_favorable_r = 0.0
    max_adverse_r = 0.0
    exit_index: int | None = None
    exit_price: float | None = None
    outcome = "timeout"
    hold_end = min(len(df) - 1, entry_index + max_hold_bars)
    
    stop_loss = initial_stop
    stop_moved_to_be = False

    for index in range(entry_index, hold_end + 1):
        low = float(df.at[index, "low"])
        high = float(df.at[index, "high"])
        
        bars_held = index - entry_index
        if bars_held >= time_exit_bars:
            exit_index = index
            exit_price = float(df.at[index, "close"])
            outcome = "time_exit"
            break
            
        if direction == "bullish":
            current_r = (high - entry_price) / risk
            max_favorable_r = max(max_favorable_r, current_r)
            max_adverse_r = min(max_adverse_r, (low - entry_price) / risk)
            
            # Trail to breakeven + costs if we reached breakeven_r
            if not stop_moved_to_be and max_favorable_r >= breakeven_r:
                stop_loss = entry_price + (entry_price * (cost_bps/10000.0))
                stop_moved_to_be = True
                
            hit_stop = low <= stop_loss
            hit_target = high >= target
        else:
            current_r = (entry_price - low) / risk
            max_favorable_r = max(max_favorable_r, current_r)
            max_adverse_r = min(max_adverse_r, (entry_price - high) / risk)
            
            # Trail to breakeven + costs if we reached breakeven_r
            if not stop_moved_to_be and max_favorable_r >= breakeven_r:
                stop_loss = entry_price - (entry_price * (cost_bps/10000.0))
                stop_moved_to_be = True
                
            hit_stop = high >= stop_loss
            hit_target = low <= target

        if hit_stop and hit_target:
            exit_index = index
            exit_price = stop_loss
            outcome = "loss_ambiguous"
            break
        if hit_stop:
            exit_index = index
            exit_price = stop_loss
            outcome = "breakeven" if stop_moved_to_be else "loss"
            break
        if hit_target:
            exit_index = index
            exit_price = target
            outcome = "win"
            break

    if exit_index is None:
        exit_index = hold_end
        exit_price = float(df.at[hold_end, "close"])

    if direction == "bullish":
        r_multiple = (exit_price - entry_price) / risk
    else:
        r_multiple = (entry_price - exit_price) / risk
    cost_r = (entry_price * (cost_bps / 10_000.0)) / risk
    r_multiple -= cost_r

    if outcome == "timeout":
        if r_multiple > 0.05:
            outcome = "timeout_win"
        elif r_multiple < -0.05:
            outcome = "timeout_loss"
        else:
            outcome = "timeout_flat"
            
    notes = f"cost_r={cost_r:.4f}"
    if stop_moved_to_be:
        notes += "; trailed to BE"

    return {
        "entry_price": round(entry_price, 8),
        "entry_index": entry_index,
        "entry_time": _timestamp(df, entry_index),
        "exit_index": exit_index,
        "exit_time": _timestamp(df, exit_index),
        "outcome": outcome,
        "r_multiple": round(r_multiple, 4),
        "max_favorable_r": round(max_favorable_r, 4),
        "max_adverse_r": round(max_adverse_r, 4),
        "notes": notes,
    }, exit_index + 1
