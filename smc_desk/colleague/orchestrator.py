from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.case_library import file_sha256
from smc_desk.colleague.analysis_package import AnalysisPackageWriter
from smc_desk.colleague.decision_summary import (
    build_confirmed_state,
    build_decision,
    build_mtf_state_graph,
    build_provisional_state,
    build_scenario_tree,
)
from smc_desk.colleague.request_contract import ColleagueRunRequest, TIMEFRAME_ORDER
from smc_desk.colleague.run_context import build_run_market_context, dataframe_to_candles
from smc_desk.colleague.tradingview_alignment import build_alignment_report
from smc_desk.colleague.outcome_logging import (
    build_event_ledger_records,
    build_outcome_contract,
    event_ledger_jsonl,
    unresolved_resolution_stub,
)
from smc_desk.colleague.similar_cases import retrieve_similar_cases
from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, assert_not_in_holdout
from smc_desk.mtf_current import build_mtf_graph
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.render import render_raw_chart, render_smc_annotated
from smc_desk.rendering.mtf_mosaic import render_mtf_mosaic
from smc_desk.rules import RuleConfig
from smc_desk.colleague.thesis_builder import build_colleague_thesis


def _json_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(json.dumps(model, default=str))


def _load_tradingview_evidence(path: str | None) -> dict[str, Any]:
    if not path:
        return {"status": "not_attached", "role": "optional_visual_cross_check_not_authority"}
    manifest_path = Path(path).expanduser().resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    screenshots = payload.get("screenshots") if isinstance(payload, dict) else None
    screenshot_hashes: dict[str, Any] = {}
    if isinstance(screenshots, dict):
        for label, raw in screenshots.items():
            screenshot = Path(str(raw)).expanduser()
            screenshot_hashes[label] = {
                "path": str(screenshot.resolve()),
                "exists": screenshot.exists(),
                "sha256": file_sha256(screenshot) if screenshot.exists() else None,
            }
    return {
        "status": "attached",
        "role": "optional_visual_cross_check_not_authority",
        "manifest_path": str(manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "payload": payload,
        "screenshot_hashes": screenshot_hashes,
    }


def _run_perception_for_timeframes(
    *,
    timeframe_dfs: dict[str, pd.DataFrame],
    symbol: str,
    decision_available_at: pd.Timestamp,
    config: RuleConfig,
) -> dict[str, dict[str, Any]]:
    perception: dict[str, dict[str, Any]] = {}
    decision_dt = decision_available_at.tz_localize("UTC").to_pydatetime() if decision_available_at.tzinfo is None else decision_available_at.to_pydatetime()
    for tf, df in timeframe_dfs.items():
        perception_df = df.tail(int(config.lookback_bars)).reset_index(drop=True)
        candles = dataframe_to_candles(perception_df, venue="BINANCE", instrument=symbol, timeframe=tf)
        engine = PerceptionEngineV2(expected_instrument=symbol, expected_timeframe=tf, config=config)
        snapshot = engine.analyze(candles, decision_dt)
        payload = _json_model(snapshot)
        payload["perception_window_rows"] = int(len(perception_df))
        perception[tf] = payload
    return perception


def _write_data_files(writer: AnalysisPackageWriter, timeframe_dfs: dict[str, pd.DataFrame]) -> None:
    writer.write_csv("data/canonical_15m.csv", timeframe_dfs["15m"])
    writer.write_csv("data/derived_1h.csv", timeframe_dfs["1h"])
    writer.write_csv("data/derived_4h.csv", timeframe_dfs["4h"])
    writer.write_csv("data/derived_1d.csv", timeframe_dfs["1d"])
    writer.write_json(
        "data/native_reconciliation.json",
        {
            "status": "not_run_in_wp0002_slice",
            "reason": "Native HTF audit exists separately; this package uses source-consistent 15m reconstruction.",
        },
    )


def _render_charts(
    *,
    writer: AnalysisPackageWriter,
    timeframe_dfs: dict[str, pd.DataFrame],
    symbol: str,
    chart_bars: dict[str, int],
    legacy_analysis: Any | None,
    legacy_analyzed_df: pd.DataFrame | None,
    mtf_snapshot: dict[str, Any],
) -> None:
    for tf in TIMEFRAME_ORDER:
        output = writer.path(f"charts/clean/{symbol}_{tf}_clean.png")
        render_raw_chart(timeframe_dfs[tf].tail(chart_bars.get(tf, 180)).copy(), symbol=symbol, timeframe=tf, output_path=str(output))
        writer.register_existing(f"charts/clean/{symbol}_{tf}_clean.png", output)

    if legacy_analysis is not None and legacy_analyzed_df is not None:
        annotated = writer.path(f"charts/perception/{symbol}_15m_legacy_comparison_annotated.png")
        render_smc_annotated(
            legacy_analyzed_df,
            legacy_analysis,
            str(annotated),
            min_conf="medium",
            title=f"{symbol} 15m legacy comparison | {legacy_analysis.trade_plan.verdict} Grade {legacy_analysis.trade_plan.setup_grade}",
        )
        writer.register_existing(f"charts/perception/{symbol}_15m_legacy_comparison_annotated.png", annotated)
    else:
        writer.write_json(
            "charts/perception/legacy_annotation_status.json",
            {
                "status": "disabled",
                "reason": "Legacy comparison was disabled for this run; no legacy annotated chart was rendered.",
            },
        )

    mosaic = writer.path("charts/mtf_mosaic.png")
    mosaic.parent.mkdir(parents=True, exist_ok=True)
    render_mtf_mosaic(
        {tf: timeframe_dfs[tf].tail(chart_bars.get(tf, 180)).copy() for tf in TIMEFRAME_ORDER},
        {"mtf": mtf_snapshot},
        str(mosaic),
        title=f"{symbol} Market Colleague MTF Mosaic",
    )
    writer.register_existing("charts/mtf_mosaic.png", mosaic)


def run_colleague_analysis(request: ColleagueRunRequest, config: RuleConfig) -> dict[str, Any]:
    symbol = request.normalized_symbol
    source_path = request.resolved_source_path
    context = build_run_market_context(source_path, request.decision_time)
    decision_tag = context.decision_candle_open.strftime("%Y%m%d_%H%M")
    run_id = request.run_id or f"{symbol}_{decision_tag}_colleague"
    output_dir = request.resolved_output_dir(decision_tag)
    writer = AnalysisPackageWriter(output_dir)

    visible_start_index = max(0, len(context.history_15m) - max(max(request.chart_bars.values()), int(config.lookback_bars)))
    visible_start = pd.Timestamp(context.history_15m["timestamp"].iloc[visible_start_index])
    holdout_matches = assert_not_in_holdout(
        start=visible_start,
        end=context.decision_candle_open,
        symbol=symbol,
        action="case_generation",
        policy_path=request.holdout_policy or DEFAULT_HOLDOUT_POLICY,
        allow_holdout=request.allow_holdout,
    )

    request_payload = request.model_dump(mode="json")
    request_payload["symbol"] = symbol
    request_payload["source_path"] = str(source_path)
    writer.write_json("request.json", request_payload)

    source_manifest = {
        "venue": "BINANCE",
        "market_type": "USD-M perpetual futures",
        "symbol": symbol,
        "canonical_timeframe": "15m",
        "source_path": str(source_path),
        "source_sha256": file_sha256(source_path),
        "storage_format": request.storage_format,
        "htf_policy": "1H/4H/1D derived from canonical 15m; incomplete HTF candles dropped.",
    }
    if request.market_truth_manifest:
        market_truth_path = Path(request.market_truth_manifest).expanduser().resolve()
        source_manifest["market_truth_manifest"] = {
            "path": str(market_truth_path),
            "exists": market_truth_path.exists(),
            "sha256": file_sha256(market_truth_path) if market_truth_path.exists() else None,
            "payload": json.loads(market_truth_path.read_text(encoding="utf-8")) if market_truth_path.exists() else None,
        }
    writer.write_json("source_manifest.json", source_manifest)
    writer.write_json("data_quality.json", context.source_quality)
    writer.write_json(
        "decision_time.json",
        {
            "requested_decision_time": context.requested_decision_time.isoformat(),
            "decision_candle_open": context.decision_candle_open.isoformat(),
            "decision_available_at": context.decision_available_at.isoformat(),
            "policy": "Decision uses the completed 15m candle whose open time is decision_candle_open; analysis is available at decision_available_at.",
        },
    )
    _write_data_files(writer, context.timeframe_dfs)

    # ------------------------------------------------------------------
    # CURRENT AUTHORITY PATH: PEV2 → MTF graph → decision
    # No dependency on legacy engine.
    # ------------------------------------------------------------------

    # Run PEV2 perception on every timeframe
    perception_by_tf = _run_perception_for_timeframes(
        timeframe_dfs=context.timeframe_dfs,
        symbol=symbol,
        decision_available_at=context.decision_available_at,
        config=config,
    )

    # Build MTF graph from PEV2 snapshots (not legacy engine)
    from smc_desk.colleague.event_ledger import EventLedger

    event_ledger = EventLedger(
        events=[],  # populated later from perception objects
        decision_time=context.decision_available_at,
        ontology_version=config.ontology_version if hasattr(config, "ontology_version") else "2.0.0",
    )
    mtf_graph = build_mtf_graph(
        snapshots=perception_by_tf,
        event_ledger=event_ledger,
        decision_time=context.decision_available_at.isoformat(),
    )
    writer.write_json("perception/mtf_graph.json", mtf_graph.to_dict())

    # ------------------------------------------------------------------
    # LEGACY COMPARISON (isolated, optional, never influences current decision)
    # ------------------------------------------------------------------
    legacy_analysis = None
    legacy_analyzed_df = None
    legacy_payload: dict[str, Any] | None = None
    if request.include_legacy_comparison:
        # Legacy comparison runs through the dedicated adapter only
        from smc_desk.colleague.legacy_comparison import run_legacy_comparison  # noqa: E402

        bias_hint = mtf_graph.state.direction_bias if mtf_graph.state.direction_bias in {"bullish", "bearish"} else None
        legacy_result = run_legacy_comparison(
            history_15m=context.history_15m,
            symbol=symbol,
            timeframe="15m",
            decision_time=context.decision_available_at,
            config=config,
            bias_hint=bias_hint,
        )
        legacy_analysis = legacy_result["legacy_analysis"]
        legacy_analyzed_df = legacy_result["legacy_df"]
        legacy_payload = legacy_result["legacy_payload"]
        writer.write_json("legacy_comparison/engine_analysis.json", legacy_payload)
        writer.write_text("legacy_comparison/trade_plan.md", legacy_result["trade_plan_md"])
    else:
        writer.write_json(
            "legacy_comparison/status.json",
            {
                "status": "disabled",
                "role": "not_run",
                "reason": "Legacy engine comparison disabled; current decision/scenario layers use PEV2 + MTF current graph only.",
            },
        )
    writer.write_json("perception/objects.json", {"source": "PerceptionEngineV2", "timeframes": perception_by_tf})

    # Current MTF graph as the primary state source (replaces legacy mtf_snapshot)
    mtf_graph_dict = mtf_graph.to_dict()
    # Backward-compatible wrapper: downstream functions expect .get("execution_consensus"), etc.
    mtf_snapshot = {
        "decision_time": mtf_graph_dict["state"].get("direction_bias", "neutral"),
        "execution_consensus": mtf_graph_dict["state"].get("direction_bias", "neutral"),
        "alignment": "aligned" if mtf_graph_dict["state"]["decision"] != "ABSTAIN" else "contested",
        "agreement_count": len([n for n in mtf_graph_dict["nodes"] if n["direction"] != "neutral"]),
        "total_count": len(mtf_graph_dict["nodes"]),
        "selected_htf_poi": None,
        "graph_source": "mtf_current_v1_passing_mtf_snapshot_keys_for_downstream",
    }
    # Add timeframe entries for downstream compat
    for node in mtf_graph_dict["nodes"]:
        if node["node_type"] == "timeframe":
            mtf_snapshot[node["timeframe"]] = {
                "bias": node["direction"],
                "structure_state": node["metadata"],
            }

    confirmed_state = build_confirmed_state(perception_by_tf, mtf_snapshot)
    provisional_state = build_provisional_state()
    mtf_state_graph = build_mtf_state_graph(perception_by_tf, mtf_snapshot, None)
    writer.write_json("perception/confirmed_state.json", confirmed_state)
    writer.write_json("perception/provisional_state.json", provisional_state)
    writer.write_json("perception/mtf_state_graph.json", mtf_state_graph)
    tradingview_evidence = _load_tradingview_evidence(request.tradingview_manifest)
    alignment_report = build_alignment_report(
        capture=tradingview_evidence,
        symbol=symbol,
        decision_candle_open=context.decision_candle_open,
        decision_available_at=context.decision_available_at,
        timeframe_dfs=context.timeframe_dfs,
    )
    source_alignment_status = alignment_report.get("status", "NOT_ATTACHED")
    scenario_tree = build_scenario_tree(mtf_snapshot, mtf_state_graph, source_alignment_status=source_alignment_status)
    decision = build_decision(mtf_snapshot, mtf_state_graph, source_alignment_status=source_alignment_status)
    event_records = build_event_ledger_records(
        perception_by_tf=perception_by_tf,
        mtf_graph=mtf_state_graph,
        scenario_tree=scenario_tree,
        alignment_report=alignment_report,
        decision=decision,
    )
    writer.write_text("perception/event_ledger.jsonl", event_ledger_jsonl(event_records))
    writer.write_json("scenarios/scenario_tree.json", scenario_tree)
    writer.write_json(
        "scenarios/evidence_graph.json",
        {
            "status": "built",
            "graph_version": mtf_state_graph.get("graph_version"),
            "mtf_graph": "perception/mtf_state_graph.json",
            "alignment_report": "external/alignment_report.json",
            "scenario_tree": "scenarios/scenario_tree.json",
            "edge_count": len(mtf_state_graph.get("edges", [])),
            "node_count": len(mtf_state_graph.get("nodes", [])),
        },
    )
    writer.write_json("scenarios/decision.json", decision)

    writer.write_json("external/capture_manifest.json", tradingview_evidence)
    writer.write_json("external/alignment_report.json", alignment_report)
    writer.write_json("vision/blind_observation.json", {"status": "not_run_no_api", "authority": "observe_only"})
    writer.write_json("vision/reconciliation.json", {"status": "not_run", "reason": "No independent vision observation supplied."})
    writer.write_json("vision/render_audit.json", {"status": "rendered_charts_registered_in_manifest"})
    similar_cases = retrieve_similar_cases(
        current_run_dir=writer.root,
        analysis_runs_root=writer.root.parent,
        limit=5,
    )
    writer.write_json("prediction/forecast.json", {"status": "disabled_not_certified"})
    writer.write_json("prediction/calibration_context.json", {"status": "not_available"})
    writer.write_json("prediction/similar_cases.json", similar_cases)
    writer.write_json("prediction/abstention_report.json", {"status": "prediction_disabled", "action": decision["action"]})
    outcome_contract = build_outcome_contract(
        symbol=symbol,
        decision_available_at=context.decision_available_at,
        scenario_tree=scenario_tree,
        decision=decision,
        horizon_bars=request.outcome_horizon_bars,
    )
    writer.write_json("outcome/pending.json", outcome_contract)
    writer.write_json("outcome/resolution.json", unresolved_resolution_stub(outcome_contract))

    if request.render_charts:
        _render_charts(
            writer=writer,
            timeframe_dfs=context.timeframe_dfs,
            symbol=symbol,
            chart_bars=request.chart_bars,
            legacy_analysis=legacy_analysis,
            legacy_analyzed_df=legacy_analyzed_df,
            mtf_snapshot=mtf_snapshot,
        )
    else:
        writer.write_json(
            "charts/render_status.json",
            {
                "status": "disabled",
                "reason": "Chart rendering disabled for this batch run; OHLCV, perception, scenario, decision, and outcome files remain authoritative.",
            },
        )

    thesis = build_colleague_thesis(
        symbol=symbol,
        run_id=run_id,
        decision_candle_open=context.decision_candle_open.isoformat(),
        decision_available_at=context.decision_available_at.isoformat(),
        mtf_snapshot=mtf_snapshot,
        perception_by_tf=perception_by_tf,
        scenario_tree=scenario_tree,
        decision=decision,
        legacy_analysis=legacy_payload,
        alignment_report=alignment_report,
        mtf_graph=mtf_graph_dict,
    )
    writer.write_text("reports/colleague_thesis.md", thesis)
    writer.write_text("reports/concise_summary.md", f"# {symbol} Summary\n\nAction: `{decision['action']}`\n")
    writer.write_text(
        "reports/technical_audit.md",
        f"# Technical Audit\n\nPerceptionEngineV2 is primary. Legacy engine: {'comparison only' if request.include_legacy_comparison else 'disabled'}. No execution authority granted.\n",
    )
    review_legacy_note = (
        "Do not inspect `legacy_comparison/` until after your independent read."
        if request.include_legacy_comparison
        else "Legacy comparison is disabled for this run; review the clean charts and PEV2/MTF package."
    )
    writer.write_text(
        "reports/independent_review_prompt.md",
        f"# Independent Review Prompt - {symbol}\n\nReview `charts/clean/` first. {review_legacy_note}\n",
    )

    writer.write_json(
        "authority_manifest.json",
        {
            "market_truth": "active",
            "perception_source": "PerceptionEngineV2",
            "legacy_engine": "comparison_only" if request.include_legacy_comparison else "disabled",
            "vision": "observe_only",
            "prediction": "disabled_not_certified",
            "paper_execution": "disabled",
            "live_execution": "disabled",
            "capital_risk": 0,
        },
    )
    run_manifest = {
        "manifest_version": "1.0",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_kind": "market_colleague_analysis_run",
        "symbol": symbol,
        "decision_candle_open": context.decision_candle_open.isoformat(),
        "decision_available_at": context.decision_available_at.isoformat(),
        "primary_perception_source": "PerceptionEngineV2",
        "legacy_engine_role": "comparison_only" if request.include_legacy_comparison else "disabled",
        "storage_format": request.storage_format,
        "no_future_leakage": {
            "history_ends_at_decision_candle_open": bool(pd.Timestamp(context.history_15m["timestamp"].iloc[-1]) == context.decision_candle_open),
            "perception_decision_time": context.decision_available_at.isoformat(),
            "htf_charts_drop_incomplete_candles": True,
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
        "files": writer.build_manifest_file_index(),
    }
    writer.write_json("run_manifest.json", run_manifest)
    return run_manifest
