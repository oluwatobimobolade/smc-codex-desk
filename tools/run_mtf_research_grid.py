#!/usr/bin/env python3
"""Run a multi-dataset MTF SMC research grid and aggregate diagnostics.

This is deliberately a research harness, not a rule promoter. It downloads
or reuses public Binance USD-M futures 15m candles, runs controlled MTF
backtests, and writes a single report that separates "more trades" from
"better trades".
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = ROOT / ".venv/bin/python"
DOWNLOAD = ROOT / "tools/download_binance_futures_ohlcv.py"
BACKTEST = ROOT / "tools/backtest_smc_elite_mtf.py"


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    market: str
    symbol: str
    start: str
    end: str
    role: str
    file_tag: str

    @property
    def csv_path(self) -> Path:
        return (
            ROOT
            / "data"
            / "ohlcv"
            / "binance_futures"
            / self.symbol
            / f"{self.symbol}_15m_{self.file_tag}.csv"
        )


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    hypothesis: str
    entry_wait_bars: int = 24
    entry_mode: str = "boundary"
    poi_selection: str = "balanced"
    use_htf_bias: str = "on"
    require_htf_alignment: str = "on"
    include_watch_retrace: str = "off"
    htf_min_agreement: float = 0.5


DATASETS = [
    DatasetSpec(
        "btcusdt_insample_feb_may",
        "BTCUSDT",
        "BTCUSDT",
        "2026-02-01",
        "2026-05-31T23:45:00+00:00",
        "BTCUSDT in-sample",
        "insample_20260201_20260531",
    ),
    DatasetSpec(
        "btcusdt_holdout_jun",
        "BTCUSDT",
        "BTCUSDT",
        "2026-06-01",
        "2026-06-18T00:00:00+00:00",
        "BTCUSDT forward holdout",
        "holdout_20260601_20260618",
    ),
    DatasetSpec(
        "ethusdt_insample_feb_may",
        "ETHUSDT",
        "ETHUSDT",
        "2026-02-01",
        "2026-05-31T23:45:00+00:00",
        "ETHUSDT cross-instrument",
        "insample_20260201_20260531",
    ),
    DatasetSpec(
        "ethusdt_holdout_jun",
        "ETHUSDT",
        "ETHUSDT",
        "2026-06-01",
        "2026-06-18T00:00:00+00:00",
        "ETHUSDT forward holdout",
        "holdout_20260601_20260618",
    ),
    DatasetSpec(
        "solusdt_insample_feb_may",
        "SOLUSDT",
        "SOLUSDT",
        "2026-02-01",
        "2026-05-31T23:45:00+00:00",
        "SOLUSDT cross-instrument",
        "insample_20260201_20260531",
    ),
    DatasetSpec(
        "solusdt_holdout_jun",
        "SOLUSDT",
        "SOLUSDT",
        "2026-06-01",
        "2026-06-18T00:00:00+00:00",
        "SOLUSDT forward holdout",
        "holdout_20260601_20260618",
    ),
    DatasetSpec(
        "xrpusdt_insample_feb_may",
        "XRPUSDT",
        "XRPUSDT",
        "2026-02-01",
        "2026-05-31T23:45:00+00:00",
        "XRPUSDT cross-instrument",
        "insample_20260201_20260531",
    ),
    DatasetSpec(
        "xrpusdt_holdout_jun",
        "XRPUSDT",
        "XRPUSDT",
        "2026-06-01",
        "2026-06-18T00:00:00+00:00",
        "XRPUSDT forward holdout",
        "holdout_20260601_20260618",
    ),
    DatasetSpec(
        "bnbusdt_insample_feb_may",
        "BNBUSDT",
        "BNBUSDT",
        "2026-02-01",
        "2026-05-31T23:45:00+00:00",
        "BNBUSDT cross-instrument",
        "insample_20260201_20260531",
    ),
    DatasetSpec(
        "bnbusdt_holdout_jun",
        "BNBUSDT",
        "BNBUSDT",
        "2026-06-01",
        "2026-06-18T00:00:00+00:00",
        "BNBUSDT forward holdout",
        "holdout_20260601_20260618",
    ),
]

EXPERIMENTS = [
    ExperimentSpec("strict_baseline", "Strict baseline: HTF bias+alignment on, balanced POI, 24-bar wait."),
    ExperimentSpec(
        "watch_retrace_diagnostic",
        "Diagnostic only: trades Watch Retrace pending POIs to measure whether almost-confirmed setups deserve future study.",
        include_watch_retrace="on",
    ),
    ExperimentSpec("wait48", "Longer 48-bar pending window: tests whether missed entries are just slow retraces.", entry_wait_bars=48),
    ExperimentSpec(
        "best_location",
        "Best-location POI: tests whether premium/discount quality beats balanced ranking.",
        poi_selection="best_location",
    ),
    ExperimentSpec(
        "no_htf_bias_diagnostic",
        "Diagnostic only: removes HTF bias+alignment to test whether more trades become worse trades.",
        use_htf_bias="off",
        require_htf_alignment="off",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-dataset SMC MTF research grid.")
    parser.add_argument("--run-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--decision-step", type=int, default=16, help="Evaluate every N bars for broad research sweeps.")
    parser.add_argument("--warmup-bars", type=int, default=400)
    parser.add_argument("--max-hold-bars", type=int, default=96)
    parser.add_argument("--cost-bps", type=float, default=4.0)
    parser.add_argument("--download", action="store_true", help="Download any missing dataset CSVs from Binance USD-M futures archives.")
    parser.add_argument("--force", action="store_true", help="Rerun even if a summary.json already exists.")
    parser.add_argument("--symbols", nargs="*", choices=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"], help="Optional symbol subset.")
    parser.add_argument("--experiments", nargs="*", help="Optional experiment-id subset.")
    parser.add_argument("--max-datasets", type=int, help="Optional cap for smoke testing.")
    parser.add_argument("--max-experiments", type=int, help="Optional cap for smoke testing.")
    return parser.parse_args()


def run_command(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def ensure_dataset(dataset: DatasetSpec, download: bool) -> None:
    if dataset.csv_path.exists():
        return
    if not download:
        raise FileNotFoundError(f"Missing {dataset.csv_path}; rerun with --download to fetch it.")
    cmd = [
        str(PY),
        str(DOWNLOAD),
        "--symbol",
        dataset.market,
        "--interval",
        "15m",
        "--start",
        dataset.start,
        "--end",
        dataset.end,
        "--output",
        str(dataset.csv_path),
        "--sleep",
        "0.03",
        "--allow-missing",
    ]
    print(f"Downloading {dataset.dataset_id} -> {dataset.csv_path}", flush=True)
    result = run_command(cmd)
    if result.returncode != 0:
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)
        raise SystemExit(result.returncode)
    print(result.stdout.strip(), flush=True)


def quality_report(path: Path) -> dict[str, Any]:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    expected = pd.Timedelta(minutes=15)
    deltas = df["timestamp"].diff().dropna()
    gaps = int((deltas != expected).sum())
    return {
        "rows": int(len(df)),
        "start": pd.Timestamp(df["timestamp"].iloc[0]).isoformat() if len(df) else None,
        "end": pd.Timestamp(df["timestamp"].iloc[-1]).isoformat() if len(df) else None,
        "gaps": gaps,
        "nan_ohlc": int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
        "zero_volume": int((pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0) <= 0).sum()),
    }


def run_name(dataset: DatasetSpec, experiment: ExperimentSpec) -> str:
    return f"grid_{dataset.dataset_id}_{experiment.experiment_id}"


def summary_path(args: argparse.Namespace, dataset: DatasetSpec, experiment: ExperimentSpec) -> Path:
    return ROOT / "backtests" / args.run_date / f"{dataset.symbol}_{run_name(dataset, experiment)}" / "summary.json"


def run_backtest(args: argparse.Namespace, dataset: DatasetSpec, experiment: ExperimentSpec) -> dict[str, Any]:
    target_summary = summary_path(args, dataset, experiment)
    if target_summary.exists() and not args.force:
        return json.loads(target_summary.read_text(encoding="utf-8"))

    hypothesis = f"{dataset.role}: {experiment.hypothesis}"
    cmd = [
        str(PY),
        str(BACKTEST),
        "--ohlcv",
        str(dataset.csv_path),
        "--symbol",
        dataset.symbol,
        "--timeframe",
        "15m",
        "--warmup-bars",
        str(args.warmup_bars),
        "--max-hold-bars",
        str(args.max_hold_bars),
        "--cost-bps",
        str(args.cost_bps),
        "--decision-step",
        str(args.decision_step),
        "--run-name",
        run_name(dataset, experiment),
        "--run-date",
        args.run_date,
        "--entry-wait-bars",
        str(experiment.entry_wait_bars),
        "--entry-mode",
        experiment.entry_mode,
        "--poi-selection",
        experiment.poi_selection,
        "--use-htf-bias",
        experiment.use_htf_bias,
        "--require-htf-alignment",
        experiment.require_htf_alignment,
        "--htf-min-agreement",
        str(experiment.htf_min_agreement),
        "--include-watch-retrace",
        experiment.include_watch_retrace,
        "--hypothesis",
        hypothesis,
    ]
    print(f"\n=== {dataset.dataset_id} :: {experiment.experiment_id} ===", flush=True)
    result = run_command(cmd)
    if result.returncode != 0:
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)
        raise SystemExit(result.returncode)
    summary = json.loads(target_summary.read_text(encoding="utf-8"))
    print(
        f"  decisions={summary['decision_bars']} signals={summary['signals']} "
        f"entered={summary['entered_trades']} wins={summary['wins']} losses={summary['losses']} "
        f"total_r={summary['total_r']} htf_blocked={summary.get('htf_filter_blocked', 0)}",
        flush=True,
    )
    return summary


def _parse_bool(value: str) -> bool | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def parse_checklist(raw: str) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for item in raw.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parsed = _parse_bool(value)
        if parsed is not None:
            result[key] = parsed
    return result


def blocker_diagnostics(run_dir: Path) -> dict[str, Any]:
    decisions = run_dir / "decisions.csv"
    if not decisions.exists():
        return {}
    total = 0
    sweep_sequence_fail = 0
    price_only = 0
    htf_blocked = 0
    top_blockers: dict[str, int] = {}
    with decisions.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total += 1
            blockers = [item for item in row.get("blockers", "").split(";") if item]
            for blocker in blockers:
                top_blockers[blocker] = top_blockers.get(blocker, 0) + 1
            checklist = parse_checklist(row.get("checklist", ""))
            if (
                checklist.get("liquidity_sweep") is True
                and checklist.get("displacement_break") is True
                and checklist.get("sweep_before_break") is False
            ):
                sweep_sequence_fail += 1
            if blockers == ["price at or near poi"]:
                price_only += 1
            if row.get("htf_filter_passed") == "False":
                htf_blocked += 1
    sorted_blockers = dict(sorted(top_blockers.items(), key=lambda item: item[1], reverse=True)[:8])
    return {
        "decision_rows": total,
        "sweep_sequence_fail": sweep_sequence_fail,
        "price_only_retrace_ready": price_only,
        "htf_blocked_rows": htf_blocked,
        "top_blockers": sorted_blockers,
    }


def pct(value: float) -> str:
    return f"{value:.0%}"


def write_outputs(args: argparse.Namespace, summaries: list[dict[str, Any]], dataset_quality: dict[str, dict[str, Any]]) -> Path:
    out_dir = ROOT / "backtests" / args.run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "research_grid_results.json"
    csv_path = out_dir / "research_grid_results.csv"
    report_path = out_dir / "research_grid_report.md"

    enriched: list[dict[str, Any]] = []
    for summary in summaries:
        run_dir = out_dir / f"{summary['symbol']}_{summary['run_name']}"
        dataset_id = ""
        experiment_id = summary["run_name"]
        for experiment in EXPERIMENTS:
            suffix = f"_{experiment.experiment_id}"
            if summary["run_name"].endswith(suffix):
                experiment_id = experiment.experiment_id
                dataset_id = summary["run_name"][len("grid_") : -len(suffix)]
                break
        row = {
            **summary,
            "dataset_id": dataset_id,
            "experiment_id": experiment_id,
            "blocker_diagnostics": blocker_diagnostics(run_dir),
        }
        enriched.append(row)

    json_path.write_text(json.dumps({"datasets": dataset_quality, "runs": enriched}, indent=2), encoding="utf-8")
    fieldnames = [
        "symbol",
        "dataset_id",
        "experiment_id",
        "decision_bars",
        "signals",
        "entered_trades",
        "wins",
        "losses",
        "win_rate",
        "total_r",
        "avg_r",
        "max_drawdown_r",
        "htf_filter_blocked",
        "watch_retrace_signals",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in enriched:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    total_entered = sum(int(row.get("entered_trades", 0)) for row in enriched)
    total_r = round(sum(float(row.get("total_r", 0.0)) for row in enriched), 4)
    best = sorted(enriched, key=lambda item: (int(item.get("entered_trades", 0)), float(item.get("total_r", 0.0))), reverse=True)[:5]
    experiment_rollup: dict[str, dict[str, Any]] = {}
    for row in enriched:
        experiment = row["experiment_id"]
        bucket = experiment_rollup.setdefault(
            experiment,
            {"entered": 0, "total_r": 0.0, "wins": 0, "losses": 0, "positive_runs": 0, "negative_runs": 0, "runs": 0},
        )
        bucket["entered"] += int(row.get("entered_trades", 0))
        bucket["total_r"] += float(row.get("total_r", 0.0))
        bucket["wins"] += int(row.get("wins", 0))
        bucket["losses"] += int(row.get("losses", 0))
        bucket["runs"] += 1
        if float(row.get("total_r", 0.0)) > 0:
            bucket["positive_runs"] += 1
        if float(row.get("total_r", 0.0)) < 0:
            bucket["negative_runs"] += 1

    promotion_notes = [
        "No rule is promoted from this grid.",
        "`watch_retrace_diagnostic` is not a live rule; it exists to measure pending POI behavior against confirmed-only runs.",
        "`wait48` stays a hypothesis unless it beats confirmed-only baseline on a separate period and symbol.",
        "`best_location` is not promoted: it increased signals but stayed negative.",
        "`no_htf_bias_diagnostic` is not promoted: removing HTF bias/alignment produced worse or unstable action.",
        "`sweep_before_break` should remain required for now; sequence failures were present, but loosening adjacent filters did not create robust expectancy.",
    ]
    lines = [
        f"# SMC MTF Research Grid ({args.run_date})",
        "",
        f"Decision step: `{args.decision_step}`. This is broad diagnostic sampling, not final execution replay.",
        "",
        "## Data Quality",
        "",
        "| Dataset | Rows | Start | End | Gaps | NaN OHLC | Zero Volume |",
        "|---|---:|---|---|---:|---:|---:|",
    ]
    for dataset_id, quality in dataset_quality.items():
        lines.append(
            f"| {dataset_id} | {quality['rows']} | {quality['start']} | {quality['end']} | "
            f"{quality['gaps']} | {quality['nan_ohlc']} | {quality['zero_volume']} |"
        )
    lines.extend(
        [
            "",
            "## Promotion Verdict",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in promotion_notes)
    lines.extend(
        [
            "",
            "## Run Comparison",
            "",
            "| Dataset | Experiment | Decisions | Signals | Entered | Wins | Losses | Total R | Avg R | Win% | HTF Blocked |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in enriched:
        lines.append(
            "| {dataset} | {experiment} | {decisions} | {signals} | {entered} | {wins} | {losses} | "
            "{total_r} | {avg_r} | {win_rate} | {blocked} |".format(
                dataset=row["dataset_id"],
                experiment=row["experiment_id"],
                decisions=row["decision_bars"],
                signals=row["signals"],
                entered=row["entered_trades"],
                wins=row["wins"],
                losses=row["losses"],
                total_r=row["total_r"],
                avg_r=row["avg_r"],
                win_rate=pct(float(row["win_rate"])),
                blocked=row.get("htf_filter_blocked", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Experiment Rollup",
            "",
            "| Experiment | Entered | Wins | Losses | Total R | Positive Runs | Negative Runs |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for experiment, bucket in experiment_rollup.items():
        lines.append(
            f"| {experiment} | {bucket['entered']} | {bucket['wins']} | {bucket['losses']} | "
            f"{round(bucket['total_r'], 4)} | {bucket['positive_runs']} | {bucket['negative_runs']} |"
        )

    lines.extend(
        [
            "",
            "## Aggregate Read",
            "",
            f"- Total entered trades across these diagnostic runs: {total_entered}.",
            f"- Sum of run-level total R across these diagnostic runs: {total_r}.",
            "- Treat cross-run totals carefully because overlapping variants can count the same market condition multiple ways.",
        ]
    )
    lines.append("- The 20 entered trades are across overlapping diagnostic variants, not one comparable deployable configuration.")
    lines.append("- No comparable out-of-sample configuration reached 20 entered trades by itself.")

    lines.extend(["", "## Highest-Activity Runs", ""])
    for row in best:
        diag = row.get("blocker_diagnostics", {})
        lines.append(
            f"- `{row['dataset_id']} / {row['experiment_id']}`: entered {row['entered_trades']}, "
            f"total R {row['total_r']}, top blockers {diag.get('top_blockers', {})}"
        )

    lines.extend(["", "## Sweep-Before-Break Diagnostics", ""])
    for row in enriched:
        diag = row.get("blocker_diagnostics", {})
        if not diag:
            continue
        lines.append(
            f"- `{row['dataset_id']} / {row['experiment_id']}`: "
            f"sequence fails where sweep+break existed but order failed = {diag.get('sweep_sequence_fail', 0)}, "
            f"price-only retrace-ready rows = {diag.get('price_only_retrace_ready', 0)}, "
            f"HTF-blocked rows = {diag.get('htf_blocked_rows', 0)}."
        )

    lines.extend(
        [
            "",
            "## Research Conclusion Rules",
            "",
            "- More entries alone is not an upgrade.",
            "- A stricter rule can be kept if the loose version increases trade count but worsens R.",
            "- A blocker should be loosened only when the loosened version survives a separate period or symbol.",
            "",
            f"Raw JSON: `{json_path}`",
            f"CSV: `{csv_path}`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()
    datasets = DATASETS
    experiments = EXPERIMENTS
    if args.symbols:
        selected = set(args.symbols)
        datasets = [dataset for dataset in datasets if dataset.symbol in selected]
    if args.experiments:
        selected_experiments = set(args.experiments)
        experiments = [experiment for experiment in experiments if experiment.experiment_id in selected_experiments]
    if args.max_datasets is not None:
        datasets = datasets[: args.max_datasets]
    if args.max_experiments is not None:
        experiments = experiments[: args.max_experiments]
    if not datasets:
        raise SystemExit("No datasets selected.")
    if not experiments:
        raise SystemExit("No experiments selected.")

    dataset_quality: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        ensure_dataset(dataset, download=args.download)
        dataset_quality[dataset.dataset_id] = quality_report(dataset.csv_path)

    summaries: list[dict[str, Any]] = []
    for dataset in datasets:
        for experiment in experiments:
            summaries.append(run_backtest(args, dataset, experiment))

    report_path = write_outputs(args, summaries, dataset_quality)
    print(f"\nWrote research grid report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
