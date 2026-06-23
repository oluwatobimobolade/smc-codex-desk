#!/usr/bin/env python3
"""Evaluate a frozen research geometry across chronological holdout windows.

This is an evidence gate, not an optimizer. It never changes a rule, selects a
threshold, or promotes Watch-derived research geometries to live trades. Its
job is to establish whether the currently frozen geometry even merits further
research after realistic costs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _as_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def reprice_r(row: dict[str, str], target_cost_bps: float) -> float:
    recorded = _as_float(row.get("r_multiple"))
    entry = _as_float(row.get("entry_price"))
    risk = _as_float(row.get("risk_per_r"))
    source_cost = _as_float(row.get("cost_bps"))
    if recorded is None:
        raise ValueError("Row has no realized R multiple.")
    if entry is None or risk is None or risk <= 0 or source_cost is None:
        return recorded
    return recorded + (entry / risk) * (source_cost - target_cost_bps) / 10_000.0


def load_candidates(paths: list[Path], holdout_start: pd.Timestamp, target_cost_bps: float) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                decision_time = pd.Timestamp(row["decision_time"])
                if (
                    decision_time < holdout_start
                    or not _is_true(row.get("triggered"))
                    or _as_float(row.get("r_multiple")) is None
                    or row.get("entry_index") in {None, ""}
                ):
                    continue
                candidate = dict(row)
                candidate["decision_time"] = decision_time.isoformat()
                candidate["r_target_cost"] = round(reprice_r(row, target_cost_bps), 6)
                key = (str(candidate["symbol"]), str(candidate["entry_index"]))
                # Repeated decisions can point at the same filled entry. Keep the
                # earliest decision so the sample remains one outcome per fill.
                existing = candidates.get(key)
                if existing is None or candidate["decision_time"] < existing["decision_time"]:
                    candidates[key] = candidate
    return sorted(candidates.values(), key=lambda row: (row["decision_time"], row["symbol"]))


def chronological_folds(rows: list[dict[str, Any]], folds: int) -> list[list[dict[str, Any]]]:
    if folds <= 0:
        raise ValueError("fold count must be positive")
    if len(rows) < folds:
        raise ValueError(f"Need at least {folds} unique filled outcomes for {folds} chronological folds.")
    result: list[list[dict[str, Any]]] = []
    for fold in range(folds):
        start = fold * len(rows) // folds
        end = (fold + 1) * len(rows) // folds
        result.append(rows[start:end])
    return result


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["r_target_cost"]) for row in rows]
    wins = [value for value in values if value > 0.05]
    losses = [value for value in values if value < -0.05]
    gross_loss = abs(sum(losses))
    return {
        "n": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "flat_or_timeout": len(values) - len(wins) - len(losses),
        "win_rate": round(len(wins) / len(values), 4) if values else None,
        "avg_r": round(sum(values) / len(values), 4) if values else None,
        "total_r": round(sum(values), 4),
        "profit_factor": round(sum(wins) / gross_loss, 4) if gross_loss else None,
    }


def bootstrap_mean_ci(rows: list[dict[str, Any]], *, seed: int = 20260622, draws: int = 2_000) -> list[float | None]:
    values = [float(row["r_target_cost"]) for row in rows]
    if len(values) < 2:
        return [None, None]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(draws))
    lower = means[max(0, math.floor((draws - 1) * 0.025))]
    upper = means[min(draws - 1, math.ceil((draws - 1) * 0.975))]
    return [round(lower, 4), round(upper, 4)]


def evaluate(
    rows: list[dict[str, Any]],
    *,
    folds: int,
    min_trades: int,
    min_positive_folds: int,
    min_pairs: int,
    min_trades_per_pair: int,
) -> dict[str, Any]:
    fold_rows = chronological_folds(rows, folds)
    fold_reports = []
    for number, fold in enumerate(fold_rows, start=1):
        fold_report = metrics(fold)
        fold_report.update(
            {
                "fold": number,
                "start": fold[0]["decision_time"],
                "end": fold[-1]["decision_time"],
                "symbols": sorted({row["symbol"] for row in fold}),
            }
        )
        fold_reports.append(fold_report)
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    per_symbol = {symbol: metrics(symbol_rows) for symbol, symbol_rows in sorted(by_symbol.items())}
    positive_folds = sum(1 for fold in fold_reports if (fold["avg_r"] or 0.0) > 0.0)
    viable_pairs = sum(
        1
        for report in per_symbol.values()
        if report["n"] >= min_trades_per_pair and (report["avg_r"] or 0.0) > 0.0
    )
    aggregate = metrics(rows)
    ci = bootstrap_mean_ci(rows)
    blockers: list[str] = [
        "Research geometry is not literal Execute performance; it cannot be promoted to a live edge from this report.",
    ]
    if aggregate["n"] < min_trades:
        blockers.append(f"Only {aggregate['n']} unique filled outcomes; need at least {min_trades}.")
    if (aggregate["avg_r"] or 0.0) <= 0.0:
        blockers.append("Aggregate after-cost expectancy is non-positive.")
    if ci[0] is None or ci[0] <= 0.0:
        blockers.append("The 95% bootstrap lower bound for mean R does not clear zero.")
    if positive_folds < min_positive_folds:
        blockers.append(f"Only {positive_folds}/{folds} positive chronological folds; need {min_positive_folds}/{folds}.")
    if viable_pairs < min_pairs:
        blockers.append(
            f"Only {viable_pairs} pairs have at least {min_trades_per_pair} outcomes and positive after-cost expectancy; need {min_pairs}."
        )
    return {
        "aggregate": aggregate,
        "mean_r_bootstrap_95_ci": ci,
        "folds": fold_reports,
        "positive_folds": positive_folds,
        "per_symbol": per_symbol,
        "viable_pairs": viable_pairs,
        "promotion_status": "NO_GO" if blockers else "RESEARCH_GATE_PASSED_NOT_LIVE_APPROVED",
        "blockers": blockers,
    }


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines = [
        "# Frozen Geometry Walk-Forward Validation",
        "",
        f"Status: **{report['promotion_status']}**",
        "",
        "This is chronological, after-cost validation of a fixed research geometry. It does not tune a rule or count Watch states as live executions.",
        "",
        "## Aggregate",
        "",
        "| n | win% | avg R | total R | PF | 95% bootstrap CI for mean R |",
        "|---:|---:|---:|---:|---:|---|",
        f"| {aggregate['n']} | {aggregate['win_rate']} | {aggregate['avg_r']} | {aggregate['total_r']} | {aggregate['profit_factor']} | {report['mean_r_bootstrap_95_ci']} |",
        "",
        "## Chronological Folds",
        "",
        "| Fold | Start | End | n | Avg R | Total R | PF | Symbols |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for fold in report["folds"]:
        lines.append(
            f"| {fold['fold']} | {fold['start']} | {fold['end']} | {fold['n']} | {fold['avg_r']} | {fold['total_r']} | {fold['profit_factor']} | {', '.join(fold['symbols'])} |"
        )
    lines.extend(["", "## Pair Results", "", "| Pair | n | Avg R | Total R | PF |", "|---|---:|---:|---:|---:|"])
    for symbol, metrics_by_symbol in report["per_symbol"].items():
        lines.append(
            f"| {symbol} | {metrics_by_symbol['n']} | {metrics_by_symbol['avg_r']} | {metrics_by_symbol['total_r']} | {metrics_by_symbol['profit_factor']} |"
        )
    lines.extend(["", "## Gate", ""])
    lines.extend(f"- {blocker}" for blocker in report["blockers"]) if report["blockers"] else lines.append("- Gate passed for further research only.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a locked chronological validation of enriched research geometry.")
    parser.add_argument("--research", nargs="+", required=True)
    parser.add_argument("--holdout-start", required=True)
    parser.add_argument("--target-cost-bps", type=float, default=10.0)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--min-positive-folds", type=int, default=4)
    parser.add_argument("--min-pairs", type=int, default=3)
    parser.add_argument("--min-trades-per-pair", type=int, default=20)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    holdout_start = pd.Timestamp(args.holdout_start)
    rows = load_candidates([Path(path) for path in args.research], holdout_start, args.target_cost_bps)
    if not rows:
        raise SystemExit("No unique triggered outcomes remain after the holdout cutoff.")
    report = evaluate(
        rows,
        folds=args.folds,
        min_trades=args.min_trades,
        min_positive_folds=args.min_positive_folds,
        min_pairs=args.min_pairs,
        min_trades_per_pair=args.min_trades_per_pair,
    )
    report.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "holdout_start": holdout_start.isoformat(),
            "target_cost_bps": args.target_cost_bps,
            "research_inputs": [str(Path(path).resolve()) for path in args.research],
            "sample_definition": "Unique filled research geometries, deduplicated by symbol + entry index, ordered by decision time.",
        }
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for fold_number, fold_rows in enumerate(chronological_folds(rows, args.folds), start=1):
        for row in fold_rows:
            row["fold"] = fold_number
    with (output_dir / "fold_membership.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"Wrote validation to {output_dir}")


if __name__ == "__main__":
    main()
