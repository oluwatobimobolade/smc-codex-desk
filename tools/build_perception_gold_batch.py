#!/usr/bin/env python3
"""Build source-aligned, blind SMC chart cases for independent adjudication.

The generated cases are *candidates* for a gold set, not gold labels. Every
case contains raw OHLCV-derived charts, exact source data, and two independent
reviewer templates. Machine analysis is retained for later scoring but is never
linked from the blind-review brief.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.case_audit import audit_case
from smc_desk.case_library import file_sha256
from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, assert_not_in_holdout
from smc_desk.mtf import resample_ohlcv
from smc_desk.perception_legacy import engine_perception_objects, perception_annotation_scaffold
from smc_desk.render import render_raw_chart
from smc_desk.rules import RuleConfig, load_rule_config


TIMEFRAMES = (("15", "15m"), ("1H", "1h"), ("4H", "4h"), ("1D", "1d"))


def parse_source(value: str) -> tuple[str, Path]:
    symbol, separator, raw_path = value.partition("=")
    if not separator or not symbol.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--source must be SYMBOL=/absolute/or/relative/path.csv")
    return symbol.strip().upper(), Path(raw_path).expanduser()


def select_decision_indices(length: int, count: int, warmup_bars: int) -> list[int]:
    """Select chronological, evenly spaced decision bars without look-ahead."""
    start = warmup_bars
    end = length - 1
    if count <= 0:
        raise ValueError("case count must be positive")
    if start >= end:
        raise ValueError(f"Need more than {warmup_bars + 1} candles for a review case.")
    available = end - start + 1
    if count > available:
        raise ValueError(f"Requested {count} cases but only {available} decision bars are available.")
    if count == 1:
        return [(start + end) // 2]
    return [start + round(position * (end - start) / (count - 1)) for position in range(count)]


def _quality(df: pd.DataFrame) -> dict[str, int | str | None]:
    timestamps = pd.to_datetime(df["timestamp"], utc=False)
    deltas = timestamps.diff().dropna()
    expected = pd.Timedelta(minutes=15)
    return {
        "rows": int(len(df)),
        "start": pd.Timestamp(timestamps.iloc[0]).isoformat(),
        "end": pd.Timestamp(timestamps.iloc[-1]).isoformat(),
        "expected_step_minutes": 15,
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "out_of_order_rows": int((deltas < pd.Timedelta(0)).sum()),
        "gap_count": int((deltas > expected).sum()),
        "max_gap_minutes": float(deltas.max().total_seconds() / 60) if not deltas.empty else None,
        "nan_ohlc_rows": int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
        "zero_or_negative_volume_rows": int((pd.to_numeric(df["volume"], errors="coerce").fillna(0) <= 0).sum()),
    }


def reviewer_payload(case_id: str, reviewer_id: str) -> dict[str, Any]:
    annotations = perception_annotation_scaffold()
    annotations["label_status"] = "draft"
    annotations["reviewer_ids"] = [reviewer_id]
    return {
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "perception_annotations": annotations,
    }


def _write_blind_review(case: dict[str, Any], case_dir: Path, reviewers: list[str]) -> None:
    screenshots = case["chart_evidence"]["screenshots"]
    lines = [
        f"# Blind SMC Review - {case['case_id']}",
        "",
        "Review the raw OHLCV charts below before opening any machine-analysis file or overlay.",
        "",
        f"- Symbol: {case['symbol']}",
        f"- Venue: {case['exchange']}",
        f"- Decision candle: {case['decision_time']}",
        "- Scope: label 15m BOS, CHoCH, liquidity sweep, FVG, order block, EQH, and EQL. Use higher timeframes only as context.",
        "- Leave primitives you cannot confidently identify unlabelled; ambiguity is useful evidence.",
        "",
        "## Reviewer Files",
        "",
    ]
    lines.extend(f"- `{reviewer}.json`" for reviewer in reviewers)
    lines.append("- `adjudicated.json` (adjudicator only, after comparing both reviewer drafts)")
    lines.extend(["", "## Raw Source Charts", ""])
    for label, _timeframe in TIMEFRAMES:
        screenshot = screenshots[label]
        lines.extend([f"### {label}", f"![{case['symbol']} {label}]({screenshot})", ""])
    lines.extend(
        [
            "## Object Rules",
            "",
            "- Events require candle timestamp and price.",
            "- Zones require price_low and price_high.",
            "- BOS/CHoCH require an `internal`, `swing`, or `external` scope.",
            "- Do not call a wick-only probe a structure break without the close/displacement required by the review standard.",
            "- An adjudicator creates the final `adjudicated.json`; reviewers do not self-adjudicate.",
            "",
        ]
    )
    (case_dir / "blind_review.md").write_text("\n".join(lines), encoding="utf-8")


def _write_raw_charts(history: pd.DataFrame, decision_time: pd.Timestamp, case_dir: Path, symbol: str, chart_bars: int) -> dict[str, str]:
    charts_dir = case_dir / "raw_charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    charts: dict[str, str] = {}
    for label, timeframe in TIMEFRAMES:
        if timeframe == "15m":
            chart_df = history.tail(chart_bars).copy()
        else:
            chart_df = resample_ohlcv(history, timeframe, decision_time).tail(chart_bars).copy()  # type: ignore[arg-type]
        if chart_df.empty:
            raise ValueError(f"No closed {timeframe} candles available for {symbol} at {decision_time}.")
        output = charts_dir / f"raw_{label}.png"
        render_raw_chart(chart_df, symbol=symbol, timeframe=timeframe, output_path=str(output))
        charts[label] = str(output.resolve())
    return charts


def _write_case_manifest(
    *,
    case_dir: Path,
    case_id: str,
    symbol: str,
    decision_time: pd.Timestamp,
    analysis_window_csv: Path,
    screenshots: dict[str, str],
    engine_weak_labels_path: Path,
    holdout_matches: list[Any],
) -> None:
    manifest = {
        "manifest_version": "1.0",
        "case_id": case_id,
        "symbol": symbol,
        "decision_time": decision_time.isoformat(),
        "truth_policy": {
            "clean_charts": "review_evidence",
            "engine_weak_labels": "weak_operational_labels_only_not_gold_truth",
            "gold_requires": "two independent reviewers plus adjudicator resolution",
        },
        "no_future_leakage": {
            "decision_candle": decision_time.isoformat(),
            "analysis_window_ends_at_decision": True,
            "htf_charts_drop_incomplete_candles": True,
        },
        "files": {
            "analysis_window_15m": {
                "path": str(analysis_window_csv.resolve()),
                "sha256": file_sha256(analysis_window_csv),
            },
            "engine_weak_labels": {
                "path": str(engine_weak_labels_path.resolve()),
                "sha256": file_sha256(engine_weak_labels_path),
            },
            "raw_charts": {
                label: {"path": path, "sha256": file_sha256(Path(path))}
                for label, path in screenshots.items()
            },
        },
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
    (case_dir / "case_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_case(
    source_df: pd.DataFrame,
    *,
    symbol: str,
    source_path: Path,
    decision_index: int,
    output_root: Path,
    config: RuleConfig,
    chart_bars: int,
    reviewers: list[str],
    holdout_policy: str | Path | None = None,
    allow_holdout: bool = False,
) -> Path:
    history = source_df.iloc[: decision_index + 1].reset_index(drop=True)
    decision_time = pd.Timestamp(history["timestamp"].iloc[-1])
    visible_start = pd.Timestamp(history["timestamp"].iloc[max(0, len(history) - chart_bars)])
    holdout_matches = assert_not_in_holdout(
        start=visible_start,
        end=decision_time,
        symbol=symbol,
        action="case_generation",
        policy_path=holdout_policy,
        allow_holdout=allow_holdout,
    )
    analysis, analyzed_df = analyze_dataframe(
        df=history,
        symbol=symbol,
        timeframe="15m",
        config=config,
        notes="blind perception gold-candidate generation",
        input_type="ohlcv",
    )
    timestamp_tag = decision_time.strftime("%Y%m%d_%H%M")
    case_id = f"{symbol}_{timestamp_tag}_perception_candidate"
    case_dir = output_root / symbol / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    analysis_window_csv = case_dir / "analysis_window_15m.csv"
    analyzed_df.to_csv(analysis_window_csv, index=False)
    screenshots = _write_raw_charts(history, decision_time, case_dir, symbol, chart_bars)
    case = {
        "case_version": "1.0",
        "case_id": case_id,
        "case_kind": "perception_gold_candidate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "exchange": "BINANCE",
        "decision_time": decision_time.isoformat(),
        "data": {
            "source_name": "Binance USD-M Futures OHLCV",
            "source_csv": str(source_path.resolve()),
            "source_csv_sha256": file_sha256(source_path),
            "analysis_window_csv": str(analysis_window_csv.resolve()),
            "analysis_window_csv_sha256": file_sha256(analysis_window_csv),
            "quality": _quality(source_df),
            "visible_15m_bars_at_decision": int(len(analyzed_df)),
            "no_future_leakage_rule": "Only candles at or before the decision candle are visible; raw higher-timeframe charts exclude incomplete candles.",
        },
        "chart_evidence": {
            "instrument": symbol,
            "exchange": "BINANCE",
            "tradingview_symbol": f"BINANCE:{symbol}.P",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source": "deterministic raw OHLCV render",
            "screenshots": screenshots,
        },
        "source_alignment": {
            "ohlcv_exchange": "BINANCE",
            "chart_exchange_matches_ohlcv": True,
            "needs_human_visual_review": True,
        },
        "machine_analysis": analysis.model_dump(mode="json"),
        "expert_label": {
            "review_status": "unreviewed",
            "perception_annotations": perception_annotation_scaffold(),
        },
    }
    (case_dir / "case.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    (case_dir / "machine_analysis.json").write_text(json.dumps(case["machine_analysis"], indent=2), encoding="utf-8")
    engine_weak_labels = {
        "schema_version": "1.0",
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "deterministic_engine_weak_labels_not_gold_truth",
        "truth_status": "weak_operational_labels_only",
        "promotion_policy": "May be scored only after adjudicated human labels exist; never import as gold.",
        "objects": [item.model_dump(mode="json") for item in engine_perception_objects(case["machine_analysis"])],
    }
    engine_weak_labels_path = case_dir / "engine_weak_labels.json"
    engine_weak_labels_path.write_text(json.dumps(engine_weak_labels, indent=2), encoding="utf-8")
    for reviewer in reviewers:
        (case_dir / f"{reviewer}.json").write_text(json.dumps(reviewer_payload(case_id, reviewer), indent=2), encoding="utf-8")
    adjudicated = reviewer_payload(case_id, "")
    adjudicated["perception_annotations"]["reviewer_ids"] = reviewers
    adjudicated["perception_annotations"]["notes"] = "Populate only after comparing the two independent reviewer drafts; set label_status=adjudicated and adjudicated_by before import."
    adjudicated["adjudicator_justification"] = ""
    adjudicated.pop("reviewer_id")
    (case_dir / "adjudicated.json").write_text(json.dumps(adjudicated, indent=2), encoding="utf-8")
    _write_blind_review(case, case_dir, reviewers)
    _write_case_manifest(
        case_dir=case_dir,
        case_id=case_id,
        symbol=symbol,
        decision_time=decision_time,
        analysis_window_csv=analysis_window_csv,
        screenshots=screenshots,
        engine_weak_labels_path=engine_weak_labels_path,
        holdout_matches=holdout_matches,
    )
    return case_dir


def build_batch(
    sources: list[tuple[str, Path]],
    *,
    output_root: Path,
    cases_per_symbol: int,
    warmup_bars: int,
    chart_bars: int,
    config: RuleConfig,
    reviewers: list[str],
    holdout_policy: str | Path | None = None,
    allow_holdout: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    built: list[dict[str, str]] = []
    for symbol, source in sources:
        df = load_ohlcv_csv(str(source))
        indices = select_decision_indices(len(df), cases_per_symbol, warmup_bars)
        for decision_index in indices:
            case_dir = build_case(
                df,
                symbol=symbol,
                source_path=source,
                decision_index=decision_index,
                output_root=output_root,
                config=config,
                chart_bars=chart_bars,
                reviewers=reviewers,
                holdout_policy=holdout_policy,
                allow_holdout=allow_holdout,
            )
            case_path = case_dir / "case.json"
            audit = audit_case(case_path)
            if not audit["usable_for_machine_research"]:
                raise RuntimeError(f"Generated case failed source-alignment audit: {case_path}: {audit['warnings']}")
            built.append({"symbol": symbol, "case_id": audit["case_id"], "case_path": str(case_path.resolve())})
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "blind_perception_gold_candidates",
        "reviewers_required": reviewers,
        "cases_per_symbol": cases_per_symbol,
        "case_count": len(built),
        "source_policy": "Raw OHLCV charts only in blind_review.md; machine_analysis.json is retained for post-adjudication scoring only.",
        "weak_label_policy": "engine_weak_labels.json is a deterministic weak-label artifact, not gold truth.",
        "promotion_policy": "No case is gold until two independent reviewer files are reconciled by an adjudicator and imported as an adjudicated label set.",
        "holdout_policy": str(Path(holdout_policy).resolve()) if holdout_policy else str(DEFAULT_HOLDOUT_POLICY),
        "allow_holdout": allow_holdout,
        "cases": built,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build blind, source-aligned SMC perception cases for expert adjudication.")
    parser.add_argument("--source", type=parse_source, action="append", required=True, help="Repeat SYMBOL=path/to/15m.csv for each pair.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--cases-per-symbol", type=int, default=12)
    parser.add_argument("--warmup-bars", type=int, default=400)
    parser.add_argument("--chart-bars", type=int, default=220)
    parser.add_argument("--reviewers", nargs="+", default=["reviewer_a", "reviewer_b"])
    parser.add_argument("--rules")
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--allow-holdout", action="store_true", help="Required only for deliberate final-evaluation case generation.")
    args = parser.parse_args()
    if len(args.reviewers) < 2:
        raise SystemExit("At least two independent reviewer templates are required for a gold candidate batch.")
    manifest = build_batch(
        args.source,
        output_root=Path(args.output_root),
        cases_per_symbol=args.cases_per_symbol,
        warmup_bars=args.warmup_bars,
        chart_bars=args.chart_bars,
        config=load_rule_config(args.rules),
        reviewers=args.reviewers,
        holdout_policy=args.holdout_policy,
        allow_holdout=args.allow_holdout,
    )
    print(f"Built {manifest['case_count']} blind perception candidates at {Path(args.output_root).resolve()}")
    print("They are not gold labels yet. Review blind_review.md, adjudicate, then import the final annotation set.")


if __name__ == "__main__":
    main()
