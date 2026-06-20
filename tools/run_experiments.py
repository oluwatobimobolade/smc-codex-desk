#!/usr/bin/env python3
"""Run fixed holdout experiments and write a comparison report."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv/bin/python")
SCRIPT = str(ROOT / "tools/backtest_smc_elite_mtf.py")
HOLDOUT = str(ROOT / "data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_holdout_20260601_20260618.csv")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

BASE = [
    PY, SCRIPT, "--ohlcv", HOLDOUT,
    "--symbol", "BTCUSDT", "--timeframe", "15m",
    "--warmup-bars", "400", "--max-hold-bars", "96", "--cost-bps", "4.0",
    "--decision-step", "4",
]

EXPERIMENTS = [
    ("holdout_step4_baseline", "Baseline: 24-bar pending expiration, HTF bias+alignment on", {}),
    ("holdout_step4_wait8", "Q1a: 8-bar pending expiration", {"entry-wait-bars": "8"}),
    ("holdout_step4_wait16", "Q1b: 16-bar pending expiration", {"entry-wait-bars": "16"}),
    ("holdout_step4_wait32", "Q1c: 32-bar pending expiration", {"entry-wait-bars": "32"}),
    ("holdout_step4_no_watch_retrace", "Q2: Watch Retrace OFF", {"include-watch-retrace": "off"}),
    ("holdout_step4_no_htf_bias", "Q3: HTF bias OFF", {"use-htf-bias": "off", "require-htf-alignment": "off"}),
    ("holdout_step4_no_alignment", "Q4: HTF alignment OFF, 1H bias still on", {"require-htf-alignment": "off"}),
    ("holdout_step4_nearest", "Q5a: POI nearest", {"poi-selection": "nearest"}),
    ("holdout_step4_best_location", "Q5b: POI best_location", {"poi-selection": "best_location"}),
    ("holdout_step4_midpoint", "Q6: midpoint entry", {"entry-mode": "midpoint"}),
]

summaries: list[dict] = []

for run_name, hypothesis, overrides in EXPERIMENTS:
    cmd = list(BASE) + [
        "--run-name", run_name,
        "--run-date", RUN_DATE,
        "--entry-wait-bars", overrides.get("entry-wait-bars", "24"),
        "--entry-mode", overrides.get("entry-mode", "boundary"),
        "--poi-selection", overrides.get("poi-selection", "balanced"),
        "--use-htf-bias", overrides.get("use-htf-bias", "on"),
        "--require-htf-alignment", overrides.get("require-htf-alignment", "on"),
        "--include-watch-retrace", overrides.get("include-watch-retrace", "on"),
        "--hypothesis", hypothesis,
    ]
    print(f"\n=== {run_name} ===", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)
        raise SystemExit(result.returncode)

    summary_path = ROOT / "backtests" / RUN_DATE / f"BTCUSDT_{run_name}" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summaries.append(summary)
    print(
        f"  decisions={summary['decision_bars']} "
        f"signals={summary['signals']} entered={summary['entered_trades']} "
        f"wins={summary['wins']} losses={summary['losses']} total_r={summary['total_r']} "
        f"htf_blocked={summary.get('htf_filter_blocked', 0)}",
        flush=True,
    )


def pct(value: float) -> str:
    return f"{value:.0%}"


report = ROOT / "backtests" / RUN_DATE / "comparison_report_fixed.md"
lines = [
    f"# Fixed Holdout Experiment Comparison ({RUN_DATE})",
    "",
    "All runs use the fixed open-time MTF resampling and the same `decision-step=4` unless noted.",
    "",
    "| Run | Decisions | Signals | Entered | Wins | Losses | Total R | Win% | HTF Blocked |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for summary in summaries:
    lines.append(
        "| {run} | {decisions} | {signals} | {entered} | {wins} | {losses} | {total_r} | {win_rate} | {blocked} |".format(
            run=summary["run_name"],
            decisions=summary["decision_bars"],
            signals=summary["signals"],
            entered=summary["entered_trades"],
            wins=summary["wins"],
            losses=summary["losses"],
            total_r=summary["total_r"],
            win_rate=pct(summary["win_rate"]),
            blocked=summary.get("htf_filter_blocked", 0),
        )
    )

lines.extend(
    [
        "",
        "## Reading Notes",
        "",
        "- These are diagnostic runs only. No configuration reached 20 entered trades.",
        "- Compare runs by behavior first: signal count, fills, blockers, and whether removing filters creates worse trades.",
        "- Do not promote a rule from this table until it survives more data or another instrument.",
        "",
    ]
)
report.write_text("\n".join(lines), encoding="utf-8")
print(f"\nWrote comparison report: {report}", flush=True)

print("\n=== ALL HOLDOUT EXPERIMENTS DONE ===", flush=True)
