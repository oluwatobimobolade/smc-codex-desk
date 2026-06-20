#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk import analyze_dataframe, load_rule_config
from smc_desk.engine import load_ohlcv_csv


@dataclass
class SimulatedTrade:
    signal_index: int
    signal_time: str
    direction: str
    verdict: str
    setup_grade: str
    confluence_score: float
    entry_low: float | None
    entry_high: float | None
    entry_price: float | None
    invalidation: float | None
    target: float | None
    planned_rr: float | None
    entry_index: int | None
    entry_time: str | None
    exit_index: int | None
    exit_time: str | None
    outcome: str
    r_multiple: float
    max_favorable_r: float
    max_adverse_r: float
    notes: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay the SMC Elite engine on historical OHLCV without future leakage.")
    parser.add_argument("--ohlcv", required=True, help="CSV with timestamp, open, high, low, close, volume columns.")
    parser.add_argument("--symbol", required=True, help="Instrument symbol, for example BTCUSDT.")
    parser.add_argument("--timeframe", required=True, help="Timeframe label, for example 15m.")
    parser.add_argument("--rules", help="Optional rules JSON path.")
    parser.add_argument("--bias", help="Optional fixed bias hint: bullish or bearish.")
    parser.add_argument("--output-dir", default="backtests/latest", help="Directory for summary and trade CSV.")
    parser.add_argument("--warmup-bars", type=int, default=250, help="Bars required before the first decision.")
    parser.add_argument("--entry-wait-bars", type=int, default=8, help="Bars after a signal allowed for entry-zone fill.")
    parser.add_argument("--max-hold-bars", type=int, default=96, help="Bars after fill before timeout exit.")
    parser.add_argument("--cost-bps", type=float, default=4.0, help="Round-trip spread/slippage cost in basis points.")
    parser.add_argument("--decision-step", type=int, default=1, help="Evaluate every N bars.")
    parser.add_argument("--limit-bars", type=int, help="Optional cap after warmup for quick smoke tests.")
    parser.add_argument("--near-miss-min", type=float, default=0.62, help="Minimum confluence to record a non-executed near miss.")
    parser.add_argument(
        "--watch-entry",
        choices=["off", "price-only"],
        default="off",
        help="Diagnostic only: also simulate Watch setups that only wait for price to return to the POI.",
    )
    parser.add_argument(
        "--entry-mode",
        choices=["boundary", "midpoint"],
        default="boundary",
        help="boundary is conservative; midpoint assumes a deeper limit fill inside the POI.",
    )
    return parser.parse_args()


def _timestamp(df: pd.DataFrame, index: int) -> str:
    return pd.Timestamp(df.at[index, "timestamp"]).isoformat()


def choose_entry_price(direction: str, entry_low: float, entry_high: float, mode: str) -> float:
    if mode == "midpoint":
        return (entry_low + entry_high) / 2.0
    if direction == "bullish":
        return entry_high
    return entry_low


def _invalid_geometry(direction: str, entry: float, stop: float, target: float) -> str | None:
    if direction == "bullish":
        if stop >= entry:
            return "long stop is not below entry"
        if target <= entry:
            return "long target is not above entry"
    elif direction == "bearish":
        if stop <= entry:
            return "short stop is not above entry"
        if target >= entry:
            return "short target is not below entry"
    else:
        return "direction is not tradable"
    return None


def simulate_trade(
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
) -> tuple[dict[str, Any], int]:
    if entry_low is None or entry_high is None or invalidation is None or target is None:
        return {"outcome": "invalid_geometry", "notes": "missing entry, stop, or target"}, signal_index + 1

    entry_low, entry_high = sorted([float(entry_low), float(entry_high)])
    entry_price = choose_entry_price(direction, entry_low, entry_high, entry_mode)
    stop = float(invalidation)
    target = float(target)
    geometry_issue = _invalid_geometry(direction, entry_price, stop, target)
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

    risk = entry_price - stop if direction == "bullish" else stop - entry_price
    if risk <= 0:
        return {"entry_price": entry_price, "outcome": "invalid_geometry", "notes": "non-positive risk"}, entry_index + 1

    max_favorable_r = 0.0
    max_adverse_r = 0.0
    exit_index: int | None = None
    exit_price: float | None = None
    outcome = "timeout"
    hold_end = min(len(df) - 1, entry_index + max_hold_bars)

    for index in range(entry_index, hold_end + 1):
        low = float(df.at[index, "low"])
        high = float(df.at[index, "high"])
        if direction == "bullish":
            max_favorable_r = max(max_favorable_r, (high - entry_price) / risk)
            max_adverse_r = min(max_adverse_r, (low - entry_price) / risk)
            hit_stop = low <= stop
            hit_target = high >= target
        else:
            max_favorable_r = max(max_favorable_r, (entry_price - low) / risk)
            max_adverse_r = min(max_adverse_r, (entry_price - high) / risk)
            hit_stop = high >= stop
            hit_target = low <= target

        if hit_stop and hit_target:
            exit_index = index
            exit_price = stop
            outcome = "loss_ambiguous"
            break
        if hit_stop:
            exit_index = index
            exit_price = stop
            outcome = "loss"
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
        "notes": f"cost_r={cost_r:.4f}",
    }, exit_index + 1


