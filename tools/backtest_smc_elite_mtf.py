#!/usr/bin/env python3
"""Multi-timeframe SMC Elite backtester.

Runs the deterministic engine on 15m execution data while computing
higher-timeframe (1H / 4H / 1D) context for every decision bar. No future
leakage: at decision time `t`, only HTF candles whose close time is at or
before `t` are visible, and the 15m slice ends at `t`.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, assert_not_in_holdout
from smc_desk.mtf import build_mtf_snapshot, derive_htf_consensus_bias, precompute_htf_series, snapshot_to_dict
from smc_desk.rules import load_rule_config
from tools.backtest_smc_elite import (
    SimulatedTrade,
    choose_entry_price,
    make_trade_row,
    simulate_trade,
    summarize,
    update_diagnostics,
    write_csv,
)


@dataclass
class MtfDecision:
    decision_index: int
    decision_time: str
    bars_visible_15m: int
    direction: str
    verdict: str
    setup_grade: str
    confluence_score: float
    selected_poi_label: str | None
    htf_poi_timeframe: str | None
    htf_poi_label: str | None
    htf_poi_state: str | None
    htf_poi_low: float | None
    htf_poi_high: float | None
    htf_poi_distance_atr: float | None
    entry_low: float | None
    entry_high: float | None
    invalidation: float | None
    target: float | None
    planned_rr: float | None
    risk_reward: float | None
    checklist: dict[str, bool]
    mtf: dict[str, Any]
    htf_alignment: str
    htf_agreement_ratio: float
    htf_filter_passed: bool
    bias_hint_used: str
    fusion_verdict: str | None = None
    fusion_direction: str | None = None
    fusion_confidence: float | None = None
    trade_outcome: str | None = None
    trade_r_multiple: float | None = None
    trade_entry_time: str | None = None
    trade_exit_time: str | None = None
    trade_entry_index: int | None = None
    trade_exit_index: int | None = None
    trade_notes: str | None = None
    blockers: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-timeframe SMC Elite backtester.")
    parser.add_argument("--ohlcv", required=True, help="15m OHLCV CSV with timestamp, open, high, low, close, volume.")
    parser.add_argument("--symbol", required=True, help="Instrument symbol, e.g. BTCUSDT.")
    parser.add_argument("--timeframe", default="15m", help="Execution timeframe label.")
    parser.add_argument("--rules", help="Optional rules JSON path.")
    parser.add_argument("--use-htf-bias", choices=["off", "on"], default="on", help="Feed HTF 1H bias to the 15m analyzer as bias_hint.")
    parser.add_argument("--require-htf-alignment", choices=["off", "on"], default="on", help="Only allow 15m setups that align with the HTF agreement.")
    parser.add_argument("--htf-min-agreement", type=float, default=0.5, help="Minimum HTF agreement ratio to allow a 15m setup (0..1).")
    parser.add_argument("--poi-selection", choices=["balanced", "nearest", "best_location"], default="balanced")
    parser.add_argument("--entry-wait-bars", type=int, default=24, help="Bars a pending POI may stay open for entry.")
    parser.add_argument("--max-hold-bars", type=int, default=96, help="Bars after fill before timeout exit.")
    parser.add_argument("--cost-bps", type=float, default=4.0)
    parser.add_argument("--entry-mode", choices=["boundary", "midpoint"], default="boundary")
    parser.add_argument("--warmup-bars", type=int, default=400, help="Bars required before the first decision (covers HTF warmup).")
    parser.add_argument("--decision-step", type=int, default=1)
    parser.add_argument("--limit-bars", type=int, help="Optional cap after warmup for quick smoke tests.")
    parser.add_argument("--max-decisions", type=int, help="Optional cap on total decision bars.")
    parser.add_argument("--run-name", required=True, help="Short label for this run, e.g. baseline_mtf_24wait.")
    parser.add_argument("--run-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"), help="Folder date for the run.")
    parser.add_argument("--data-manifest", help="Optional path to a JSON file with data provenance to copy into data_manifest.json.")
    parser.add_argument("--hypothesis", default="", help="One-line hypothesis for this run, used in research_notes.")
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--allow-holdout", action="store_true", help="Only for deliberate final evaluation on a locked holdout.")
    parser.add_argument(
        "--include-watch-retrace",
        choices=["off", "on"],
        default="off",
        help="Diagnostic only: treat 'Watch Retrace' as a tradeable pending POI.",
    )
    parser.add_argument(
        "--fusion",
        action="store_true",
        help="Run the experimental Fusion Engine in shadow mode.",
    )
    return parser.parse_args()


def _timestamp(df: pd.DataFrame, index: int) -> str:
    return pd.Timestamp(df.at[index, "timestamp"]).isoformat()


def _blockers(plan: Any) -> list[str]:
    return [key.replace("_", " ") for key, value in plan.checklist.items() if not value]


def _aligns_with_htf(direction: str, snapshot_dict: dict[str, Any]) -> bool:
    if direction not in {"bullish", "bearish"}:
        return False
    return snapshot_dict["alignment"] == direction


def run_mtf_backtest(args: argparse.Namespace) -> tuple[dict[str, Any], list[SimulatedTrade], list[MtfDecision], list[dict[str, Any]]]:
    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(args.ohlcv)
    if len(df) <= args.warmup_bars + args.max_hold_bars:
        raise ValueError("Not enough candles for warmup plus max hold window.")

    last_decision_index = len(df) - args.max_hold_bars - 1
    if args.limit_bars is not None:
        last_decision_index = min(last_decision_index, args.warmup_bars + args.limit_bars)
    if args.max_decisions is not None and args.max_decisions <= 0:
        raise ValueError("--max-decisions must be positive")
    if last_decision_index < args.warmup_bars:
        raise ValueError("No valid decision bars after warmup/max-hold constraints.")
    holdout_matches = assert_not_in_holdout(
        start=pd.Timestamp(df.at[args.warmup_bars, "timestamp"]),
        end=pd.Timestamp(df.at[last_decision_index, "timestamp"]),
        symbol=args.symbol,
        action="backtest",
        policy_path=args.holdout_policy,
        allow_holdout=args.allow_holdout,
    )

    precomputed = precompute_htf_series(df)

    trades: list[SimulatedTrade] = []
    near_misses: list[dict[str, Any]] = []
    decisions: list[MtfDecision] = []
    verdict_counts: Counter = Counter()
    grade_counts: Counter = Counter()
    missing_checks: Counter = Counter()
    htf_filter_blocked = 0
    htf_filter_allowed = 0
    direction_mismatches: Counter = Counter()
    blocker_freq: Counter = Counter()
    index = args.warmup_bars
    decision_bars = 0
    
    if args.fusion:
        from smc_desk.sequence_memory import SequenceMemory, BarSnapshot
        from smc_desk.intent_detector import IntentDetector, MarketContext
        from smc_desk.features import detect_failed_breakout, detect_vertical_spike_trap, regime_features
        from smc_desk.fusion_engine import FusionEngine
        sequence_memory = SequenceMemory()
        intent_detector = IntentDetector()
        fusion_engine = FusionEngine()
        last_sm_index = -1

    while index <= last_decision_index:
        if args.max_decisions is not None and decision_bars >= args.max_decisions:
            break

        decision_time = pd.Timestamp(df.at[index, "timestamp"])
        snapshot = build_mtf_snapshot(df, decision_time, config, precomputed=precomputed)
        snap_dict = snapshot_to_dict(snapshot)

        history_15m = df.iloc[: index + 1].copy()

        bias_hint: str | None = None
        consensus_bias = derive_htf_consensus_bias(snap_dict)
        if args.use_htf_bias == "on" and consensus_bias in {"bullish", "bearish"}:
            bias_hint = consensus_bias

        analysis, _ = analyze_dataframe(
            df=history_15m,
            symbol=args.symbol,
            timeframe=args.timeframe,
            config=config,
            bias_hint=bias_hint,
            notes=f"MTF backtest: HTF alignment {snap_dict['alignment']} @ {snap_dict['agreement_ratio']:.2f}",
            input_type="ohlcv",
            poi_selection=args.poi_selection,
            htf_poi=snapshot.selected_htf_poi,
        )
        plan = analysis.trade_plan
        decision_bars += 1
        update_diagnostics(plan, verdict_counts, grade_counts, missing_checks)
        
        fusion_verdict = None
        fusion_direction = None
        fusion_confidence = None
        
        if args.fusion:
            for i in range(last_sm_index + 1, index + 1):
                row = df.iloc[i]
                sequence_memory.process_bar(BarSnapshot(
                    index=i,
                    timestamp=str(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                ))
            last_sm_index = index
            
            records = history_15m.to_dict("records")
            spike = detect_vertical_spike_trap(records)
            failed_breakout = detect_failed_breakout(records)
            pattern_dicts = []
            if spike.get("detected"):
                pattern_dicts.append({
                    "pattern_type": "vertical_spike_trap",
                    "direction": spike["direction"],
                    "confidence": spike["score"],
                    "invalidates_bias": "bullish" if spike["direction"] == "bullish" else "bearish",
                    "metadata": spike.get("metadata", {}),
                })
            if failed_breakout.get("detected"):
                pattern_dicts.append({
                    "pattern_type": "failed_breakout",
                    "direction": failed_breakout["direction"],
                    "confidence": failed_breakout["score"],
                    "invalidates_bias": failed_breakout["direction"],
                    "metadata": failed_breakout.get("metadata", {}),
                })

            regime = regime_features(records)
            context = MarketContext(
                symbol=args.symbol,
                timeframe=args.timeframe,
                regime_label=regime.get("regime_label", "unknown"),
            )
            intent_result = intent_detector.detect_intent(
                sequence_memory=sequence_memory,
                visual_patterns=pattern_dicts,
                context=context,
            )
            fusion_result = fusion_engine.fuse(
                engine_result=analysis,
                sequence_memory=sequence_memory,
                intent_result=intent_result,
                visual_patterns=pattern_dicts,
                context=context,
            )
            fusion_verdict = fusion_result.recommended_verdict
            fusion_direction = fusion_result.recommended_direction
            fusion_confidence = fusion_result.fused_confidence

        blockers = _blockers(plan)
        for blocker in blockers:
            blocker_freq[blocker] += 1

        htf_aligns = _aligns_with_htf(plan.direction, snap_dict)
        htf_filter_passed = (
            args.require_htf_alignment == "off"
            or (
                snap_dict["agreement_ratio"] >= args.htf_min_agreement
                and htf_aligns
                and plan.direction in {"bullish", "bearish"}
            )
        )
        if plan.direction in {"bullish", "bearish"} and not htf_filter_passed and args.require_htf_alignment == "on":
            htf_filter_blocked += 1
            if snap_dict["alignment"] != "neutral" and plan.direction != snap_dict["alignment"]:
                direction_mismatches[(plan.direction, snap_dict["alignment"])] += 1
        else:
            htf_filter_allowed += 1

        selected_poi = plan.selected_poi
        htf_poi = plan.selected_htf_poi
        is_watch_retrace = plan.verdict == "Watch Retrace"
        should_trade = (
            plan.verdict == "Execute"
            or (is_watch_retrace and args.include_watch_retrace == "on")
        )

        decision_record = MtfDecision(
            decision_index=index,
            decision_time=_timestamp(df, index),
            bars_visible_15m=int(len(history_15m)),
            direction=plan.direction,
            verdict=plan.verdict,
            setup_grade=plan.setup_grade,
            confluence_score=float(plan.confluence_score),
            selected_poi_label=selected_poi.label if selected_poi else None,
            htf_poi_timeframe=htf_poi.timeframe if htf_poi else None,
            htf_poi_label=htf_poi.zone.label if htf_poi else None,
            htf_poi_state=htf_poi.state if htf_poi else None,
            htf_poi_low=htf_poi.zone.low if htf_poi else None,
            htf_poi_high=htf_poi.zone.high if htf_poi else None,
            htf_poi_distance_atr=htf_poi.distance_atr if htf_poi else None,
            entry_low=plan.entry_low,
            entry_high=plan.entry_high,
            invalidation=plan.invalidation,
            target=plan.targets[0] if plan.targets else None,
            planned_rr=plan.risk_reward,
            risk_reward=plan.risk_reward,
            checklist=dict(plan.checklist),
            mtf=snap_dict,
            htf_alignment=snap_dict["alignment"],
            htf_agreement_ratio=float(snap_dict["agreement_ratio"]),
            htf_filter_passed=bool(htf_filter_passed),
            bias_hint_used=bias_hint or "",
            fusion_verdict=fusion_verdict,
            fusion_direction=fusion_direction,
            fusion_confidence=fusion_confidence,
            blockers=blockers,
        )

        if should_trade and htf_filter_passed:
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
            trade_row = make_trade_row(df, index, plan, simulation)
            trades.append(trade_row)
            decision_record.trade_outcome = trade_row.outcome
            decision_record.trade_r_multiple = trade_row.r_multiple
            decision_record.trade_entry_time = trade_row.entry_time
            decision_record.trade_exit_time = trade_row.exit_time
            decision_record.trade_entry_index = trade_row.entry_index
            decision_record.trade_exit_index = trade_row.exit_index
            decision_record.trade_notes = trade_row.notes
            decisions.append(decision_record)
            index = max(index + args.decision_step, resume_index)
            continue

        if (
            plan.confluence_score >= 0.5
            or plan.verdict in {"Watch", "Watch Retrace"}
            or htf_filter_passed
        ):
            near_misses.append(
                {
                    "decision_index": index,
                    "decision_time": _timestamp(df, index),
                    "direction": plan.direction,
                    "verdict": plan.verdict,
                    "setup_grade": plan.setup_grade,
                    "confluence_score": plan.confluence_score,
                    "selected_poi": selected_poi.label if selected_poi else None,
                    "htf_poi": htf_poi.zone.label if htf_poi else None,
                    "htf_poi_state": htf_poi.state if htf_poi else None,
                    "htf_alignment": snap_dict["alignment"],
                    "htf_agreement_ratio": snap_dict["agreement_ratio"],
                    "htf_filter_passed": bool(htf_filter_passed),
                    "missing_checks": blockers,
                    "warnings": plan.warnings[:3],
                }
            )
            near_misses = sorted(near_misses, key=lambda item: item["confluence_score"], reverse=True)[:200]

        decisions.append(decision_record)
        index += args.decision_step

    diagnostics = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "run_name": args.run_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(Path(args.ohlcv).resolve()),
        "period_start": _timestamp(df, 0),
        "period_end": _timestamp(df, len(df) - 1),
        "decision_period_start": _timestamp(df, args.warmup_bars),
        "decision_period_end": _timestamp(df, last_decision_index),
        "bars": int(len(df)),
        "decision_bars": decision_bars,
        "warmup_bars": args.warmup_bars,
        "entry_wait_bars": args.entry_wait_bars,
        "max_hold_bars": args.max_hold_bars,
        "cost_bps": args.cost_bps,
        "entry_mode": args.entry_mode,
        "poi_selection": args.poi_selection,
        "use_htf_bias": args.use_htf_bias,
        "require_htf_alignment": args.require_htf_alignment,
        "htf_min_agreement": args.htf_min_agreement,
        "include_watch_retrace": args.include_watch_retrace,
        "verdict_counts": dict(verdict_counts.most_common()),
        "grade_counts": dict(grade_counts.most_common()),
        "missing_check_counts": dict(missing_checks.most_common()),
        "blocker_frequency": dict(blocker_freq.most_common()),
        "htf_filter_allowed": htf_filter_allowed,
        "htf_filter_blocked": htf_filter_blocked,
        "htf_direction_mismatches": {f"{k[0]}_vs_{k[1]}": v for k, v in direction_mismatches.most_common()},
        "near_miss_count": len(near_misses),
        "hypothesis": args.hypothesis,
        "watch_retrace_count": sum(1 for d in decisions if d.verdict == "Watch Retrace"),
        "watch_count": sum(1 for d in decisions if d.verdict == "Watch"),
        "execute_count": sum(1 for d in decisions if d.verdict == "Execute"),
        "pass_count": sum(1 for d in decisions if d.verdict == "Pass"),
        "fusion_enabled": args.fusion,
        "holdout_windows_touched": [
            {
                "name": window.name,
                "start": window.start.isoformat(),
                "end": None if window.end is None else window.end.isoformat(),
                "reason": window.reason,
            }
            for window in holdout_matches
        ],
    }
    if args.fusion:
        diagnostics["fusion_verdict_counts"] = dict(Counter(d.fusion_verdict for d in decisions).most_common())
        diagnostics["fusion_overrides"] = sum(1 for d in decisions if d.fusion_verdict != d.verdict)
    
    summary = summarize(trades, diagnostics)
    return summary, trades, decisions, near_misses


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _write_decisions_csv(path: Path, decisions: list[MtfDecision]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not decisions:
        path.write_text("decision_index,decision_time\n", encoding="utf-8")
        return
    base = {key: value for key, value in asdict(decisions[0]).items() if key not in {"mtf", "checklist", "blockers"}}
    fieldnames = list(base.keys()) + ["1h_bias", "4h_bias", "1d_bias", "blockers", "checklist"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for d in decisions:
            row = {key: value for key, value in asdict(d).items() if key not in {"mtf", "checklist", "blockers"}}
            mtf = d.mtf
            row["1h_bias"] = mtf.get("1h", {}).get("bias")
            row["4h_bias"] = mtf.get("4h", {}).get("bias")
            row["1d_bias"] = mtf.get("1d", {}).get("bias")
            row["blockers"] = ";".join(d.blockers)
            row["checklist"] = ";".join(f"{k}={v}" for k, v in d.checklist.items())
            writer.writerow(row)


def _write_summary_markdown(path: Path, summary: dict[str, Any], decisions: list[MtfDecision], trades: list[SimulatedTrade], args: argparse.Namespace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entered = [t for t in trades if t.entry_index is not None and not t.outcome.startswith("missed")]
    wins = [t for t in entered if t.r_multiple > 0.05]
    losses = [t for t in entered if t.r_multiple < -0.05]
    lines = [
        f"# {summary['symbol']} {summary['timeframe']} MTF Backtest — {args.run_name}",
        "",
        f"Generated: {summary['generated_at']}",
        f"Period: {summary['period_start']} to {summary['period_end']}",
        f"Decision bars: {summary['decision_bars']}",
        f"HTF bias used: {summary['use_htf_bias']}, HTF alignment required: {summary['require_htf_alignment']} (min agreement {summary['htf_min_agreement']})",
        f"POI selection: {summary['poi_selection']}, entry mode: {summary['entry_mode']}, entry wait: {summary['entry_wait_bars']} bars, max hold: {summary['max_hold_bars']} bars",
        f"Watch Retrace treated as tradeable: {summary['include_watch_retrace']}",
        "",
        f"Hypothesis: {args.hypothesis or '(none)'}",
        "",
        "## Result",
        f"- Tradeable candidates: {summary['signals']}",
        f"- Literal Execute signals: {summary['execute_signals']}",
        f"- Watch Retrace signals: {summary.get('watch_retrace_signals', 0)}",
        f"- Entered trades: {summary['entered_trades']}",
        f"- Wins / losses: {summary['wins']} / {summary['losses']}",
        f"- Win rate: {summary['win_rate']:.2%}",
        f"- Total R: {summary['total_r']}",
        f"- Avg R per entered trade: {summary['avg_r']}",
        f"- Max drawdown R: {summary['max_drawdown_r']}",
        f"- HTF filter allowed/blocked: {summary.get('htf_filter_allowed', 0)} / {summary.get('htf_filter_blocked', 0)}",
    ]
    if args.fusion:
        lines.extend([
            "",
            "## Fusion Shadow Mode",
            f"- Fusion overrides: {summary.get('fusion_overrides', 0)}",
            f"- Fusion verdicts: {summary.get('fusion_verdict_counts', {})}",
        ])
    lines.extend([
        "",
        "## HTF Direction Mismatches",
    ])
    if summary.get("htf_direction_mismatches"):
        for k, v in summary["htf_direction_mismatches"].items():
            lines.append(f"- 15m said {k.split('_vs_')[0]}, HTF said {k.split('_vs_')[1]}: {v} times")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Most Common Blockers"])
    if summary.get("blocker_frequency"):
        for k, v in summary["blocker_frequency"].items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- No blockers recorded.")
    lines.extend(["", "## Verdict Distribution"])
    for k, v in summary.get("verdict_counts", {}).items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Setup Grade Distribution"])
    for k, v in summary.get("grade_counts", {}).items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Loopholes Found"])
    if summary.get("loopholes_found"):
        for issue in summary["loopholes_found"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- None.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_research_notes(path: Path, args: argparse.Namespace, summary: dict[str, Any], decisions: list[MtfDecision]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notes = [
        f"# Research Notes — {args.run_name}",
        "",
        f"Run: {args.run_name}",
        f"Date: {args.run_date}",
        f"Symbol / timeframe: {args.symbol} / {args.timeframe}",
        f"Source CSV: {args.ohlcv}",
        f"Hypothesis: {args.hypothesis or '(none)'}",
        "",
        "## What was tested",
        f"- HTF bias {'enabled' if args.use_htf_bias == 'on' else 'disabled'}.",
        f"- HTF alignment filter {'enabled' if args.require_htf_alignment == 'on' else 'disabled'} with min agreement {args.htf_min_agreement}.",
        f"- POI selection mode: {args.poi_selection}.",
        f"- Entry wait window: {args.entry_wait_bars} bars; max hold {args.max_hold_bars} bars; entry mode {args.entry_mode}.",
        f"- Watch Retrace treated as pending tradeable: {args.include_watch_retrace}.",
        "",
        "## What changed",
        "- This is a separate run folder; original code in `tools/backtest_smc_elite_mtf.py` and `smc_desk/mtf.py` is additive.",
        "",
        "## What was learned",
        f"- Decisions evaluated: {summary['decision_bars']}.",
        f"- Tradeable candidates: {summary['signals']}.",
        f"- Entered trades: {summary['entered_trades']}.",
        f"- Total R: {summary['total_r']}.",
        f"- HTF filter allowed/blocked: {summary.get('htf_filter_allowed', 0)} / {summary.get('htf_filter_blocked', 0)}.",
    ]
    path.write_text("\n".join(notes) + "\n", encoding="utf-8")


def _write_loopholes(path: Path, args: argparse.Namespace, summary: dict[str, Any], decisions: list[MtfDecision]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Loopholes & Bugs — {args.run_name}",
        "",
        "## Engine / data assumptions worth re-checking",
        "- MTF resampling uses visible 15m bars only. If a 1H candle is in-progress it is dropped, but if source candles are missing (e.g. exchange outage/archive gap) the resample may produce extra empty hours.",
        "- The 15m analyzer sees the full `analyze_dataframe` history window, which itself trims to `lookback_bars` (default 250). Long warmup is required to give the 1H/4H/1D contexts room to form.",
        "- The 1H bias is the latest structure event direction from 1H candles. If 1H is still in an early pullback that hasn't formed a CHoCH yet, the bias may lag.",
        "- HTF alignment uses the latest structure event from each HTF; if the HTF is choppy the inferred bias may oscillate. Review the per-decision `mtf` column in `decisions.csv` to audit.",
        "- Pending POI expiration is fixed by `--entry-wait-bars`; this run does not retest 8/16/24/32 separately.",
        "",
        "## Things this run did NOT prove",
        "- Sample is too small to call statistically meaningful (per project rules we need ≥ 20 entered trades).",
        "- Costs are 4 bps round trip; this does not model funding, slippage, or exchange-specific spreads.",
        "- This run alone does not prove edge. Promote a rule only after it survives a separate time period or instrument.",
        "",
        "## Detected during this run",
    ]
    for issue in summary.get("loopholes_found", []):
        lines.append(f"- {issue}")
    if not summary.get("loopholes_found"):
        lines.append("- No automated loophole issues flagged. Inspect the decisions.csv for silent issues.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_next_steps(path: Path, args: argparse.Namespace, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Next Steps — {args.run_name}",
        "",
        "1. Re-run this exact configuration on a separate period or instrument and compare expectancy.",
        "2. Sweep `--entry-wait-bars` over 8, 16, 24, 32 bars while keeping every other parameter fixed.",
        "3. Toggle `--require-htf-alignment` off and rerun to measure the value added by the 1H/4H/1D filter.",
        "4. Try `--poi-selection nearest` and `best_location` and compare to `balanced`.",
        "5. Try `--entry-mode midpoint` vs `boundary` and compare fill rate and R.",
        "6. When 20+ entered trades exist on out-of-sample data, consider the first rule upgrade candidates.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _infer_exchange_label(path: Path, symbol: str) -> str:
    lower = str(path).lower()
    if "binance_futures" in lower:
        return f"Binance USD-M Futures ({symbol} perpetual)"
    if "bitstamp" in lower:
        return f"Bitstamp spot ({symbol})"
    return f"Unknown/imported source ({symbol})"


def _write_data_manifest(path: Path, args: argparse.Namespace, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "symbol": args.symbol,
        "execution_timeframe": args.timeframe,
        "source_csv": str(Path(args.ohlcv).resolve()),
        "csv_sha256": _hash_file(Path(args.ohlcv)),
        "candles": int(len(df)),
        "period_start": pd.Timestamp(df["timestamp"].iloc[0]).isoformat(),
        "period_end": pd.Timestamp(df["timestamp"].iloc[-1]).isoformat(),
        "htf_resample_source": "15m -> 1H, 4H, 1D in-process",
        "no_future_leakage_rule": "HTF candles kept only if close_time <= decision_time; in-progress HTF candles dropped",
        "exchange": _infer_exchange_label(Path(args.ohlcv), args.symbol),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.data_manifest:
        extra = json.loads(Path(args.data_manifest).read_text(encoding="utf-8"))
        manifest.update({f"provided_{k}": v for k, v in extra.items()})
    _write_json(path, manifest)


def _hash_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_config(path: Path, args: argparse.Namespace, rules: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_name": args.run_name,
        "args": {k: getattr(args, k) for k in [
            "symbol", "timeframe", "ohlcv", "rules",
            "use_htf_bias", "require_htf_alignment", "htf_min_agreement",
            "poi_selection", "entry_wait_bars", "max_hold_bars",
            "cost_bps", "entry_mode", "warmup_bars", "decision_step",
            "limit_bars", "max_decisions", "include_watch_retrace",
        ] if not k.startswith("_")},
        "rules": rules,
    }
    _write_json(path, payload)


def main() -> None:
    args = parse_args()
    output_dir = Path("backtests") / args.run_date / f"{args.symbol}_{args.run_name}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary, trades, decisions, near_misses = run_mtf_backtest(args)

    df = load_ohlcv_csv(args.ohlcv)
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "near_misses.json", near_misses)
    write_csv(output_dir / "trades.csv", trades)
    _write_decisions_csv(output_dir / "decisions.csv", decisions)
    _write_summary_markdown(output_dir / "summary.md", summary, decisions, trades, args)
    _write_research_notes(output_dir / "research_notes.md", args, summary, decisions)
    _write_loopholes(output_dir / "loopholes.md", args, summary, decisions)
    _write_next_steps(output_dir / "next_steps.md", args, summary)
    _write_data_manifest(output_dir / "data_manifest.json", args, df)
    rules = json.loads(Path(args.rules or "strategies/smc/default_rules.json").read_text(encoding="utf-8"))
    _write_config(output_dir / "config.json", args, rules)

    print(f"Wrote MTF backtest to {output_dir}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
