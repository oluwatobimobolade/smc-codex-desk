#!/usr/bin/env python3
"""Audit a fixed out-of-sample sample of research geometries against today's engine.

This is deliberately *not* a rule optimizer. It takes the first unique filled
research geometries after a fixed holdout cutoff, reprices their recorded
outcomes at a requested cost, and replays each decision through the current
MTF engine. The report keeps literal Execute signals separate from research
geometry so a Watch is never presented as a live trade.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.mtf import build_mtf_snapshot, derive_htf_consensus_bias, precompute_htf_series
from smc_desk.rules import load_rule_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a fixed 50-trade out-of-sample research audit.")
    parser.add_argument("--research", nargs="+", required=True, help="Enriched research CSVs, one or more pairs.")
    parser.add_argument("--data-root", default=str(ROOT / "data/ohlcv/binance_futures"))
    parser.add_argument("--data-tag", default="4year", help="CSV suffix, e.g. 4year -> SYMBOL_15m_4year.csv.")
    parser.add_argument("--rules", default=str(ROOT / "strategies/smc/rules_open.json"))
    parser.add_argument("--holdout-start", required=True, help="Fixed OOS decision cutoff, ISO timestamp or date.")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument(
        "--sample-mode",
        choices=["first", "evenly_spaced"],
        default="first",
        help="Use the first sequential fills or spread the fixed sample across the full holdout.",
    )
    parser.add_argument("--target-cost-bps", type=float, default=10.0)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def _as_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _load_rows(paths: list[Path], holdout_start: pd.Timestamp) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                decision_time = pd.Timestamp(row["decision_time"])
                if (
                    decision_time >= holdout_start
                    and _is_true(row.get("triggered"))
                    and _as_float(row.get("r_multiple")) is not None
                    and row.get("entry_index") not in {None, ""}
                ):
                    rows.append(row)
    return rows


def _data_path(data_root: Path, symbol: str, tag: str) -> Path:
    return data_root / symbol / f"{symbol}_15m_{tag}.csv"


def _reprice_r(row: dict[str, str], target_cost_bps: float) -> float:
    recorded = _as_float(row.get("r_multiple"))
    entry = _as_float(row.get("entry_price"))
    risk = _as_float(row.get("risk_per_r"))
    source_cost = _as_float(row.get("cost_bps"))
    if recorded is None:
        raise ValueError("Row has no realized R.")
    if entry is None or risk is None or risk <= 0 or source_cost is None:
        return recorded
    return recorded + (entry / risk) * (source_cost - target_cost_bps) / 10_000.0


def _metrics(rows: list[dict[str, Any]], r_key: str) -> dict[str, Any]:
    values = [float(row[r_key]) for row in rows]
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


def _same_price(left: float | None, right: float | None, *, rounded_to_cents: bool = False) -> bool:
    if left is None or right is None:
        return left is right
    # Enriched research CSVs serialize POI bounds to two decimal places, while
    # stops retain full precision. Compare each field at its stored precision.
    tolerance = max(0.0051 if rounded_to_cents else 1e-6, abs(right) * 1e-8)
    return abs(left - right) <= tolerance


def _revalidate_sample(
    sample: list[dict[str, Any]],
    dataframes: dict[str, pd.DataFrame],
    config: Any,
) -> None:
    precomputed = {symbol: precompute_htf_series(df) for symbol, df in dataframes.items()}
    for row in sample:
        symbol = row["symbol"]
        df = dataframes[symbol]
        index = int(row["decision_index"])
        decision_time = pd.Timestamp(df.at[index, "timestamp"])
        snapshot = build_mtf_snapshot(df, decision_time, config, precomputed=precomputed[symbol])
        snapshot_dict = {
            "1h": {"bias": snapshot.one_hour.bias},
            "4h": {"bias": snapshot.four_hour.bias},
            "1d": {"bias": snapshot.daily.bias},
        }
        consensus = derive_htf_consensus_bias(snapshot_dict)
        analysis, _ = analyze_dataframe(
            df=df.iloc[: index + 1],
            symbol=symbol,
            timeframe="15m",
            config=config,
            bias_hint=consensus if consensus in {"bullish", "bearish"} else None,
            notes="fixed 50-trade audit replay",
            input_type="ohlcv",
            htf_poi=snapshot.selected_htf_poi,
        )
        plan = analysis.trade_plan
        poi = plan.selected_poi
        same_geometry = bool(
            poi
            and plan.direction == row["direction"]
            and poi.kind == row["poi_kind"]
            and _same_price(poi.low, _as_float(row.get("poi_low")), rounded_to_cents=True)
            and _same_price(poi.high, _as_float(row.get("poi_high")), rounded_to_cents=True)
            and _same_price(plan.invalidation, _as_float(row.get("stop_price")))
        )
        row.update(
            {
                "current_verdict": plan.verdict,
                "current_setup_grade": plan.setup_grade,
                "current_direction": plan.direction,
                "current_poi_kind": poi.kind if poi else "",
                "current_poi_low": poi.low if poi else None,
                "current_poi_high": poi.high if poi else None,
                "current_stop_price": plan.invalidation,
                "current_htf_poi_state": plan.selected_htf_poi.state if plan.selected_htf_poi else "none",
                "current_htf_poi_timeframe": plan.selected_htf_poi.timeframe if plan.selected_htf_poi else "",
                "current_geometry_matches_record": same_geometry,
            }
        )


def _render_report(report: dict[str, Any], sample: list[dict[str, Any]]) -> str:
    gross = report["metrics_4bps"]
    stressed = report["metrics_target_cost"]
    lines = [
        "# Fixed 50-Trade Out-of-Sample Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Research decision cutoff: {report['holdout_start']}",
        f"Sample rule: {report['sample_rule']}.",
        "",
        "## Scope",
        "",
        "- This is a replay audit of research geometries, not a claim that all 50 were live Execute signals.",
        "- The current engine independently replayed each selected decision; its geometry match is reported below.",
        "- `Watch HTF POI` remains zero-risk context and is never counted as a trade merely because it appears during replay.",
        "",
        "## Result",
        "",
        "| cost basis | n | wins | losses | win% | avg R | total R | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| recorded 4 bps | {gross['n']} | {gross['wins']} | {gross['losses']} | {gross['win_rate']} | {gross['avg_r']} | {gross['total_r']} | {gross['profit_factor']} |",
        f"| repriced {report['target_cost_bps']:.1f} bps | {stressed['n']} | {stressed['wins']} | {stressed['losses']} | {stressed['win_rate']} | {stressed['avg_r']} | {stressed['total_r']} | {stressed['profit_factor']} |",
        "",
        "## Signal Classification",
        "",
    ]
    for verdict, count in report["recorded_verdicts"].items():
        lines.append(f"- Recorded {verdict}: {count}")
    for verdict, count in report["current_verdicts"].items():
        lines.append(f"- Current replay {verdict}: {count}")
    lines.extend(
        [
            f"- Current geometry matched the recorded POI/direction/SL: {report['geometry_match_count']}/{report['sample_size']}",
            "",
            "## By Pair At Target Cost",
            "",
            "| pair | n | win% | avg R | total R | PF |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for symbol, metrics in report["by_symbol_target_cost"].items():
        lines.append(
            f"| {symbol} | {metrics['n']} | {metrics['win_rate']} | {metrics['avg_r']} | {metrics['total_r']} | {metrics['profit_factor']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A 50-trade sample is an operational checkpoint, not sufficient evidence to promote a strategy or model.",
            "- The target-cost row matters more than the recorded-cost row; a strategy that fails after reasonable costs is not ready for deployment.",
            "- Research-geometry outcomes must not be treated as live performance until the same result is reproduced using literal Execute rules or a separately tested confirmation rule.",
            "",
            "## Sample",
            "",
            "| # | entry time | pair | recorded verdict | current verdict | HTF state | outcome | R @ target cost | geometry match |",
            "|---:|---|---|---|---|---|---|---:|---|",
        ]
    )
    for number, row in enumerate(sample, start=1):
        lines.append(
            f"| {number} | {row['entry_time']} | {row['symbol']} | {row['verdict']} | "
            f"{row['current_verdict']} | {row['current_htf_poi_state']} | {row['outcome']} | "
            f"{row['r_target_cost']:.4f} | {row['current_geometry_matches_record']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    if args.sample_size <= 0:
        raise SystemExit("--sample-size must be positive")
    holdout_start = pd.Timestamp(args.holdout_start)
    research_rows = _load_rows([Path(path) for path in args.research], holdout_start)
    if not research_rows:
        raise SystemExit("No triggered research rows after the requested cutoff.")

    data_root = Path(args.data_root)
    needed_symbols = sorted({row["symbol"] for row in research_rows})
    dataframes = {
        symbol: load_ohlcv_csv(str(_data_path(data_root, symbol, args.data_tag)))
        for symbol in needed_symbols
    }
    for row in research_rows:
        symbol = row["symbol"]
        entry_index = int(row["entry_index"])
        row["entry_time"] = pd.Timestamp(dataframes[symbol].at[entry_index, "timestamp"]).isoformat()

    unique: dict[tuple[str, str], dict[str, str]] = {}
    for row in sorted(research_rows, key=lambda item: (item["decision_time"], item["symbol"])):
        unique.setdefault((row["symbol"], row["entry_index"]), row)
    candidates = sorted(unique.values(), key=lambda item: (item["entry_time"], item["symbol"]))
    if args.sample_mode == "first":
        sample = candidates[: args.sample_size]
        sample_rule = f"first {args.sample_size} unique filled research geometries by entry time across the supplied pairs"
    else:
        if len(candidates) < args.sample_size:
            sample = candidates
        elif args.sample_size == 1:
            sample = [candidates[0]]
        else:
            indexes = [round(index * (len(candidates) - 1) / (args.sample_size - 1)) for index in range(args.sample_size)]
            sample = [candidates[index] for index in indexes]
        sample_rule = f"{args.sample_size} evenly spaced unique filled research geometries across the full holdout by entry time"
    if len(sample) < args.sample_size:
        raise SystemExit(f"Only {len(sample)} unique triggered rows available; requested {args.sample_size}.")

    audit_rows: list[dict[str, Any]] = []
    for row in sample:
        audit = dict(row)
        audit["r_recorded_4bps"] = float(row["r_multiple"])
        audit["r_target_cost"] = round(_reprice_r(row, args.target_cost_bps), 6)
        audit_rows.append(audit)

    config = load_rule_config(args.rules)
    _revalidate_sample(audit_rows, dataframes, config)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "holdout_start": holdout_start.isoformat(),
        "sample_size": len(audit_rows),
        "sample_rule": sample_rule,
        "target_cost_bps": args.target_cost_bps,
        "research_inputs": [str(Path(path).resolve()) for path in args.research],
        "rules": str(Path(args.rules).resolve()),
        "metrics_4bps": _metrics(audit_rows, "r_recorded_4bps"),
        "metrics_target_cost": _metrics(audit_rows, "r_target_cost"),
        "recorded_verdicts": dict(Counter(row["verdict"] for row in audit_rows)),
        "current_verdicts": dict(Counter(row["current_verdict"] for row in audit_rows)),
        "geometry_match_count": sum(1 for row in audit_rows if row["current_geometry_matches_record"]),
        "by_symbol_target_cost": {
            symbol: _metrics(rows, "r_target_cost")
            for symbol, rows in sorted(
                defaultdict(list, {symbol: [row for row in audit_rows if row["symbol"] == symbol] for symbol in needed_symbols}).items()
            )
            if rows
        },
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(audit_rows[0].keys())
    with (output_dir / "sample.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit_rows)
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(_render_report(report, audit_rows), encoding="utf-8")
    print(_render_report(report, audit_rows))
    print(f"Wrote audit to {output_dir}")


if __name__ == "__main__":
    main()
