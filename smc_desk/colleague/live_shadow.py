from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from smc_desk.colleague.orchestrator import run_colleague_analysis
from smc_desk.colleague.request_contract import ColleagueRunRequest, normalize_symbol
from smc_desk.colleague.tradingview_live_manifest import build_live_visual_manifest
from smc_desk.data.live_ohlcv import acquire_verified_closed_ohlcv
from smc_desk.rules import RuleConfig


CaptureFn = Callable[..., tuple[Path, dict[str, Any]]]
MarketDataFn = Callable[..., tuple[Path, dict[str, Any]]]
AnalysisFn = Callable[[ColleagueRunRequest, RuleConfig], dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_or_missing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    return _read_json(path)


def _decision_time_from_market_manifest(manifest: dict[str, Any]) -> str:
    """Use actual acquisition time as the decision-time availability boundary."""
    try:
        return str(manifest["fetched_at"])
    except KeyError as exc:
        raise ValueError("Market-truth manifest is missing fetched_at") from exc


def _source_15m_from_market_manifest(manifest: dict[str, Any]) -> Path:
    try:
        return Path(str(manifest["source_csv"])).expanduser().resolve()
    except KeyError as exc:
        raise ValueError("Market-truth manifest is missing source_csv") from exc


def _semantic_summary(run_dir: Path) -> dict[str, Any]:
    graph = _json_or_missing(run_dir / "perception" / "mtf_state_graph.json")
    overlay = graph.get("semantic_overlay") if isinstance(graph, dict) else None
    if not isinstance(overlay, dict):
        return {}
    summary = overlay.get("summary")
    return summary if isinstance(summary, dict) else {}


def _summarize_success(symbol: str, market_manifest_path: Path, capture_manifest_path: Path, run_manifest: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_manifest["files"]["request.json"]["path"]).parent
    decision = _json_or_missing(run_dir / "scenarios" / "decision.json")
    alignment = _json_or_missing(run_dir / "external" / "alignment_report.json")
    graph = _json_or_missing(run_dir / "perception" / "mtf_state_graph.json")
    outcome = _json_or_missing(run_dir / "outcome" / "pending.json")
    thesis = run_dir / "reports" / "colleague_thesis.md"
    return {
        "symbol": symbol,
        "status": "ok",
        "market_truth_manifest": str(market_manifest_path),
        "capture_manifest": str(capture_manifest_path),
        "run_dir": str(run_dir),
        "run_manifest": str(run_dir / "run_manifest.json"),
        "decision_candle_open": run_manifest.get("decision_candle_open"),
        "decision_available_at": run_manifest.get("decision_available_at"),
        "alignment_status": alignment.get("status"),
        "alignment_blocking_failures": len(alignment.get("blocking_failures") or []),
        "decision_action": decision.get("action"),
        "capital_risk": decision.get("capital_risk"),
        "graph_version": graph.get("graph_version"),
        "graph_nodes": len(graph.get("nodes") or []),
        "graph_edges": len(graph.get("edges") or []),
        "semantic_summary": _semantic_summary(run_dir),
        "outcome_status": outcome.get("status"),
        "outcome_resolution_due_at": outcome.get("resolution_due_at"),
        "thesis": str(thesis) if thesis.exists() else None,
        "market_edge_claimed": False,
        "execution_authority_changed": False,
    }


def _summarize_failure(symbol: str, symbol_dir: Path, exc: BaseException) -> dict[str, Any]:
    payload = {
        "symbol": symbol,
        "status": "failed",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(limit=12),
        "market_edge_claimed": False,
        "execution_authority_changed": False,
    }
    symbol_dir.mkdir(parents=True, exist_ok=True)
    (symbol_dir / "error.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _write_summary_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Live Shadow Universe Summary",
        "",
        f"Created: {summary['created_at']}",
        f"Output root: `{summary['output_root']}`",
        "",
        "This is observe/log only. No paper execution, live execution, or market edge claim is enabled.",
        "",
        "| Symbol | Status | Alignment | Decision | Graph | Outcome Due |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in summary["symbols"]:
        graph = (
            f"{result.get('graph_nodes', 0)} nodes / {result.get('graph_edges', 0)} edges"
            if result.get("status") == "ok"
            else "-"
        )
        lines.append(
            "| {symbol} | {status} | {alignment} | {decision} | {graph} | {due} |".format(
                symbol=result.get("symbol"),
                status=result.get("status"),
                alignment=result.get("alignment_status", "-"),
                decision=result.get("decision_action", result.get("error_type", "-")),
                graph=graph,
                due=result.get("outcome_resolution_due_at", "-"),
            )
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_live_shadow_universe(
    *,
    symbols: list[str],
    output_root: Path,
    config: RuleConfig,
    bars: int = 500,
    timeout_ms: int = 60000,
    session_prefix: str = "smc-tv-live-shadow",
    allow_holdout: bool = True,
    continue_on_error: bool = True,
    market_data_fn: MarketDataFn = acquire_verified_closed_ohlcv,
    capture_fn: CaptureFn = build_live_visual_manifest,
    analysis_fn: AnalysisFn = run_colleague_analysis,
) -> dict[str, Any]:
    """Run observe-only live colleague packages for a symbol universe.

    Each symbol gets verified Binance market truth, a separate TradingView visual capture, and a sealed colleague package.
    Failures are isolated by symbol so one bad browser/data fetch does not hide
    whether the rest of the universe is reproducible.
    """

    started = datetime.now(timezone.utc)
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for raw_symbol in symbols:
        symbol = normalize_symbol(raw_symbol)
        symbol_dir = output_root / "symbols" / symbol
        capture_dir = symbol_dir / "tradingview_capture"
        run_dir = symbol_dir / "colleague_run"
        try:
            market_manifest_path, market_manifest = market_data_fn(
                symbol=symbol,
                output_dir=symbol_dir / "market_truth",
                interval="15m",
                limit=bars,
                min_bars=min(100, max(20, bars // 2)),
                timeout=max(10.0, float(timeout_ms) / 1000.0),
                webbridge_session=f"{session_prefix}-market-{symbol.lower()}",
            )
            capture_manifest_path: Path | None = None
            visual_capture_error: dict[str, Any] | None = None
            try:
                capture_manifest_path, _capture_manifest = capture_fn(
                    symbol=symbol,
                    output_dir=capture_dir,
                    session=f"{session_prefix}-visual-{symbol.lower()}",
                    bars=bars,
                    timeout_ms=timeout_ms,
                )
            except Exception as capture_exc:
                visual_capture_error = {
                    "status": "failed",
                    "error_type": type(capture_exc).__name__,
                    "error": str(capture_exc),
                }
                capture_dir.mkdir(parents=True, exist_ok=True)
                (capture_dir / "visual_capture_error.json").write_text(
                    json.dumps(visual_capture_error, indent=2),
                    encoding="utf-8",
                )

            request = ColleagueRunRequest(
                symbol=symbol,
                source_path=str(_source_15m_from_market_manifest(market_manifest)),
                output_dir=str(run_dir),
                decision_time=_decision_time_from_market_manifest(market_manifest),
                tradingview_manifest=None if capture_manifest_path is None else str(capture_manifest_path),
                market_truth_manifest=str(market_manifest_path),
                allow_holdout=allow_holdout,
                run_id=f"{symbol}_live_shadow",
                include_legacy_comparison=False,
            )
            run_manifest = analysis_fn(request, config)
            success = _summarize_success(
                symbol,
                market_manifest_path,
                capture_manifest_path or capture_dir / "visual_capture_error.json",
                run_manifest,
            )
            success["visual_capture"] = visual_capture_error or {"status": "ok"}
            results.append(success)
        except Exception as exc:
            results.append(_summarize_failure(symbol, symbol_dir, exc))
            if not continue_on_error:
                raise

    completed = datetime.now(timezone.utc)
    failures = [item for item in results if item.get("status") != "ok"]
    summary = {
        "live_shadow_universe_version": "0.1",
        "created_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "output_root": str(output_root),
        "symbols_requested": [normalize_symbol(symbol) for symbol in symbols],
        "symbols_completed": [item["symbol"] for item in results if item.get("status") == "ok"],
        "symbols_failed": [item["symbol"] for item in failures],
        "status": "PASS" if not failures else "PARTIAL" if len(failures) < len(results) else "FAIL",
        "authority": "observe_only_live_shadow",
        "market_edge_claimed": False,
        "paper_execution_enabled": False,
        "live_execution_enabled": False,
        "symbols": results,
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _write_summary_markdown(summary, output_root / "summary.md")
    return summary