def make_trade_row(
    df: pd.DataFrame,
    signal_index: int,
    plan: Any,
    simulation: dict[str, Any],
) -> SimulatedTrade:
    return SimulatedTrade(
        signal_index=signal_index,
        signal_time=_timestamp(df, signal_index),
        direction=plan.direction,
        verdict=plan.verdict,
        setup_grade=plan.setup_grade,
        confluence_score=float(plan.confluence_score),
        entry_low=plan.entry_low,
        entry_high=plan.entry_high,
        entry_price=simulation.get("entry_price"),
        invalidation=plan.invalidation,
        target=plan.targets[0] if plan.targets else None,
        planned_rr=plan.risk_reward,
        entry_index=simulation.get("entry_index"),
        entry_time=simulation.get("entry_time"),
        exit_index=simulation.get("exit_index"),
        exit_time=simulation.get("exit_time"),
        outcome=simulation.get("outcome", "unknown"),
        r_multiple=float(simulation.get("r_multiple", 0.0)),
        max_favorable_r=float(simulation.get("max_favorable_r", 0.0)),
        max_adverse_r=float(simulation.get("max_adverse_r", 0.0)),
        notes=simulation.get("notes", ""),
    )


def update_diagnostics(plan: Any, verdict_counts: Counter, grade_counts: Counter, missing_checks: Counter) -> None:
    verdict_counts[plan.verdict] += 1
    grade_counts[plan.setup_grade] += 1
    for key, value in plan.checklist.items():
        if not value:
            missing_checks[key] += 1


def summarize(trades: list[SimulatedTrade], diagnostics: dict[str, Any]) -> dict[str, Any]:
    entered = [trade for trade in trades if trade.entry_index is not None and not trade.outcome.startswith("missed")]
    wins = [trade for trade in entered if trade.r_multiple > 0.05]
    losses = [trade for trade in entered if trade.r_multiple < -0.05]
    flats = [trade for trade in entered if -0.05 <= trade.r_multiple <= 0.05]
    total_r = round(sum(trade.r_multiple for trade in entered), 4)
    gross_win_r = sum(trade.r_multiple for trade in wins)
    gross_loss_r = abs(sum(trade.r_multiple for trade in losses))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in entered:
        equity += trade.r_multiple
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)

    summary = {
        **diagnostics,
        "signals": len(trades),
        "execute_signals": sum(1 for trade in trades if trade.verdict == "Execute"),
        "watch_retrace_signals": sum(1 for trade in trades if trade.verdict == "Watch Retrace"),
        "watch_signals": sum(1 for trade in trades if trade.verdict == "Watch"),
        "entered_trades": len(entered),
        "missed_entries": sum(1 for trade in trades if trade.outcome == "missed_entry"),
        "invalid_signals": sum(1 for trade in trades if trade.outcome == "invalid_geometry"),
        "wins": len(wins),
        "losses": len(losses),
        "flat_or_timeout": len(flats),
        "win_rate": round(len(wins) / len(entered), 4) if entered else 0.0,
        "avg_r": round(total_r / len(entered), 4) if entered else 0.0,
        "total_r": total_r,
        "max_drawdown_r": round(max_drawdown, 4),
        "profit_factor": round(gross_win_r / gross_loss_r, 4) if gross_loss_r else None,
        "expectancy_note": "Meaningful only after a large out-of-sample sample; use this run as diagnostics first.",
    }
    summary["loopholes_found"] = diagnose_loopholes(summary)
    return summary


