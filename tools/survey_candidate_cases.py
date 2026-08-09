"""Render a blind survey of candidate decision points for analyst selection.

The v2 evaluation contract requires that a human selects and justifies the
development cases. That requirement exists because the previous set was built
from sequential date-block placeholders and then described as "balanced across
four regimes" — a claim nobody had checked against a chart.

This tool does not select anything. It renders candidate decision points as
clean charts, numbered, so an analyst can choose by eye. It deliberately shows:

* no system bias, narrative, POI or state;
* no regime label — naming the regime is part of what the analyst decides;
* no detector objects of any kind.

Anything else would make the selection a review of the machine's opinion
rather than an independent reading of the market.

Slice boundary matches the corrected builder: a candle enters the window only
once it has **closed** at or before the decision time. The earlier harness
used the candle's open time and admitted the still-forming candle, which is
future information.

Usage::

    python tools/survey_candidate_cases.py \\
        --source data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv \\
        --start 2026-03-01 --end 2026-06-19 --every 3D \\
        --output review_queues/candidate_survey_<date>

Then open ``survey_index.md``, pick the 12–15 you want, and pass them to
``tools/seal_definition_set.py``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.data.timeframe_reconstruction import resample_ohlcv
from smc_desk.evaluation.cohort_integrity import RENDER_TIMEFRAMES

CONTEXT_CANDLES = {"15m": 180, "1h": 150, "4h": 120, "1d": 180}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", required=True, help="First candidate decision date (UTC).")
    parser.add_argument("--end", required=True, help="Last candidate decision date (UTC).")
    parser.add_argument("--every", default="3D", help="Spacing between candidates, e.g. 3D, 12h.")
    parser.add_argument("--at-hour", type=int, default=12, help="UTC hour for each decision time.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeframes", default="1d,4h,1h,15m")
    return parser.parse_args()


def _closed_history(df: pd.DataFrame, decision: pd.Timestamp) -> pd.DataFrame:
    """Only candles whose close is at or before the decision time."""
    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    if "close_time" in df.columns:
        close_times = pd.to_datetime(df["close_time"], utc=True)
    else:
        close_times = timestamps + pd.Timedelta("15min")
    return df.loc[close_times <= decision].copy()


def _slice_at(df: pd.DataFrame, decision: pd.Timestamp, timeframes: list[str]) -> dict[str, pd.DataFrame]:
    history = _closed_history(df, decision)
    if history.empty:
        raise ValueError("no closed candles at or before the decision time")
    history = history.copy()
    history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True)
    out: dict[str, pd.DataFrame] = {}
    for timeframe in timeframes:
        if timeframe == "15m":
            frame = history
        else:
            frame = resample_ohlcv(history, timeframe, decision)
        if frame.empty:
            continue
        out[timeframe] = frame.tail(CONTEXT_CANDLES.get(timeframe, 150)).reset_index(drop=True)
    return out


def _render_clean(frame: pd.DataFrame, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    o = frame["open"].astype(float).to_numpy()
    h = frame["high"].astype(float).to_numpy()
    low = frame["low"].astype(float).to_numpy()
    c = frame["close"].astype(float).to_numpy()
    n = len(frame)
    span = max(float(h.max() - low.min()), 1e-9)

    fig, ax = plt.subplots(figsize=(16, 8.5))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.grid(color="#eceff1", linewidth=0.7, alpha=0.9)
    floor = span * 0.0008
    for i in range(n):
        colour = "#159a8c" if c[i] >= o[i] else "#e65353"
        ax.plot([i, i], [low[i], h[i]], color="#242424", linewidth=0.65, zorder=2)
        ax.bar(i, max(abs(c[i] - o[i]), floor), bottom=min(o[i], c[i]), width=0.62,
               color=colour, edgecolor=colour, linewidth=0.4, zorder=3)

    step = max(1, n // 9)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [pd.Timestamp(frame["timestamp"].iloc[i]).strftime("%m-%d %H:%M") for i in ticks],
        fontsize=9, color="#5b6670",
    )
    ax.set_xlim(-1, n)
    ax.set_ylim(low.min() - span * 0.06, h.max() + span * 0.06)
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#12181c", pad=14)
    for side in ("top", "left"):
        ax.spines[side].set_visible(False)
    ax.yaxis.tick_right()
    fig.tight_layout()
    fig.savefig(path, dpi=105, facecolor="#ffffff")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    out_root = Path(args.output).expanduser().resolve()
    if out_root.exists() and any(out_root.iterdir()):
        raise SystemExit(f"Refusing to write into an existing survey: {out_root}")
    out_root.mkdir(parents=True, exist_ok=True)

    timeframes = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    unknown = [tf for tf in timeframes if tf not in RENDER_TIMEFRAMES]
    if unknown:
        raise SystemExit(f"Unsupported timeframes: {unknown}")

    source_path = Path(args.source).expanduser().resolve()
    df = pd.read_csv(source_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    decision_times = pd.date_range(
        start=pd.Timestamp(args.start, tz="UTC") + pd.Timedelta(hours=args.at_hour),
        end=pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(hours=args.at_hour),
        freq=args.every, tz="UTC",
    )

    rows: list[dict[str, Any]] = []
    for index, decision in enumerate(decision_times, start=1):
        candidate_id = f"cand_{index:02d}"
        try:
            frames = _slice_at(df, decision, timeframes)
        except ValueError as exc:
            rows.append({"candidate_id": candidate_id, "decision_time": str(decision),
                         "status": "SKIPPED", "reason": str(exc)})
            continue
        if not frames:
            rows.append({"candidate_id": candidate_id, "decision_time": str(decision),
                         "status": "SKIPPED", "reason": "no timeframe produced candles"})
            continue

        case_dir = out_root / candidate_id
        case_dir.mkdir(parents=True, exist_ok=True)
        charts = []
        for timeframe, frame in frames.items():
            name = f"{args.symbol}_{timeframe}_clean.png"
            _render_clean(
                frame, case_dir / name,
                f"{args.symbol} · {timeframe.upper()}   (decision time {decision:%Y-%m-%d %H:%M} UTC)",
            )
            charts.append(name)
        rows.append({
            "candidate_id": candidate_id,
            "decision_time": decision.isoformat().replace("+00:00", "Z"),
            "status": "RENDERED",
            "charts": charts,
            "last_closed_candle": str(frames["15m"]["timestamp"].iloc[-1])
            if "15m" in frames else None,
        })
        print(f"  {candidate_id}  {decision:%Y-%m-%d %H:%M}  ({len(charts)} charts)")

    rendered = [r for r in rows if r["status"] == "RENDERED"]
    (out_root / "survey_manifest.json").write_text(json.dumps({
        "schema": "candidate_survey_v1",
        "symbol": args.symbol,
        "source": str(source_path),
        "slice_rule": "candle enters the window only once closed at or before the decision time",
        "blinding": "No system output, detector object, or regime label is rendered.",
        "candidate_count": len(rows),
        "rendered_count": len(rendered),
        "candidates": rows,
    }, indent=2))

    lines = [
        f"# Candidate survey — {args.symbol}",
        "",
        f"{len(rendered)} candidate decision points rendered from `{source_path.name}`.",
        "",
        "These are **candidates only**. Nothing here is selected, labelled, or",
        "scored. No system output is shown, deliberately — your reading has to be",
        "independent of the machine's.",
        "",
        "## How to choose",
        "",
        "Open each candidate's charts and decide two things:",
        "",
        "1. **Do you want it?** Pick 12–15 that between them cover the conditions",
        "   you care about — clear trend, clean range, a genuine transition, and",
        "   some honestly ambiguous ones. Ambiguous cases matter most: they are",
        "   where a system either abstains correctly or invents a story.",
        "2. **What is it?** Your regime call, in your words. The old set's labels",
        "   were assigned by date block and never checked; yours replace them.",
        "",
        "Then write your picks into a selections file and run:",
        "",
        "```bash",
        "python tools/seal_definition_set.py --survey <this folder> \\",
        "    --selections my_picks.json --analyst-id <you> \\",
        "    --output data/gold_sets/<new_set_name>",
        "```",
        "",
        "## Candidates",
        "",
        "| # | decision time (UTC) | last closed 15m candle | charts |",
        "|---|---|---|---|",
    ]
    for row in rendered:
        lines.append(
            f"| `{row['candidate_id']}` | {row['decision_time']} | "
            f"{row['last_closed_candle']} | {len(row['charts'])} |"
        )
    skipped = [r for r in rows if r["status"] == "SKIPPED"]
    if skipped:
        lines += ["", f"Skipped {len(skipped)}: " + ", ".join(
            f"{r['candidate_id']} ({r['reason']})" for r in skipped)]
    (out_root / "survey_index.md").write_text("\n".join(lines) + "\n")

    print(f"\n{len(rendered)}/{len(rows)} candidates rendered in {out_root}")
    print("Open survey_index.md, pick 12-15, then run tools/seal_definition_set.py")


if __name__ == "__main__":
    main()
