#!/usr/bin/env python3
"""Build and resolve a deterministic Market Colleague case cohort.

This is research plumbing, not a trading-performance claim. It creates local
colleague packages, resolves their pending outcome contracts from future 15m
candles, and summarizes buckets honestly.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.outcome_resolution import resolve_run_outcome
from smc_desk.colleague.request_contract import ColleagueRunRequest, default_ohlcv_path, normalize_symbol
from smc_desk.colleague.run_context import TIMEFRAME_DURATIONS, load_local_15m
from smc_desk.colleague.orchestrator import run_colleague_analysis
from smc_desk.rules import RuleConfig, load_rule_config


DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]


def _as_utc_naive(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)
    return ts


def select_decision_times(
    df: pd.DataFrame,
    *,
    count: int,
    horizon_bars: int = 96,
    min_history_bars: int = 500,
    start: str | None = None,
    end: str | None = None,
) -> list[pd.Timestamp]:
    """Return evenly spaced analysis availability times with enough future bars."""

    if count <= 0:
        return []
    data = df.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True).dt.tz_convert(None)
    data = data.sort_values("timestamp").reset_index(drop=True)
    start_ts = _as_utc_naive(start)
    end_ts = _as_utc_naive(end)
    min_index = max(0, int(min_history_bars) - 1)
    max_index = len(data) - int(horizon_bars) - 1
    candidates: list[int] = []
    for index, row in data.iterrows():
        if index < min_index or index > max_index:
            continue
        candle_open = pd.Timestamp(row["timestamp"])
        decision_available_at = candle_open + TIMEFRAME_DURATIONS["15m"]
        if start_ts is not None and decision_available_at < start_ts:
            continue
        if end_ts is not None and decision_available_at > end_ts:
            continue
        candidates.append(index)
    if len(candidates) < count:
        raise ValueError(f"Only {len(candidates)} eligible decision points available; requested {count}.")
    if count == 1:
        chosen = [candidates[len(candidates) // 2]]
    else:
        positions = [round(i * (len(candidates) - 1) / (count - 1)) for i in range(count)]
        chosen = [candidates[position] for position in positions]
    return [pd.Timestamp(data["timestamp"].iloc[index]) + TIMEFRAME_DURATIONS["15m"] for index in chosen]


def _case_record(run_manifest: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_manifest["files"]["request.json"]["path"]).parent
    decision_path = run_dir / "scenarios" / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    return {
        "symbol": run_manifest.get("symbol"),
        "run_dir": str(run_dir),
        "run_manifest": str(run_dir / "run_manifest.json"),
        "decision_candle_open": run_manifest.get("decision_candle_open"),
        "decision_available_at": run_manifest.get("decision_available_at"),
        "decision_action": decision.get("action"),
        "legacy_engine_role": run_manifest.get("legacy_engine_role"),
        "resolution_status": resolution.get("status"),
        "scenario_result_statuses": [item.get("status") for item in resolution.get("scenario_results", [])],
        "future_window_complete": resolution.get("future_window", {}).get("complete_window"),
        "market_edge_claimed": False,
        "performance_claim_allowed": False,
    }


def _summarize(records: list[dict[str, Any]], *, output_root: Path, requested: dict[str, Any]) -> dict[str, Any]:
    decision_counts = Counter(str(item.get("decision_action")) for item in records)
    resolution_counts = Counter(str(item.get("resolution_status")) for item in records)
    scenario_counts: Counter[str] = Counter()
    for item in records:
        scenario_counts.update(str(status) for status in item.get("scenario_result_statuses", []))
    unresolved = [item for item in records if not item.get("future_window_complete")]
    ambiguous = [
        item
        for item in records
        if any("ambiguous" in str(status) for status in item.get("scenario_result_statuses", []))
    ]
    cohort_buckets = {
        "no_trade_observation": sum(1 for item in records if str(item.get("decision_action")).upper() in {"NO_SETUP", "SOURCE_MISMATCH"}),
        "watch_observation": sum(1 for item in records if str(item.get("decision_action")).upper() == "WATCH"),
        "disabled_signal_observation": sum(1 for item in records if str(item.get("decision_action")).upper() == "PAPER_EXECUTE_DISABLED"),
        "ambiguous_resolution": len(ambiguous),
        "unresolved": len(unresolved),
    }
    return {
        "cohort_version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(output_root.resolve()),
        "requested": requested,
        "resolved_packages": len(records) - len(unresolved),
        "total_packages": len(records),
        "unresolved_packages": len(unresolved),
        "decision_action_counts": dict(sorted(decision_counts.items())),
        "resolution_status_counts": dict(sorted(resolution_counts.items())),
        "scenario_result_status_counts": dict(sorted(scenario_counts.items())),
        "cohort_bucket_counts": cohort_buckets,
        "case_records_path": str((output_root / "case_records.jsonl").resolve()),
        "authority": "research_observation_only",
        "market_edge_claimed": False,
        "paper_execution_enabled": False,
        "live_execution_enabled": False,
        "promotion_status": "not_eligible_edge_not_tested",
        "honesty_rule": "Non-execute outcomes are observations only; no win rate, profit factor, or signal quality claim is made from this cohort.",
        "cases": records,
    }


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Resolved Case Cohort Summary",
        "",
        f"Created: `{summary['created_at']}`",
        f"Output root: `{summary['output_root']}`",
        "",
        "This cohort is research observation only. No execution, win-rate, profit-factor, or market-edge claim is enabled.",
        "",
        f"- Total packages: `{summary['total_packages']}`",
        f"- Resolved packages: `{summary['resolved_packages']}`",
        f"- Unresolved packages: `{summary['unresolved_packages']}`",
        f"- Promotion status: `{summary['promotion_status']}`",
        "",
        "## Decision Actions",
        "",
    ]
    for key, value in summary["decision_action_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Resolution Status", ""])
    for key, value in summary["resolution_status_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Cohort Buckets", ""])
    for key, value in summary["cohort_bucket_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Scenario Result Status", ""])
    for key, value in summary["scenario_result_status_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", f"Case records: `{summary['case_records_path']}`", ""])
    return "\n".join(lines)


def build_resolved_case_cohort(
    *,
    symbols: list[str],
    output_root: Path,
    config: RuleConfig,
    cases_per_symbol: int = 10,
    horizon_bars: int = 96,
    data_root: Path | None = None,
    tag: str = "4year",
    start: str | None = None,
    end: str | None = None,
    include_legacy_comparison: bool = False,
    render_charts: bool = False,
    allow_holdout: bool = False,
    holdout_policy: str | None = None,
) -> dict[str, Any]:
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    requested = {
        "symbols": [normalize_symbol(symbol) for symbol in symbols],
        "cases_per_symbol": cases_per_symbol,
        "horizon_bars": horizon_bars,
        "tag": tag,
        "start": start,
        "end": end,
        "include_legacy_comparison": include_legacy_comparison,
        "render_charts": render_charts,
    }

    for raw_symbol in symbols:
        symbol = normalize_symbol(raw_symbol)
        source_path = default_ohlcv_path(symbol, data_root or (ROOT / "data" / "ohlcv" / "binance_futures"), tag)
        df = load_local_15m(source_path)
        decision_times = select_decision_times(
            df,
            count=cases_per_symbol,
            horizon_bars=horizon_bars,
            start=start,
            end=end,
        )
        for number, decision_time in enumerate(decision_times, start=1):
            decision_tag = decision_time.strftime("%Y%m%d_%H%M")
            run_dir = output_root / "runs" / symbol / f"{symbol}_{decision_tag}_case_{number:02d}"
            request = ColleagueRunRequest(
                symbol=symbol,
                source_path=str(source_path),
                output_dir=str(run_dir),
                decision_time=decision_time.isoformat(),
                holdout_policy=holdout_policy,
                allow_holdout=allow_holdout,
                include_legacy_comparison=include_legacy_comparison,
                render_charts=render_charts,
                outcome_horizon_bars=horizon_bars,
                run_id=f"{symbol}_{decision_tag}_resolved_case_{number:02d}",
            )
            run_manifest = run_colleague_analysis(request, config)
            actual_run_dir = Path(run_manifest["files"]["request.json"]["path"]).parent
            resolution = resolve_run_outcome(run_dir=actual_run_dir, ohlcv_path=source_path)
            records.append(_case_record(run_manifest, resolution))

    (output_root / "case_records.jsonl").write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    summary = _summarize(records, output_root=output_root, requested=requested)
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_root / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and resolve a local Market Colleague cohort.")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--rules")
    parser.add_argument("--cases-per-symbol", type=int, default=10)
    parser.add_argument("--horizon-bars", type=int, default=96)
    parser.add_argument("--data-root", default=str(ROOT / "data" / "ohlcv" / "binance_futures"))
    parser.add_argument("--tag", default="4year")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--include-legacy-comparison", action="store_true")
    parser.add_argument("--render-charts", action="store_true")
    parser.add_argument("--allow-holdout", action="store_true")
    parser.add_argument("--holdout-policy")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_resolved_case_cohort(
        symbols=args.symbols,
        output_root=Path(args.output_root),
        config=load_rule_config(args.rules),
        cases_per_symbol=args.cases_per_symbol,
        horizon_bars=args.horizon_bars,
        data_root=Path(args.data_root),
        tag=args.tag,
        start=args.start,
        end=args.end,
        include_legacy_comparison=args.include_legacy_comparison,
        render_charts=args.render_charts,
        allow_holdout=args.allow_holdout,
        holdout_policy=args.holdout_policy,
    )
    print(render_summary_markdown(summary))


if __name__ == "__main__":
    main()
