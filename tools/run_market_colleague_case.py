#!/usr/bin/env python3
"""Build one local-first SMC market-colleague case.

This is the operator-facing spine for the desk:

- canonical Binance futures 15m OHLCV is the source of truth;
- 1H/4H/1D charts are derived from the 15m history with closed-candle gating;
- the deterministic engine writes a sealed JSON read;
- clean charts are kept separate from the annotated engine chart;
- optional TradingView/WebBridge screenshots can be attached as visual evidence,
  but they do not become authority over the OHLCV data.
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

from smc_desk.case_library import data_quality_report, file_sha256, normalize_ohlcv_timestamps
from smc_desk.colleague.orchestrator import run_colleague_analysis
from smc_desk.colleague.request_contract import ColleagueRunRequest
from smc_desk.engine import analyze_dataframe, build_trade_plan_markdown, format_level, format_zone, load_ohlcv_csv
from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, assert_not_in_holdout
from smc_desk.models import AnalysisResult
from smc_desk.mtf import build_mtf_snapshot, derive_htf_consensus_bias, resample_ohlcv, snapshot_to_dict
from smc_desk.render import render_raw_chart, render_smc_annotated
from smc_desk.rules import RuleConfig, load_rule_config


DEFAULT_DATA_ROOT = ROOT / "data" / "ohlcv" / "binance_futures"
DEFAULT_CHART_BARS = {"15m": 220, "1h": 240, "4h": 180, "1d": 180}
TF_LABELS = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
TF_ORDER = ("15m", "1h", "4h", "1d")


def normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def default_ohlcv_path(symbol: str, data_root: Path = DEFAULT_DATA_ROOT, tag: str = "4year") -> Path:
    normalized = normalize_symbol(symbol)
    return data_root / normalized / f"{normalized}_15m_{tag}.csv"


def _parse_decision_time(value: str | None, df: pd.DataFrame) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp(df["timestamp"].iloc[-1])
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.tz_convert("UTC").tz_localize(None)


def _load_local_15m(path: Path) -> pd.DataFrame:
    df = normalize_ohlcv_timestamps(load_ohlcv_csv(str(path)))
    if df.empty:
        raise ValueError(f"OHLCV source is empty: {path}")
    return df


def _slice_history(df: pd.DataFrame, requested_decision_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.Timestamp]:
    history = df.loc[pd.to_datetime(df["timestamp"], utc=False) <= requested_decision_time].reset_index(drop=True)
    if history.empty:
        first = pd.Timestamp(df["timestamp"].iloc[0]).isoformat()
        raise ValueError(f"Decision time {requested_decision_time.isoformat()} is before first candle {first}.")
    decision_time = pd.Timestamp(history["timestamp"].iloc[-1])
    return history, decision_time


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _write_visible_data(history: pd.DataFrame, decision_time: pd.Timestamp, output_dir: Path) -> dict[str, dict[str, Any]]:
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}

    visible_15m = data_dir / "visible_history_15m.csv"
    history.to_csv(visible_15m, index=False)
    files["visible_history_15m"] = {"path": str(visible_15m.resolve()), "sha256": file_sha256(visible_15m), "rows": int(len(history))}

    for tf in ("1h", "4h", "1d"):
        htf = resample_ohlcv(history, tf, decision_time)  # type: ignore[arg-type]
        path = data_dir / f"visible_history_{tf}.csv"
        htf.to_csv(path, index=False)
        files[f"visible_history_{tf}"] = {"path": str(path.resolve()), "sha256": file_sha256(path), "rows": int(len(htf))}

    return files


def _render_local_charts(
    *,
    history: pd.DataFrame,
    analyzed_df: pd.DataFrame,
    analysis: AnalysisResult,
    decision_time: pd.Timestamp,
    symbol: str,
    output_dir: Path,
    chart_bars: dict[str, int],
) -> dict[str, dict[str, str]]:
    charts_dir = output_dir / "charts"
    raw_dir = charts_dir / "clean_raw"
    annotated_dir = charts_dir / "annotated"
    raw_dir.mkdir(parents=True, exist_ok=True)
    annotated_dir.mkdir(parents=True, exist_ok=True)

    local_charts: dict[str, dict[str, str]] = {"clean_raw": {}, "annotated": {}}
    for tf in TF_ORDER:
        if tf == "15m":
            chart_df = history.tail(chart_bars[tf]).copy()
        else:
            chart_df = resample_ohlcv(history, tf, decision_time).tail(chart_bars[tf]).copy()  # type: ignore[arg-type]
        if chart_df.empty:
            raise ValueError(f"No visible {tf} candles available for {symbol} at {decision_time.isoformat()}.")
        output = raw_dir / f"{symbol}_{tf}_clean.png"
        render_raw_chart(chart_df, symbol=symbol, timeframe=tf, output_path=str(output))
        local_charts["clean_raw"][tf] = str(output.resolve())

    annotated_path = annotated_dir / f"{symbol}_15m_engine_annotated.png"
    render_smc_annotated(
        analyzed_df,
        analysis,
        str(annotated_path),
        min_conf="medium",
        title=f"{symbol} 15m engine annotated | {analysis.trade_plan.verdict} Grade {analysis.trade_plan.setup_grade}",
    )
    local_charts["annotated"]["15m"] = str(annotated_path.resolve())
    return local_charts


def _chart_manifest(local_charts: dict[str, dict[str, str]]) -> dict[str, dict[str, dict[str, Any]]]:
    manifest: dict[str, dict[str, dict[str, Any]]] = {}
    for group, paths in local_charts.items():
        manifest[group] = {}
        for label, raw_path in paths.items():
            path = Path(raw_path)
            manifest[group][label] = {"path": str(path.resolve()), "sha256": file_sha256(path)}
    return manifest


def _load_tradingview_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "not_attached",
            "role": "optional_visual_cross_check_not_authority",
            "expected_source": "tools/smc_webbridge_analyst.py --mode capture",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    screenshots = payload.get("screenshots") if isinstance(payload, dict) else None
    screenshot_hashes: dict[str, dict[str, Any]] = {}
    if isinstance(screenshots, dict):
        for label, value in screenshots.items():
            screenshot_path = Path(str(value)).expanduser()
            screenshot_hashes[str(label)] = {
                "path": str(screenshot_path.resolve()),
                "exists": screenshot_path.exists(),
                "sha256": file_sha256(screenshot_path) if screenshot_path.exists() else None,
            }
    return {
        "status": "attached",
        "role": "optional_visual_cross_check_not_authority",
        "manifest_path": str(path.resolve()),
        "manifest_sha256": file_sha256(path),
        "payload": payload,
        "screenshot_hashes": screenshot_hashes,
    }


def _failed_checklist_items(analysis: AnalysisResult) -> list[str]:
    checklist = analysis.trade_plan.checklist or {}
    return [key for key, passed in checklist.items() if not passed]


def _mtf_lines(snapshot: dict[str, Any]) -> list[str]:
    lines = []
    for tf in ("1h", "4h", "1d"):
        ctx = snapshot[tf]
        lines.append(
            f"- {TF_LABELS[tf]}: {ctx['bias']} bias, {ctx['candle_count']} closed candles, "
            f"last close {format_level(ctx['last_close'])}, last structure "
            f"{ctx['last_structure_label'] or 'none'} {ctx['last_structure_direction'] or ''}".rstrip()
        )
    return lines


def _build_thesis_markdown(
    *,
    symbol: str,
    source_path: Path,
    decision_time: pd.Timestamp,
    analysis: AnalysisResult,
    mtf_snapshot: dict[str, Any],
    local_charts: dict[str, dict[str, str]],
    tradingview_evidence: dict[str, Any],
) -> str:
    plan = analysis.trade_plan
    failed = _failed_checklist_items(analysis)
    latest_close = analysis.metrics.get("latest_close")
    selected_poi = plan.selected_poi
    htf_poi = plan.selected_htf_poi
    raw_charts = local_charts["clean_raw"]
    annotated_chart = local_charts["annotated"]["15m"]

    lines = [
        f"# {symbol} Market Colleague Thesis",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Decision candle: {decision_time.isoformat()}",
        f"Source: `{source_path.resolve()}`",
        "",
        "## Verdict",
        "",
        f"**{plan.verdict} / Grade {plan.setup_grade}**. Direction: **{plan.direction}**. "
        f"Risk allowed: **{plan.risk_pct:.1f}%**. Latest close: **{format_level(float(latest_close) if latest_close is not None else None)}**.",
        "",
        plan.thesis,
        "",
        "## Multi-Timeframe Read",
        "",
        f"- Execution consensus: {mtf_snapshot['execution_consensus']}",
        f"- Descriptive alignment: {mtf_snapshot['alignment']} ({mtf_snapshot['agreement_count']}/{mtf_snapshot['total_count']})",
        *_mtf_lines(mtf_snapshot),
        "",
        "## Key Areas",
        "",
        f"- Selected 15m POI: {selected_poi.kind if selected_poi else 'None'} "
        f"{format_zone(selected_poi.low, selected_poi.high) if selected_poi else ''}".rstrip(),
        (
            f"- Selected HTF POI: {htf_poi.timeframe} {htf_poi.zone.kind} "
            f"{format_zone(htf_poi.zone.low, htf_poi.zone.high)} "
            f"({htf_poi.state}, {htf_poi.distance_atr:.2f} ATR away)"
            if htf_poi
            else "- Selected HTF POI: None"
        ),
        f"- Entry zone: {format_zone(plan.entry_low, plan.entry_high)}",
        f"- Execution SL: {format_level(plan.invalidation)}",
        f"- Structural invalidation: {format_level(plan.structural_invalidation)}",
        f"- Liquidity target: {format_level(plan.liquidity_target)}",
        f"- Targets: {', '.join(format_level(target) for target in plan.targets) or 'None'}",
        f"- Risk/Reward: {plan.risk_reward if plan.risk_reward is not None else 'N/A'}",
        "",
        "## What Would Make This Tradeable",
        "",
    ]
    if plan.verdict == "Execute":
        lines.append("- The engine has an executable plan. Human review should verify the marked structure, POI freshness, stop logic, and TradingView source match before any real risk.")
    elif plan.verdict in {"Watch", "Watch Retrace", "Watch HTF POI"}:
        lines.extend(f"- {condition}" for condition in (plan.conditions or ["Wait for the missing confirmation before execution."]))
    else:
        if failed:
            lines.extend(f"- Failed: {item.replace('_', ' ')}" for item in failed[:8])
        else:
            lines.append("- No complete setup is present. Stand aside until structure, liquidity, POI, stop, and target logic align.")
    if plan.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in plan.warnings)

    lines.extend(
        [
            "",
            "## Chart Evidence",
            "",
            "Clean charts are for independent visual review. The annotated chart is the engine explanation layer.",
            "",
            f"![15m annotated]({annotated_chart})",
            "",
        ]
    )
    for tf in TF_ORDER:
        lines.extend([f"### {TF_LABELS[tf]} Clean", f"![{symbol} {tf} clean]({raw_charts[tf]})", ""])

    lines.extend(["## TradingView/WebBridge Evidence", ""])
    if tradingview_evidence["status"] == "attached":
        lines.append(f"- Attached manifest: `{tradingview_evidence['manifest_path']}`")
        screenshots = tradingview_evidence.get("screenshot_hashes", {})
        for label, meta in screenshots.items():
            lines.append(f"- {label}: `{meta['path']}` (exists={meta['exists']})")
    else:
        lines.append("- Not attached for this case. This is still valid as a local OHLCV-engine case, but not yet visually cross-checked against TradingView.")

    lines.extend(["", "## Engine Trade Plan Detail", "", build_trade_plan_markdown(analysis).strip(), ""])
    return "\n".join(lines)


def _build_review_prompt(
    *,
    symbol: str,
    decision_time: pd.Timestamp,
    local_charts: dict[str, dict[str, str]],
    output_dir: Path,
) -> str:
    raw_charts = local_charts["clean_raw"]
    return "\n".join(
        [
            f"# Independent SMC Review Prompt - {symbol}",
            "",
            "You are reviewing a local-first SMC case. Start from the clean charts only.",
            "Do not read `engine_analysis.json` until after you write your independent read.",
            "",
            f"- Symbol: {symbol}",
            f"- Decision candle: {decision_time.isoformat()}",
            f"- Case folder: `{output_dir.resolve()}`",
            "",
            "## Clean Charts",
            "",
            *[f"- {TF_LABELS[tf]}: `{raw_charts[tf]}`" for tf in TF_ORDER],
            "",
            "## Tasks",
            "",
            "1. Identify HTF bias from 1D/4H/1H without using engine labels.",
            "2. Mark real protected highs/lows, not internal noise.",
            "3. Identify whether liquidity was swept before displacement.",
            "4. Identify valid FVG/OB POIs and whether they are fresh or mitigated.",
            "5. Decide Pass, Watch, or Execute. If Execute, state entry, SL, TP, and invalidation.",
            "6. Then open `engine_analysis.json` and compare disagreements.",
            "",
            "Return the review as JSON or concise notes. Any disagreement is useful training evidence.",
            "",
        ]
    )


def build_market_colleague_case(
    *,
    symbol: str,
    source_path: Path,
    output_dir: Path,
    config: RuleConfig,
    decision_time: str | None = None,
    chart_bars: dict[str, int] | None = None,
    tradingview_manifest: Path | None = None,
    bias: str | None = None,
    holdout_policy: str | Path | None = DEFAULT_HOLDOUT_POLICY,
    allow_holdout: bool = False,
    include_legacy_comparison: bool = True,
    render_charts: bool = True,
    outcome_horizon_bars: int = 96,
) -> dict[str, Any]:
    request = ColleagueRunRequest(
        symbol=symbol,
        source_path=str(source_path.expanduser()),
        output_dir=str(output_dir.expanduser()),
        decision_time=decision_time,
        bias=bias,  # type: ignore[arg-type]
        tradingview_manifest=str(tradingview_manifest.expanduser()) if tradingview_manifest else None,
        holdout_policy=str(holdout_policy) if holdout_policy else None,
        allow_holdout=allow_holdout,
        include_legacy_comparison=include_legacy_comparison,
        render_charts=render_charts,
        outcome_horizon_bars=outcome_horizon_bars,
        chart_bars=dict(DEFAULT_CHART_BARS | (chart_bars or {})),
    )
    return run_colleague_analysis(request, config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one PerceptionEngineV2-led Market Colleague analysis run.")
    parser.add_argument("--symbol", required=True, help="Example: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT.")
    parser.add_argument("--ohlcv", help="Override canonical 15m OHLCV CSV.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--tag", default="4year")
    parser.add_argument("--decision-time", help="Decision candle timestamp. Defaults to the latest candle in the CSV.")
    parser.add_argument("--output-dir", help="Default: analysis_runs/<SYMBOL>_<decision_tag>_colleague.")
    parser.add_argument("--rules")
    parser.add_argument("--bias", choices=["bullish", "bearish"], help="Diagnostic override. Default uses strict HTF consensus.")
    parser.add_argument("--tradingview-manifest", help="Optional screenshots.json from tools/smc_webbridge_analyst.py.")
    parser.add_argument("--chart-bars-15m", type=int, default=DEFAULT_CHART_BARS["15m"])
    parser.add_argument("--chart-bars-1h", type=int, default=DEFAULT_CHART_BARS["1h"])
    parser.add_argument("--chart-bars-4h", type=int, default=DEFAULT_CHART_BARS["4h"])
    parser.add_argument("--chart-bars-1d", type=int, default=DEFAULT_CHART_BARS["1d"])
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--allow-holdout", action="store_true", help="Only for deliberate final-evaluation or live-shadow review.")
    parser.add_argument("--no-legacy-comparison", action="store_true", help="Disable legacy engine comparison artifacts for this run.")
    parser.add_argument("--no-render-charts", action="store_true", help="Skip chart rendering for batch/research runs.")
    parser.add_argument("--outcome-horizon-bars", type=int, default=96)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbol = normalize_symbol(args.symbol)
    source_path = Path(args.ohlcv).expanduser() if args.ohlcv else default_ohlcv_path(symbol, Path(args.data_root), args.tag)
    config = load_rule_config(args.rules)

    source_df = _load_local_15m(source_path)
    requested_decision_time = _parse_decision_time(args.decision_time, source_df)
    _, effective_decision_time = _slice_history(source_df, requested_decision_time)
    decision_tag = effective_decision_time.strftime("%Y%m%d_%H%M")
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    manifest = build_market_colleague_case(
        symbol=symbol,
        source_path=source_path,
        output_dir=output_dir if output_dir else ROOT / "analysis_runs" / f"{symbol}_{decision_tag}_colleague",
        config=config,
        decision_time=args.decision_time,
        chart_bars={
            "15m": args.chart_bars_15m,
            "1h": args.chart_bars_1h,
            "4h": args.chart_bars_4h,
            "1d": args.chart_bars_1d,
        },
        tradingview_manifest=Path(args.tradingview_manifest) if args.tradingview_manifest else None,
        bias=args.bias,
        holdout_policy=args.holdout_policy,
        allow_holdout=args.allow_holdout,
        include_legacy_comparison=not args.no_legacy_comparison,
        render_charts=not args.no_render_charts,
        outcome_horizon_bars=args.outcome_horizon_bars,
    )
    run_dir = Path(manifest["files"]["request.json"]["path"]).parent
    decision = json.loads((run_dir / "scenarios" / "decision.json").read_text(encoding="utf-8"))
    print(f"Built market-colleague analysis run: {run_dir}")
    print(
        f"{symbol} {manifest['decision_candle_open']} -> {decision['action']} "
        f"(primary perception: {manifest['primary_perception_source']}, legacy: {manifest['legacy_engine_role']})"
    )
    print(f"Thesis: {manifest['files']['reports/colleague_thesis.md']['path']}")
    print(f"Run manifest: {run_dir / 'run_manifest.json'}")


if __name__ == "__main__":
    main()