def diagnose_loopholes(summary: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if summary["signals"] == 0:
        issues.append("No tradeable candidates. The rule stack may be too strict, or the analyzer needs multi-timeframe context.")
    elif summary.get("execute_signals", 0) == 0 and summary.get("watch_retrace_signals", 0):
        issues.append("Trades came only from Watch retraces. The engine should separate confirmation events from pending limit orders more explicitly.")
    if summary["entered_trades"] == 0 and summary["signals"] > 0:
        issues.append("Signals did not fill. Entry-zone logic may be too narrow or too late after confirmation.")
    if summary["entered_trades"] and summary["avg_r"] <= 0:
        issues.append("Executed sample has non-positive expectancy after costs; do not trust this rule mix live yet.")
    missing = summary.get("missing_check_counts", {})
    if missing:
        top_missing = next(iter(missing))
        issues.append(f"Most common blocker: {top_missing}. This is the first rule to inspect before loosening anything.")
    if summary["signals"] < 20:
        issues.append("Sample has fewer than 20 signals. Treat results as a smoke test, not proof.")
    return issues


def write_csv(path: Path, trades: list[SimulatedTrade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(trades[0]).keys()) if trades else list(SimulatedTrade.__annotations__))
        writer.writeheader()
        for trade in trades:
            writer.writerow(asdict(trade))


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# {summary['symbol']} {summary['timeframe']} SMC Elite Backtest",
        "",
        f"Generated: {summary['generated_at']}",
        f"Period: {summary['period_start']} to {summary['period_end']}",
        f"Decision bars: {summary['decision_bars']}",
        "",
        "## Result",
        f"- Tradeable candidates: {summary['signals']}",
        f"- Literal Execute signals: {summary['execute_signals']}",
        f"- Watch retrace signals: {summary['watch_retrace_signals']}",
        f"- Entered trades: {summary['entered_trades']}",
        f"- Win rate: {summary['win_rate']:.2%}",
        f"- Total R: {summary['total_r']}",
        f"- Avg R: {summary['avg_r']}",
        f"- Max drawdown R: {summary['max_drawdown_r']}",
        "",
        "## Rule Diagnostics",
    ]
    for key, value in summary.get("missing_check_counts", {}).items():
        lines.append(f"- {key}: missing {value} times")
    if not summary.get("missing_check_counts"):
        lines.append("- No missing-check diagnostics recorded.")
    lines.extend(["", "## Loopholes Found"])
    lines.extend(f"- {issue}" for issue in summary.get("loopholes_found", []))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_backtest(args: argparse.Namespace) -> tuple[dict[str, Any], list[SimulatedTrade], list[dict[str, Any]]]:
    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(args.ohlcv)
    if len(df) <= args.warmup_bars + args.max_hold_bars:
        raise ValueError("Not enough candles for warmup plus max hold window.")

    last_decision_index = len(df) - args.max_hold_bars - 1
    if args.limit_bars:
        last_decision_index = min(last_decision_index, args.warmup_bars + args.limit_bars)

    trades: list[SimulatedTrade] = []
    near_misses: list[dict[str, Any]] = []
    verdict_counts: Counter = Counter()
    grade_counts: Counter = Counter()
    missing_checks: Counter = Counter()
    decision_bars = 0
    index = args.warmup_bars

    while index <= last_decision_index:
        history = df.iloc[: index + 1]
        analysis, _ = analyze_dataframe(
            df=history,
            symbol=args.symbol,
            timeframe=args.timeframe,
            config=config,
            bias_hint=args.bias,
            notes="Backtest replay: candles after this timestamp are hidden from the analyzer.",
            input_type="ohlcv",
        )
        plan = analysis.trade_plan
        decision_bars += 1
        update_diagnostics(plan, verdict_counts, grade_counts, missing_checks)

        missing_keys = [key for key, value in plan.checklist.items() if not value]
        is_watch_retrace = (
            args.watch_entry == "price-only"
            and (plan.verdict == "Watch Retrace"
                 or (plan.verdict == "Watch" and missing_keys == ["price_at_or_near_poi"]))
        )
        if plan.verdict == "Execute" or is_watch_retrace:
            simulation, resume_index = simulate_trade(
                df=df,
                signal_index=index,
                direction=plan.direction,
                entry_low=plan.entry_low,
                entry_high=plan.entry_high,
                invalidation=plan.invalidation,
                target=plan.targets[0] if plan.targets else None,
                entry_wait_bars=args.entry_wait_bars,
                max_hold_bars=args.max_hold_bars,
                cost_bps=args.cost_bps,
                entry_mode=args.entry_mode,
            )
            if is_watch_retrace:
                simulation["notes"] = f"watch_retrace_pending_poi; {simulation.get('notes', '')}".strip()
            trades.append(make_trade_row(df, index, plan, simulation))
            index = max(index + args.decision_step, resume_index)
            continue

        if plan.verdict == "Watch" or plan.confluence_score >= args.near_miss_min:
            selected_poi = plan.selected_poi
            near_misses.append(
                {
                    "index": index,
                    "time": _timestamp(df, index),
                    "verdict": plan.verdict,
                    "grade": plan.setup_grade,
                    "direction": plan.direction,
                    "confluence_score": plan.confluence_score,
                    "selected_poi": selected_poi.label if selected_poi else None,
                    "missing_checks": [key for key, value in plan.checklist.items() if not value],
                    "warnings": plan.warnings[:3],
                }
            )
            near_misses = sorted(near_misses, key=lambda item: item["confluence_score"], reverse=True)[:75]

        index += args.decision_step

    diagnostics = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(Path(args.ohlcv).resolve()),
        "period_start": _timestamp(df, 0),
        "period_end": _timestamp(df, len(df) - 1),
        "bars": int(len(df)),
        "decision_bars": decision_bars,
        "warmup_bars": args.warmup_bars,
        "entry_wait_bars": args.entry_wait_bars,
        "max_hold_bars": args.max_hold_bars,
        "cost_bps": args.cost_bps,
        "entry_mode": args.entry_mode,
        "watch_entry": args.watch_entry,
        "verdict_counts": dict(verdict_counts.most_common()),
        "grade_counts": dict(grade_counts.most_common()),
        "missing_check_counts": dict(missing_checks.most_common()),
        "near_miss_count": len(near_misses),
    }
    return summarize(trades, diagnostics), trades, near_misses


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary, trades, near_misses = run_backtest(args)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "near_misses.json").write_text(json.dumps(near_misses, indent=2), encoding="utf-8")
    write_csv(output_dir / "trades.csv", trades)
    write_markdown(output_dir / "summary.md", summary)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
