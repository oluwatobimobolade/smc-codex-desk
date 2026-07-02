"""WP-0020 end-to-end market colleague gauntlet.

The gauntlet proves the observe-only colleague workflow can run from verified
OHLCV through charts, annotations, cognitive refusal, visual-audit boundary,
and evidence-linked thesis generation. It does not certify strategy edge.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from PIL import Image

from smc_desk.case_library import file_sha256
from smc_desk.colleague.orchestrator_v2 import run_colleague_brain_v2
from smc_desk.colleague.smc_narrative_authority import (
    assert_narrative_authority_contract,
    build_smc_narrative_authority,
)
from smc_desk.colleague.smc_thesis_v5 import (
    assert_smc_thesis_v5_quality,
    build_smc_thesis_v5,
    render_smc_thesis_v5_markdown,
)
from smc_desk.colleague.smc_thesis_v2 import (
    assert_smc_thesis_v2_quality,
    build_smc_thesis_v2,
    render_smc_thesis_v2_markdown,
)
from smc_desk.colleague.run_context import (
    build_run_market_context,
    dataframe_to_candles,
)
from smc_desk.colleague.tradingview_live_manifest import build_live_visual_manifest
from smc_desk.colleague.legacy_comparison import run_legacy_annotation_analysis
from smc_desk.colleague.outcome_logging import unresolved_resolution_stub
from smc_desk.data.live_ohlcv import acquire_verified_closed_ohlcv
from smc_desk.data.live_route_health import run_route_health_preflight
from smc_desk.render import render_raw_chart, render_smc_annotated
from smc_desk.render_v2 import render_v2_story_chart
from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.rendering.mtf_mosaic import render_mtf_mosaic
from smc_desk.rendering.trade_plan_chart_renderer import render_trade_plan_chart
from smc_desk.rendering.watch_chart_renderer import render_watch_chart
from smc_desk.rules import RuleConfig, load_rule_config
from smc_desk.vision.visual_proof import evaluate_tradingview_screenshot, summarize_visual_proof


TIMEFRAMES = ("15m", "1h", "4h", "1d")
GAUNTLET_STRUCTURE = (
    "00_route_health",
    "01_verified_ohlcv",
    "02_mtf_package",
    "03_clean_charts",
    "04_debug_legacy_annotations",
    "04a_story_charts",
    "04b_official_charts",
    "05_perception",
    "06_cognitive",
    "07_tradingview_visual",
    "08_visual_reconciliation",
    "09_smc_thesis",
    "10_memory",
    "11_final_report",
    "12_research_events",
)


@dataclass(frozen=True)
class GauntletResult:
    output_dir: Path
    status: str
    failed_layer: str | None
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "status": self.status,
            "failed_layer": self.failed_layer,
            "summary": self.summary,
        }


def run_wp0020_gauntlet(
    *,
    symbol: str,
    output_dir: str | Path,
    source: str | Path | None = None,
    decision_time: str | None = None,
    mode: str = "csv",
    visual_mode: str = "skip",
    config: RuleConfig | None = None,
    live_limit: int = 500,
    min_live_bars: int = 100,
) -> GauntletResult:
    """Run the WP-0020 gauntlet.

    mode:
        ``csv`` uses a local canonical 15m source.
        ``live`` attempts Binance USD-M live acquisition and fails cleanly if
        the route is unavailable. If ``source`` is supplied with live mode it is
        used as a CSV fallback after a clean live failure.
    visual_mode:
        ``skip`` writes a visual-audit skipped manifest.
        ``capture`` attempts Kimi/TradingView screenshots and fails cleanly.
    """
    symbol = _normalize_symbol(symbol)
    config = config or load_rule_config()
    root = Path(output_dir).expanduser().resolve()
    _prepare_structure(root)
    stage_results: dict[str, dict[str, Any]] = {}

    # 00 route health
    route_report = _run_route_health(symbol, root / "00_route_health", enabled=(mode == "live"))
    stage_results["00_route_health"] = route_report

    # 01 verified OHLCV
    source_path, verified_manifest = _resolve_ohlcv_source(
        symbol=symbol,
        output_dir=root / "01_verified_ohlcv",
        source=Path(source).expanduser().resolve() if source else None,
        mode=mode,
        live_limit=live_limit,
        min_live_bars=min_live_bars,
    )
    stage_results["01_verified_ohlcv"] = verified_manifest
    if verified_manifest.get("status") not in {"VERIFIED", "VERIFIED_CSV_SOURCE"}:
        final = _write_final_report(root, stage_results, status="PARTIAL_PASS", failed_layer="01_verified_ohlcv")
        return GauntletResult(root, "PARTIAL_PASS", "01_verified_ohlcv", final)

    # 02 MTF package and truth validation
    context = build_run_market_context(source_path, decision_time)
    decision_dt = _decision_datetime(context.decision_available_at)
    analysis_timeframe_dfs = _analysis_timeframe_dfs(context.timeframe_dfs)
    candles_by_tf = {
        tf: dataframe_to_candles(
            df.reset_index(drop=True),
            venue="BINANCE",
            instrument=symbol,
            timeframe=tf,
            reference_time=decision_dt,
        )
        for tf, df in analysis_timeframe_dfs.items()
    }
    truth = run_colleague_brain_v2(
        candles_by_timeframe=candles_by_tf,
        decision_time=decision_dt,
        symbol=symbol,
        memory_path=None,
        config=config,
    ).truth_report
    mtf_manifest = _write_mtf_package(root / "02_mtf_package", symbol, context, analysis_timeframe_dfs, source_path, verified_manifest, truth.to_dict())
    stage_results["02_mtf_package"] = mtf_manifest
    if not truth.ok:
        stage_results["06_cognitive"] = {"status": "REFUSE_PERCEPTION", "truth_report": truth.to_dict()}
        final = _write_final_report(root, stage_results, status="FAIL", failed_layer="02_mtf_package")
        return GauntletResult(root, "FAIL", "02_mtf_package", final)

    # 03 clean charts
    clean_manifest = render_clean_mtf_charts(
        timeframe_dfs=analysis_timeframe_dfs,
        symbol=symbol,
        output_dir=root / "03_clean_charts",
        source_manifest=mtf_manifest,
    )
    stage_results["03_clean_charts"] = clean_manifest

    # 04 debug legacy annotations
    annotation_manifest, analysis_by_tf = render_smc_annotations(
        timeframe_dfs=analysis_timeframe_dfs,
        symbol=symbol,
        output_dir=root / "04_debug_legacy_annotations",
        config=config,
    )
    annotation_manifest["chart_authority"] = "debug_only_legacy_not_decision_authority"
    annotation_manifest["decision_authority_chart_stage"] = "04a_story_charts"
    stage_results["04_debug_legacy_annotations"] = annotation_manifest

    # 06 cognitive, with perception copied to 05
    memory_path = root / "10_memory" / "decision_memory.jsonl"
    cognitive_result = run_colleague_brain_v2(
        candles_by_timeframe=candles_by_tf,
        decision_time=decision_dt,
        symbol=symbol,
        memory_path=str(memory_path),
        config=config,
    ).to_dict()
    if not cognitive_result.get("smc_narrative_authority"):
        cognitive_result["smc_narrative_authority"] = build_smc_narrative_authority(
            symbol=symbol,
            cognitive_result=cognitive_result,
        )
    assert_narrative_authority_contract(cognitive_result["smc_narrative_authority"])
    (root / "05_perception").mkdir(parents=True, exist_ok=True)
    _write_json(root / "05_perception" / "perception_events.json", cognitive_result["perception_by_tf"])
    _write_json(root / "05_perception" / "perception_manifest.json", _perception_manifest(cognitive_result))
    _write_json(root / "06_cognitive" / "truth_validation.json", cognitive_result["truth_report"])
    _write_json(root / "06_cognitive" / "regime_report.json", cognitive_result["regime"])
    _write_json(root / "06_cognitive" / "contradiction_report.json", cognitive_result["contradiction"])
    _write_json(root / "06_cognitive" / "uncertainty_report.json", cognitive_result["uncertainty"])
    _write_json(root / "06_cognitive" / "refusal_report.json", cognitive_result["refusal"])
    _write_json(root / "06_cognitive" / "smc_narrative_authority.json", cognitive_result["smc_narrative_authority"])
    _write_json(root / "06_cognitive" / "final_colleague_output.json", cognitive_result)
    _write_json(root / "10_memory" / "memory_manifest.json", _memory_manifest(memory_path, package_root=root))
    stage_results["05_perception"] = _perception_manifest(cognitive_result)
    stage_results["06_cognitive"] = {
        "status": "PASS",
        "final_action": cognitive_result["final_action"],
        "final_state": cognitive_result.get("final_state"),
        "watch_state": cognitive_result.get("watch_state"),
        "liquidity_sequence": cognitive_result.get("liquidity_sequence"),
        "inducement_continuation": cognitive_result.get("inducement_continuation"),
        "execution_readiness": cognitive_result.get("execution_readiness"),
        "smc_narrative_authority": cognitive_result.get("smc_narrative_authority"),
        "regime": cognitive_result.get("regime"),
        "contradiction": cognitive_result.get("contradiction"),
        "uncertainty": cognitive_result.get("uncertainty"),
        "refusal": cognitive_result.get("refusal"),
    }
    stage_results["10_memory"] = _memory_manifest(memory_path, package_root=root)

    # 04a story charts (V6-aligned, rendered after cognitive output is available)
    story_manifest = render_v2_story_charts(
        timeframe_dfs=analysis_timeframe_dfs,
        symbol=symbol,
        cognitive_result=cognitive_result,
        output_dir=root / "04a_story_charts",
    )
    stage_results["04a_story_charts"] = story_manifest

    # 04b official charts: one narrative-authority-driven chart, not a detector dump.
    official_manifest = render_official_narrative_charts(
        timeframe_dfs=analysis_timeframe_dfs,
        symbol=symbol,
        cognitive_result=cognitive_result,
        output_dir=root / "04b_official_charts",
    )
    stage_results["04b_official_charts"] = official_manifest

    # 12 research event/outcome scaffolding (observe-only)
    research_manifest = write_research_event_package(
        output_dir=root / "12_research_events",
        symbol=symbol,
        cognitive_result=cognitive_result,
        decision_available_at=context.decision_available_at,
    )
    stage_results["12_research_events"] = research_manifest

    # 07 visual audit and 08 reconciliation
    visual_manifest = _run_visual_capture(symbol, root / "07_tradingview_visual", visual_mode=visual_mode)
    stage_results["07_tradingview_visual"] = visual_manifest
    visual_reconciliation = reconcile_engine_vs_tradingview(
        engine_chart_manifest=clean_manifest,
        tradingview_manifest=visual_manifest,
        output_dir=root / "08_visual_reconciliation",
    )
    stage_results["08_visual_reconciliation"] = visual_reconciliation

    # 09 thesis
    thesis = generate_evidence_linked_smc_thesis(
        symbol=symbol,
        cognitive_result=cognitive_result,
        annotation_manifest=annotation_manifest,
        visual_reconciliation=visual_reconciliation,
        output_dir=root / "09_smc_thesis",
    )
    stage_results["09_smc_thesis"] = thesis

    status, failed_layer = _status_from_stage_results(stage_results)
    final = _write_final_report(root, stage_results, status=status, failed_layer=failed_layer)
    return GauntletResult(root, status, failed_layer, final)


def render_clean_mtf_charts(
    *,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    symbol: str,
    output_dir: str | Path,
    source_manifest: Mapping[str, Any],
    chart_bars: int = 180,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    charts: dict[str, dict[str, Any]] = {}
    for tf in TIMEFRAMES:
        path = output / f"{symbol}_{tf}_clean.png"
        df = timeframe_dfs[tf].tail(chart_bars).copy()
        render_raw_chart(df, symbol=symbol, timeframe=tf, output_path=str(path))
        charts[tf] = _image_manifest(path, candle_count=len(df), timeframe=tf, package_root=output.parent)
    mosaic = output / "mtf_mosaic.png"
    render_mtf_mosaic({tf: timeframe_dfs[tf].tail(chart_bars).copy() for tf in TIMEFRAMES}, {}, str(mosaic), title=f"{symbol} WP-0020 MTF")
    manifest = {
        "status": "PASS",
        "chart_type": "clean_engine_charts",
        "symbol": symbol,
        "source_manifest_sha256": _payload_hash(source_manifest),
        "tradingview_used_as_market_truth": False,
        "charts": charts,
        "mosaic": _image_manifest(
            mosaic,
            candle_count=sum(min(chart_bars, len(timeframe_dfs[tf])) for tf in TIMEFRAMES),
            timeframe="mtf",
            package_root=output.parent,
        ),
    }
    _write_json(output / "chart_render_manifest.json", manifest)
    return manifest


def render_smc_annotations(
    *,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    symbol: str,
    output_dir: str | Path,
    config: RuleConfig,
    chart_bars: int = 240,
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    charts: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    analyses: dict[str, Any] = {}
    for tf in TIMEFRAMES:
        df = timeframe_dfs[tf].tail(chart_bars).reset_index(drop=True).copy()
        analysis, analyzed_df = run_legacy_annotation_analysis(
            df=df,
            symbol=symbol,
            timeframe=tf,
            config=config,
            notes="WP-0020 annotation-only analysis; not execution authority.",
        )
        analyses[tf] = analysis.model_dump(mode="json")
        path = output / f"{symbol}_{tf}_annotated.png"
        render_smc_annotated(
            analyzed_df,
            analysis,
            str(path),
            min_conf="medium",
            title=f"DEBUG ONLY - {symbol} {tf} detector annotations, not official trade thesis",
        )
        charts[tf] = _image_manifest(path, candle_count=len(analyzed_df), timeframe=tf, package_root=output.parent)
        events.extend(_annotation_events(tf, analysis.model_dump(mode="json"), analyzed_df))

    mosaic = output / "mtf_annotated_mosaic.png"
    render_mtf_mosaic({tf: timeframe_dfs[tf].tail(chart_bars).copy() for tf in TIMEFRAMES}, {}, str(mosaic), title=f"{symbol} WP-0020 annotated MTF")
    manifest = {
        "status": "PASS",
        "symbol": symbol,
        "chart_authority": "debug_only_legacy_not_decision_authority",
        "debug_only_banner": "DEBUG ONLY - not official trade thesis",
        "annotation_count": len(events),
        "charts": charts,
        "mosaic": _image_manifest(
            mosaic,
            candle_count=sum(min(chart_bars, len(timeframe_dfs[tf])) for tf in TIMEFRAMES),
            timeframe="mtf",
            package_root=output.parent,
        ),
        "annotations": events,
        "provenance_rule": "Every annotation carries event_id, timeframe, candle_index, timestamp, and price or price zone.",
    }
    _write_json(output / "smc_annotation_manifest.json", manifest)
    _write_json(output / "perception_events.json", {"events": events, "analysis_by_timeframe": analyses})
    return manifest, analyses


def render_v2_story_charts(
    *,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    symbol: str,
    cognitive_result: Mapping[str, Any],
    output_dir: str | Path,
    chart_bars: int = 240,
) -> dict[str, Any]:
    """Render V6-cognitive-aligned story charts after the colleague brain runs.

    Story charts derive title, bias, and active POI from ``cognitive_result`` so
    they always agree with the V6 watch state.  Debug/legacy annotations remain
    in ``04_debug_legacy_annotations`` for comparison.  Rendering is best-effort: an
    invalid perception payload skips that timeframe without failing the gauntlet.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    charts: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for tf in TIMEFRAMES:
        df = timeframe_dfs[tf].tail(chart_bars).reset_index(drop=True).copy()
        payload = (cognitive_result.get("perception_by_tf") or {}).get(tf, {})
        path = output / f"{symbol}_{tf}_story.png"
        try:
            snapshot = PerceptionSnapshot.model_validate(payload)
            render_v2_story_chart(df, snapshot, dict(cognitive_result), tf, str(path), mode="story")
            charts[tf] = _image_manifest(path, candle_count=len(df), timeframe=tf, package_root=output.parent)
        except Exception as exc:  # pragma: no cover - defensive skip for malformed snapshots
            errors.append({"timeframe": tf, "error": str(exc)})
    status = "PASS" if len(charts) == len(TIMEFRAMES) else ("PARTIAL_PASS" if charts else "FAIL")
    manifest = {
        "status": status,
        "symbol": symbol,
        "chart_type": "v2_story_charts",
        "mode": "story",
        "story_mode_contract": {
            "raw_internal_events_hidden": True,
            "raw_detector_objects_hidden": True,
            "far_invalid_pois_note_only": True,
            "daily_shallow_blocks_ltf_poi_authority": True,
            "debug_stage_for_raw_events": "04_debug_legacy_annotations",
        },
        "charts": charts,
        "errors": errors,
    }
    _write_json(output / "v2_story_chart_manifest.json", manifest)
    return manifest


def render_official_narrative_charts(
    *,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    symbol: str,
    cognitive_result: Mapping[str, Any],
    output_dir: str | Path,
    chart_bars: int = 240,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    authority = cognitive_result.get("smc_narrative_authority") or build_smc_narrative_authority(
        symbol=symbol,
        cognitive_result=cognitive_result,
    )
    assert_narrative_authority_contract(authority)
    chart_template = str(authority.get("chart_template") or "watch_chart")
    path = output / f"{symbol}_official_{chart_template}.png"
    df = timeframe_dfs["15m"].tail(chart_bars).reset_index(drop=True).copy()
    if chart_template == "trade_plan_chart":
        render_trade_plan_chart(df, authority, path, timeframe="15m")
    else:
        render_watch_chart(df, authority, path, timeframe="15m")
    chart_manifest = _image_manifest(path, candle_count=len(df), timeframe="15m", package_root=output.parent)
    manifest = {
        "status": "PASS",
        "symbol": symbol,
        "chart_type": "official_narrative_authority_chart",
        "chart_template": chart_template,
        "official_state": authority.get("official_state"),
        "official_model": authority.get("official_model"),
        "official_trade_plan_state": authority.get("official_trade_plan_state"),
        "show_trade_box": bool(authority.get("show_trade_box")),
        "authority_source": "06_cognitive/smc_narrative_authority.json",
        "charts": {"official": chart_manifest},
        "debug_stage_for_raw_events": "04_debug_legacy_annotations",
    }
    _write_json(output / "official_chart_manifest.json", manifest)
    return manifest


def reconcile_engine_vs_tradingview(
    *,
    engine_chart_manifest: Mapping[str, Any],
    tradingview_manifest: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tv_status = tradingview_manifest.get("status") or tradingview_manifest.get("verification_status")
    screenshots = tradingview_manifest.get("screenshots", {}) if isinstance(tradingview_manifest, Mapping) else {}
    required_labels = {"15m", "1h", "4h", "1d"}
    label_aliases = {"15": "15m", "15m": "15m", "1H": "1h", "1h": "1h", "4H": "4h", "4h": "4h", "1D": "1d", "1d": "1d"}
    symbol = str(
        tradingview_manifest.get("symbol")
        or tradingview_manifest.get("ticker")
        or engine_chart_manifest.get("symbol")
        or ""
    )
    screenshot_checks = {}
    for label, path in screenshots.items():
        timeframe = label_aliases.get(str(label), str(label))
        screenshot_checks[str(label)] = evaluate_tradingview_screenshot(
            screenshot_path=str(path),
            symbol=symbol,
            timeframe=timeframe,
            package_root=output.parent,
            metadata={"symbol": symbol, "timeframe": timeframe},
        )
    visual_proof = summarize_visual_proof(screenshot_checks, required_timeframes=required_labels)
    present_timeframes = {check["timeframe"] for check in screenshot_checks.values() if check.get("image_exists")}
    missing_timeframes = sorted(required_labels - present_timeframes)
    missing_files = sorted(label for label, check in screenshot_checks.items() if not check.get("image_exists"))
    alignment_status = None
    if isinstance(tradingview_manifest.get("alignment_report"), Mapping):
        alignment_status = tradingview_manifest["alignment_report"].get("status")
    if tv_status in {"SKIPPED", "FAILED", "visual_capture_failed"} or not screenshots:
        status = "REVIEW_REQUIRED"
        reason = f"TradingView visual audit unavailable: {tv_status or 'no_screenshots'}"
    elif missing_timeframes or missing_files or visual_proof["status"] == "VISUAL_CONTEXT_UNVERIFIED":
        status = "VISUAL_CONTEXT_UNVERIFIED"
        reason = visual_proof["reason"]
    elif alignment_status == "FAIL":
        status = "VISUAL_CONTEXT_MISMATCH"
        reason = "TradingView evidence exists, but alignment checks failed."
    else:
        status = "VISUAL_AUDIT_AVAILABLE"
        reason = "TradingView screenshots exist and chart context is visually verified. Visual comparison remains audit evidence only."
    report = {
        "status": status,
        "reason": reason,
        "market_truth_changed": False,
        "tradingview_used_as_market_truth": False,
        "engine_chart_status": engine_chart_manifest.get("status"),
        "screenshot_checks": screenshot_checks,
        "missing_timeframes": missing_timeframes,
        "missing_files": missing_files,
        "visual_proof": visual_proof,
        "alignment_status": alignment_status,
        "review_required": status in {"REVIEW_REQUIRED", "VISUAL_CONTEXT_UNVERIFIED", "VISUAL_CONTEXT_MISMATCH"},
        "context_mismatch": status == "VISUAL_CONTEXT_MISMATCH",
        "notes": [
            "Visual mismatch must not automatically change OHLCV truth.",
            "A mismatch can only request human review or re-run market-truth acquisition.",
        ],
    }
    _write_json(output / "visual_reconciliation_report.json", report)
    summary = (
        "# Visual Reconciliation\n\n"
        f"- Status: `{status}`\n"
        f"- Reason: {reason}\n"
        "- Market truth changed: `false`\n"
    )
    (output / "visual_reconciliation_summary.md").write_text(summary, encoding="utf-8")
    return report


def write_research_event_package(
    *,
    output_dir: str | Path,
    symbol: str,
    cognitive_result: Mapping[str, Any],
    decision_available_at: pd.Timestamp,
    horizon_bars: int = 96,
) -> dict[str, Any]:
    """Write observe-only event logs and a pending outcome contract.

    This is research infrastructure only: it records what the colleague saw and
    what should be checked later, without creating execution authority.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tiers = _tiered_research_events_from_cognitive(cognitive_result)
    events = [event for tier_events in tiers.values() for event in tier_events]
    ledger_path = output / "event_ledger.jsonl"
    ledger_path.write_text("\n".join(json.dumps(event, sort_keys=True, default=str) for event in events) + "\n", encoding="utf-8")
    tier_paths: dict[str, dict[str, Any]] = {}
    for tier_name, tier_events in tiers.items():
        path = output / f"{tier_name}.jsonl"
        path.write_text("\n".join(json.dumps(event, sort_keys=True, default=str) for event in tier_events) + ("\n" if tier_events else ""), encoding="utf-8")
        tier_paths[tier_name] = {
            "path": _package_relative_path(path, output.parent),
            "sha256": file_sha256(path),
            "event_count": len(tier_events),
        }

    contract = _build_gauntlet_outcome_contract(
        symbol=symbol,
        cognitive_result=cognitive_result,
        decision_available_at=decision_available_at,
        horizon_bars=horizon_bars,
    )
    pending_path = output / "pending_outcome_contract.json"
    _write_json(pending_path, contract)
    _write_json(output / "unresolved_resolution_stub.json", unresolved_resolution_stub(contract))

    manifest = {
        "status": "PASS",
        "authority": "research_observation_only",
        "market_edge_claimed": False,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "capital_risk": 0,
        "event_count": len(events),
        "event_hierarchy": {
            "raw_detector_events": len(tiers["raw_detector_events"]),
            "candidate_research_events": len(tiers["candidate_research_events"]),
            "decision_grade_events": len(tiers["decision_grade_events"]),
            "outcome_contract_events": len(tiers["outcome_contract_events"]),
        },
        "wisdom_layer_priority": ["decision_grade_events", "outcome_contract_events"],
        "tier_ledgers": tier_paths,
        "event_ledger": {"path": _package_relative_path(ledger_path, output.parent), "sha256": file_sha256(ledger_path)},
        "pending_outcome_contract": {"path": _package_relative_path(pending_path, output.parent), "sha256": file_sha256(pending_path)},
        "outcome_contract_status": contract["status"],
        "tracked_scenarios": len(contract.get("tracked_scenarios", [])),
    }
    _write_json(output / "research_event_manifest.json", manifest)
    return manifest


def _research_events_from_cognitive(cognitive_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    tiers = _tiered_research_events_from_cognitive(cognitive_result)
    return [event for tier_events in tiers.values() for event in tier_events]


def _tiered_research_events_from_cognitive(cognitive_result: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tiers = {
        "raw_detector_events": [],
        "candidate_research_events": [],
        "decision_grade_events": [],
        "outcome_contract_events": [],
    }
    events: list[dict[str, Any]] = []
    for tf, payload in (cognitive_result.get("perception_by_tf") or {}).items():
        for kind in ("structure_breaks", "sweeps", "order_blocks", "fvgs", "inducements"):
            for obj in payload.get(kind, []) or []:
                event = {
                    "event_type": f"perception.{kind}",
                    "event_tier": "raw_detector_events",
                    "timeframe": tf,
                    "object_id": obj.get("object_id"),
                    "direction": obj.get("direction"),
                    "status": obj.get("confirmation_status") or obj.get("mitigation_status") or obj.get("terminal_reason"),
                    "event_time": obj.get("confirmed_at") or obj.get("candidate_at") or obj.get("pivot_time"),
                    "authority": "engine_observation",
                }
                tiers["raw_detector_events"].append(event)
    for tf, pois in (cognitive_result.get("poi_lifecycle") or {}).items():
        for poi in pois or []:
            event = {
                "event_type": "candidate.poi",
                "event_tier": "candidate_research_events",
                "timeframe": tf,
                "object_id": poi.get("poi_id"),
                "direction": poi.get("direction"),
                "status": poi.get("validity_status"),
                "scope": poi.get("scope"),
                "price_low": poi.get("price_low"),
                "price_high": poi.get("price_high"),
                "authority": "candidate_research_context",
            }
            tiers["candidate_research_events"].append(event)
    watch = cognitive_result.get("watch_state") or {}
    active_poi = watch.get("active_poi") if isinstance(watch, Mapping) else None
    if active_poi:
        tiers["decision_grade_events"].append({
            "event_type": "watch.active_poi",
            "event_tier": "decision_grade_events",
            "timeframe": active_poi.get("timeframe"),
            "object_id": active_poi.get("poi_id"),
            "direction": active_poi.get("direction"),
            "status": active_poi.get("freshness"),
            "validity_status": active_poi.get("validity_status"),
            "scope": active_poi.get("scope"),
            "price_relation": active_poi.get("price_relation"),
            "selection_score": active_poi.get("selection_score"),
            "authority": "v6_watch_state",
        })
    for tf, sequence in (cognitive_result.get("liquidity_sequence") or {}).items():
        tiers["decision_grade_events"].append({
            "event_type": "liquidity.sequence",
            "event_tier": "decision_grade_events",
            "timeframe": tf,
            "buy_side_liquidity_taken": sequence.get("buy_side_liquidity_taken"),
            "sell_side_liquidity_taken": sequence.get("sell_side_liquidity_taken"),
            "current_liquidity_draw": sequence.get("current_liquidity_draw"),
            "inducement_risk": sequence.get("inducement_risk"),
            "authority": "smc_sequence_summary",
        })
    move_quality = cognitive_result.get("inducement_continuation") or {}
    if move_quality:
        tiers["decision_grade_events"].append({
            "event_type": "decision.inducement_continuation",
            "event_tier": "decision_grade_events",
            "state": move_quality.get("state"),
            "direction": move_quality.get("direction"),
            "confidence": move_quality.get("confidence"),
            "authority": "smc_decision_quality",
        })
    narrative = cognitive_result.get("smc_narrative_authority") or {}
    if narrative:
        tiers["decision_grade_events"].append({
            "event_type": "decision.smc_narrative_authority",
            "event_tier": "decision_grade_events",
            "official_model": narrative.get("official_model"),
            "official_state": narrative.get("official_state"),
            "official_trade_plan_state": narrative.get("official_trade_plan_state"),
            "show_trade_box": narrative.get("show_trade_box"),
            "authority": "final_smc_narrative_authority",
        })
    readiness = cognitive_result.get("execution_readiness") or {}
    if readiness:
        tiers["decision_grade_events"].append({
            "event_type": "decision.execution_readiness",
            "event_tier": "decision_grade_events",
            "state": readiness.get("state"),
            "confidence": readiness.get("confidence"),
            "authority": "observe_only_stage_classifier",
        })
    tiers["decision_grade_events"].append({
        "event_type": "watch.final_state",
        "event_tier": "decision_grade_events",
        "state": watch.get("final_state") or cognitive_result.get("final_state"),
        "direction": watch.get("direction"),
        "signal_allowed": watch.get("signal_allowed", False),
        "authority": "observe_only",
    })
    refusal = cognitive_result.get("refusal") or {}
    tiers["decision_grade_events"].append({
        "event_type": "decision.refusal",
        "event_tier": "decision_grade_events",
        "final_action": cognitive_result.get("final_action") or refusal.get("final_action"),
        "blocking_codes": refusal.get("blocking_codes", []),
        "authority": "observe_only_no_execution",
    })
    tiers["outcome_contract_events"].append({
        "event_type": "outcome.contract_pending",
        "event_tier": "outcome_contract_events",
        "state": (narrative.get("official_state") if narrative else None) or watch.get("final_state") or cognitive_result.get("final_state"),
        "move_quality_state": move_quality.get("state"),
        "execution_readiness_state": readiness.get("state"),
        "direction": narrative.get("official_bias") or watch.get("direction"),
        "official_model": narrative.get("official_model"),
        "official_trade_plan_state": narrative.get("official_trade_plan_state"),
        "show_trade_box": narrative.get("show_trade_box", False),
        "authority": "pending_observation_no_edge_claim",
    })
    return tiers


def _build_gauntlet_outcome_contract(
    *,
    symbol: str,
    cognitive_result: Mapping[str, Any],
    decision_available_at: pd.Timestamp,
    horizon_bars: int,
) -> dict[str, Any]:
    due_at = pd.Timestamp(decision_available_at) + pd.Timedelta(minutes=15 * horizon_bars)
    watch = cognitive_result.get("watch_state") or {}
    active_poi = watch.get("active_poi") if isinstance(watch, Mapping) else None
    narrative = cognitive_result.get("smc_narrative_authority") or {}
    direction = str(watch.get("direction") or (active_poi.get("direction") if isinstance(active_poi, Mapping) else "neutral"))
    scenario = {
        "scenario_id": f"{symbol}:official_state:{narrative.get('official_state') or watch.get('final_state') or cognitive_result.get('final_state') or 'unknown'}",
        "direction": narrative.get("official_bias") or direction,
        "setup_stage": narrative.get("official_state") or watch.get("final_state") or cognitive_result.get("final_state"),
        "execution_readiness": (cognitive_result.get("execution_readiness") or {}).get("state"),
        "inducement_continuation": (cognitive_result.get("inducement_continuation") or {}).get("state"),
        "official_model": narrative.get("official_model"),
        "official_trade_plan_state": narrative.get("official_trade_plan_state"),
        "show_trade_box": narrative.get("show_trade_box", False),
        "continuation_confirmed_if": narrative.get("continuation_confirmed_if") or (cognitive_result.get("inducement_continuation") or {}).get("continuation_confirmed_if", []),
        "inducement_confirmed_if": narrative.get("inducement_confirmed_if") or (cognitive_result.get("inducement_continuation") or {}).get("inducement_confirmed_if", []),
        "do_not_chase_reason": (cognitive_result.get("inducement_continuation") or {}).get("do_not_chase_reason"),
        "terminal_conditions": _terminal_conditions_from_narrative(cognitive_result, narrative, active_poi),
    }
    return {
        "outcome_contract_version": "0.1",
        "status": "pending_observation",
        "symbol": symbol,
        "decision_available_at": pd.Timestamp(decision_available_at).isoformat(),
        "resolution_due_at": due_at.isoformat(),
        "horizon_bars_15m": horizon_bars,
        "decision_action": _research_decision_action(cognitive_result),
        "capital_risk": 0,
        "tracked_scenarios": [scenario],
        "resolution_policy": "No performance claim until future OHLCV resolves this observe-only contract.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _research_decision_action(cognitive_result: Mapping[str, Any]) -> str:
    watch = cognitive_result.get("watch_state") or {}
    state = str(watch.get("final_state") or cognitive_result.get("final_state") or "")
    if state.startswith("WATCH") or state.startswith("POI_") or state.startswith("AWAIT"):
        return "WATCH"
    if str(cognitive_result.get("final_action") or "").upper() == "SOURCE_MISMATCH":
        return "SOURCE_MISMATCH"
    return "NO_SETUP"


def _terminal_conditions_from_watch(
    cognitive_result: Mapping[str, Any],
    active_poi: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(active_poi, Mapping):
        return {"target_touch": [], "invalidation": [], "expiry": "96x15m_bars"}
    direction = str(active_poi.get("direction") or "neutral")
    hierarchy = cognitive_result.get("structure_hierarchy") or {}
    tf_h = hierarchy.get(str(active_poi.get("timeframe"))) or hierarchy.get("1h") or hierarchy.get("4h") or {}
    if direction == "bearish":
        target = tf_h.get("external_range_low") or tf_h.get("protected_low")
        invalidation = active_poi.get("price_high")
    elif direction == "bullish":
        target = tf_h.get("external_range_high") or tf_h.get("protected_high")
        invalidation = active_poi.get("price_low")
    else:
        target = invalidation = None
    return {
        "target_touch": [] if target in {None, ""} else [{"price": target, "source": "active_external_range"}],
        "invalidation": [] if invalidation in {None, ""} else [{"price": invalidation, "source": "active_poi_boundary"}],
        "expiry": "96x15m_bars",
    }


def _terminal_conditions_from_narrative(
    cognitive_result: Mapping[str, Any],
    narrative: Mapping[str, Any],
    active_poi: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not narrative:
        return _terminal_conditions_from_watch(cognitive_result, active_poi)
    liquidity_draw = []
    for item in narrative.get("official_liquidity_draw", []) or []:
        if isinstance(item, Mapping) and item.get("price") not in {None, ""}:
            liquidity_draw.append({
                "price": item.get("price"),
                "source": item.get("source") or "official_liquidity_draw",
                "timeframe": item.get("timeframe"),
                "label": item.get("label"),
                "not_take_profit": True,
            })
    invalidation = []
    official_invalidation = narrative.get("official_invalidation") if isinstance(narrative.get("official_invalidation"), Mapping) else {}
    if official_invalidation.get("price") not in {None, ""}:
        invalidation.append({
            "price": official_invalidation.get("price"),
            "source": official_invalidation.get("source") or "official_watch_invalidation",
            "condition": official_invalidation.get("condition"),
            "not_stop_loss": True,
        })
    return {
        "target_touch": liquidity_draw,
        "invalidation": invalidation,
        "expiry": "96x15m_bars",
        "trade_box_allowed": bool(narrative.get("show_trade_box")),
    }


def generate_evidence_linked_smc_thesis(
    *,
    symbol: str,
    cognitive_result: Mapping[str, Any],
    annotation_manifest: Mapping[str, Any],
    visual_reconciliation: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    claims = _thesis_claims(symbol, cognitive_result, annotation_manifest, visual_reconciliation)
    payload = {
        "status": "PASS",
        "symbol": symbol,
        "final_decision": cognitive_result.get("final_action"),
        "forbidden_language_present": _forbidden_language_present(claims),
        "claims": claims,
        "claim_count": len(claims),
    }
    thesis_v2 = build_smc_thesis_v2(
        symbol=symbol,
        cognitive_result=cognitive_result,
        structure_hierarchy=cognitive_result.get("structure_hierarchy") or {},
        timeframe_roles=cognitive_result.get("timeframe_roles") or {},
        pois_by_tf=cognitive_result.get("poi_lifecycle") or {},
        watch_state=cognitive_result.get("watch_state") or {},
    )
    assert_smc_thesis_v2_quality(thesis_v2)
    authority = cognitive_result.get("smc_narrative_authority") or build_smc_narrative_authority(
        symbol=symbol,
        cognitive_result=cognitive_result,
    )
    assert_narrative_authority_contract(authority)
    thesis_v5 = build_smc_thesis_v5(
        symbol=symbol,
        cognitive_result=cognitive_result,
        narrative_authority=authority,
    )
    assert_smc_thesis_v5_quality(thesis_v5)
    payload["thesis_v2"] = {
        "status": thesis_v2["status"],
        "final_state": thesis_v2["final_state"],
        "final_action": thesis_v2["final_action"],
        "claim_count": thesis_v2["claim_count"],
    }
    payload["thesis_v5"] = {
        "status": thesis_v5["status"],
        "official_model": thesis_v5["official_model"],
        "official_state": thesis_v5["official_state"],
        "official_trade_plan_state": thesis_v5["official_trade_plan_state"],
        "show_trade_box": thesis_v5["show_trade_box"],
        "claim_count": thesis_v5["claim_count"],
    }
    evidence_map = {
        claim["claim_id"]: claim["evidence"]
        for claim in claims
    }
    lines = [f"# {symbol} Evidence-Linked SMC Thesis", ""]
    for claim in claims:
        lines.append(f"## {claim['title']}")
        lines.append("")
        lines.append(claim["claim"])
        lines.append("")
        lines.append("Evidence:")
        lines.extend(f"- `{item}`" for item in claim["evidence"])
        lines.append("")
    _write_json(output / "smc_trade_thesis.json", payload)
    _write_json(output / "thesis_evidence_map.json", evidence_map)
    _write_json(output / "smc_trade_thesis_v2.json", thesis_v2)
    _write_json(output / "smc_trade_thesis_v5.json", thesis_v5)
    (output / "smc_trade_thesis.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "smc_trade_thesis_v2.md").write_text(render_smc_thesis_v2_markdown(thesis_v2), encoding="utf-8")
    (output / "smc_trade_thesis_v5.md").write_text(render_smc_thesis_v5_markdown(thesis_v5), encoding="utf-8")
    return payload


def assert_thesis_evidence_links(thesis_payload: Mapping[str, Any]) -> None:
    for claim in thesis_payload.get("claims", []):
        if not claim.get("evidence"):
            raise AssertionError(f"Claim has no evidence: {claim}")
    if thesis_payload.get("forbidden_language_present"):
        raise AssertionError("Thesis contains forbidden live-signal language.")


def _run_route_health(symbol: str, output_dir: Path, *, enabled: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not enabled:
        report = {
            "status": "SKIPPED",
            "reason": "csv_mode_uses_local_verified_source",
            "tradingview_used_as_market_truth": False,
        }
        _write_json(output_dir / "route_health.json", report)
        return report
    report = run_route_health_preflight(symbol=symbol, interval="15m").to_dict()
    _write_json(output_dir / "route_health.json", report)
    return report


def _resolve_ohlcv_source(
    *,
    symbol: str,
    output_dir: Path,
    source: Path | None,
    mode: str,
    live_limit: int,
    min_live_bars: int,
) -> tuple[Path, dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if mode not in {"csv", "live"}:
        raise ValueError("mode must be 'csv' or 'live'")
    if mode == "live":
        try:
            manifest_path, manifest = acquire_verified_closed_ohlcv(
                symbol=symbol,
                output_dir=output_dir,
                interval="15m",
                limit=live_limit,
                min_bars=min_live_bars,
            )
            copied = output_dir / f"{symbol}_15m.csv"
            shutil.copy2(Path(manifest["source_csv"]), copied)
            manifest = dict(manifest)
            manifest["source_csv"] = _package_relative_path(copied, output_dir.parent)
            manifest["source_sha256"] = file_sha256(copied)
            manifest["local_package_source"] = manifest["source_csv"]
            _write_json(output_dir / "verified_closed_ohlcv_manifest.json", manifest)
            return copied, manifest
        except Exception as exc:
            failure_path = output_dir / "verified_closed_ohlcv_failure.json"
            if not failure_path.exists():
                _write_json(
                    failure_path,
                    {
                        "status": "FAILED",
                        "required_action": "NO_VALID_LIVE_TRADE",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "tradingview_used_as_market_truth": False,
                    },
                )
            if source is None:
                payload = json.loads(failure_path.read_text(encoding="utf-8"))
                return failure_path, payload
            # Fall back to a local source, preserving the live failure.
            fallback_payload = json.loads(failure_path.read_text(encoding="utf-8"))
            fallback_payload["fallback_source"] = source.name
            _write_json(output_dir / "verified_closed_ohlcv_failure.json", fallback_payload)

    if source is None:
        source = Path(f"data/ohlcv/binance_futures/{symbol}/{symbol}_15m_4year.csv").resolve()
    if not source.exists():
        raise FileNotFoundError(f"CSV source not found: {source}")
    copied = output_dir / f"{symbol}_15m.csv"
    shutil.copy2(source, copied)
    manifest = {
        "status": "VERIFIED_CSV_SOURCE",
        "authority": "local_research_market_truth",
        "venue": "BINANCE",
        "market_type": "USD-M perpetual futures",
        "symbol": symbol,
        "interval": "15m",
        "source_csv": _package_relative_path(copied, output_dir.parent),
        "original_source_csv_name": source.name,
        "original_source_sha256": file_sha256(source),
        "source_sha256": file_sha256(copied),
        "tradingview_used_as_market_truth": False,
    }
    _write_json(output_dir / "verified_closed_ohlcv_manifest.json", manifest)
    return copied, manifest


def _write_mtf_package(
    output_dir: Path,
    symbol: str,
    context: Any,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    source_path: Path,
    verified_manifest: Mapping[str, Any],
    truth_report: Mapping[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csvs: dict[str, dict[str, Any]] = {}
    data_depth: dict[str, dict[str, Any]] = {}
    min_research_depth = {"15m": 1500, "1h": 1000, "4h": 500, "1d": 365}
    for tf in TIMEFRAMES:
        path = output_dir / f"{symbol}_{tf}.csv"
        timeframe_dfs[tf].to_csv(path, index=False)
        rows = int(len(timeframe_dfs[tf]))
        minimum = min_research_depth[tf]
        csvs[tf] = {
            "path": _package_relative_path(path, output_dir.parent),
            "sha256": file_sha256(path),
            "rows": rows,
            "last_timestamp": str(timeframe_dfs[tf]["timestamp"].iloc[-1]),
        }
        data_depth[tf] = {
            "rows": rows,
            "min_research_depth": minimum,
            "status": "sufficient" if rows >= minimum else "shallow",
            "shortfall": max(0, minimum - rows),
        }
    derived_htf_consistency = _validate_derived_htf_consistency(timeframe_dfs, decision_available_at=context.decision_available_at)
    native_htf_audit = _audit_native_htf_against_derived(symbol=symbol, timeframe_dfs=timeframe_dfs)
    manifest = {
        "status": "PASS",
        "symbol": symbol,
        "source_15m": _package_relative_path(source_path, output_dir.parent),
        "decision_candle_open": context.decision_candle_open.isoformat(),
        "decision_available_at": context.decision_available_at.isoformat(),
        "verified_source_status": verified_manifest.get("status"),
        "truth_validation": truth_report,
        "csvs": csvs,
        "data_depth": data_depth,
        "derived_htf_consistency": derived_htf_consistency,
        "native_htf_audit": native_htf_audit,
        "analysis_window_policy": "bounded_recent_window_for_operator_gauntlet",
        "htf_policy": "1h/4h/1d derived from canonical 15m, incomplete HTF candles excluded.",
    }
    _write_json(output_dir / "mtf_package_manifest.json", manifest)
    _write_json(output_dir / "truth_validation.json", truth_report)
    return manifest


def _validate_derived_htf_consistency(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    *,
    decision_available_at: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Compare provided HTF data against a pure 15m resampled reference.

    The gauntlet currently derives HTF candles from 15m. This validator
    resamples the 15m frame again and checks the most recent HTF candle
    for large OHLC discrepancies, surfacing data-quality risk without
    claiming native exchange HTF validation.
    """
    if "15m" not in timeframe_dfs:
        return {"status": "no_15m_reference", "checks": {}}

    df15 = timeframe_dfs["15m"].copy()
    df15["timestamp"] = pd.to_datetime(df15["timestamp"], utc=True)
    cutoff = _as_utc_timestamp(decision_available_at) if decision_available_at is not None else None
    if cutoff is not None:
        df15 = df15.loc[df15["timestamp"] + pd.Timedelta(minutes=15) <= cutoff].copy()
    df15 = df15.set_index("timestamp")
    checks: dict[str, dict[str, Any]] = {}
    for tf, rule in [("1h", "1h"), ("4h", "4h"), ("1d", "D")]:
        ht = timeframe_dfs.get(tf)
        if ht is None or ht.empty:
            checks[tf] = {"status": "missing_htf_data"}
            continue
        ht = ht.copy()
        ht["timestamp"] = pd.to_datetime(ht["timestamp"], utc=True)
        if cutoff is not None:
            ht = ht.loc[ht["timestamp"] + _tf_duration(tf) <= cutoff].copy()
        if ht.empty:
            checks[tf] = {"status": "no_closed_htf_rows_at_cutoff", "decision_available_at": cutoff.isoformat() if cutoff is not None else None}
            continue
        resampled = df15.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        if cutoff is not None:
            resampled = resampled.loc[resampled.index + _tf_duration(tf) <= cutoff]
        if resampled.empty:
            checks[tf] = {"status": "resample_empty"}
            continue
        r_last = resampled.iloc[-1]
        h_last = ht.iloc[-1]
        diffs: dict[str, float] = {}
        for col in ["open", "high", "low", "close"]:
            try:
                diffs[col] = abs(float(r_last[col]) - float(h_last[col]))
            except Exception:
                diffs[col] = float("nan")
        tolerance = max(float(h_last.get("close", 1) or 1) * 1e-4, 0.01)
        max_diff = max((v for v in diffs.values() if v == v), default=0.0)
        checks[tf] = {
            "status": "aligned" if max_diff <= tolerance else "discrepancy",
            "max_diff": max_diff,
            "tolerance": tolerance,
            "diffs": diffs,
            "resampled_last_close": r_last.get("close"),
            "provided_last_close": h_last.get("close"),
            "closed_cutoff_applied": cutoff.isoformat() if cutoff is not None else None,
        }
    overall = "aligned" if all(c.get("status") == "aligned" for c in checks.values()) else "review"
    return {
        "status": overall,
        "validation_type": "derived_htf_consistency",
        "native_exchange_htf_used": False,
        "checks": checks,
    }


def _validate_direct_vs_resampled(timeframe_dfs: Mapping[str, pd.DataFrame]) -> dict[str, Any]:
    """Backward-compatible alias for older WP-0023 tests.

    New manifests use ``derived_htf_consistency`` because this check does not
    prove native Binance HTF agreement.
    """
    return _validate_derived_htf_consistency(timeframe_dfs)


def _audit_native_htf_against_derived(
    *,
    symbol: str,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Optionally compare derived HTF candles with native exchange HTF files.

    If local HTF files are themselves marked ``derived_from_15m`` this audit
    refuses to call them native. That is the key honesty guard.
    """
    root = data_root or Path("data/ohlcv/binance_futures")
    checks: dict[str, dict[str, Any]] = {}
    for tf in ("1h", "4h", "1d"):
        native_path = root / symbol / f"{symbol}_{tf}_4year.csv"
        if not native_path.exists():
            checks[tf] = {"status": "missing_native_file", "path": str(native_path)}
            continue
        try:
            native = pd.read_csv(native_path)
        except Exception as exc:
            checks[tf] = {"status": "native_file_unreadable", "path": str(native_path), "error": str(exc)}
            continue
        source_values = set(str(v) for v in native.get("source", pd.Series(dtype=str)).dropna().head(20).tolist())
        if any("derived_from_15m" in value for value in source_values):
            checks[tf] = {
                "status": "not_native_file",
                "path": str(native_path),
                "reason": "local HTF file source column indicates derived_from_15m",
            }
            continue
        derived = timeframe_dfs.get(tf)
        if derived is None or derived.empty or native.empty:
            checks[tf] = {"status": "missing_comparable_data", "path": str(native_path)}
            continue
        native = native.copy()
        derived = derived.copy()
        native["timestamp"] = pd.to_datetime(native["timestamp"], utc=True)
        derived["timestamp"] = pd.to_datetime(derived["timestamp"], utc=True)
        merged = pd.merge(
            derived.tail(100),
            native,
            on="timestamp",
            how="inner",
            suffixes=("_derived", "_native"),
        )
        if merged.empty:
            checks[tf] = {"status": "no_timestamp_overlap", "path": str(native_path)}
            continue
        diffs = []
        for _, row in merged.tail(20).iterrows():
            row_diffs = {
                col: abs(float(row[f"{col}_derived"]) - float(row[f"{col}_native"]))
                for col in ("open", "high", "low", "close")
            }
            max_diff = max(row_diffs.values())
            tolerance = max(float(row["close_native"]) * 1e-4, 0.01)
            if max_diff > tolerance:
                diffs.append({
                    "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                    "max_diff": max_diff,
                    "tolerance": tolerance,
                    "diffs": row_diffs,
                })
        checks[tf] = {
            "status": "aligned" if not diffs else "discrepancy",
            "path": str(native_path),
            "matched_rows": int(len(merged)),
            "recent_discrepancies": diffs[:10],
        }
    if all(check.get("status") == "aligned" for check in checks.values()):
        status = "aligned"
    elif any(check.get("status") in {"discrepancy", "native_file_unreadable"} for check in checks.values()):
        status = "review"
    else:
        status = "not_available"
    return {
        "status": status,
        "validation_type": "native_htf_audit",
        "native_exchange_htf_used": status in {"aligned", "review"},
        "checks": checks,
    }


def _run_visual_capture(symbol: str, output_dir: Path, *, visual_mode: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if visual_mode == "skip":
        manifest = {
            "status": "SKIPPED",
            "reason": "visual_capture_not_requested",
            "tradingview_used_as_market_truth": False,
            "screenshots": {},
        }
        _write_json(output_dir / "webbridge_session_manifest.json", manifest)
        return manifest
    try:
        status = _kimi_status()
        _write_json(output_dir / "webbridge_status.json", status)
        if not status.get("running") or not status.get("extension_connected"):
            raise RuntimeError(f"Kimi WebBridge unhealthy: {status}")
        _manifest_path, manifest = build_live_visual_manifest(symbol=symbol, output_dir=output_dir, session="wp0020-tv-visual")
        manifest = dict(manifest)
        if isinstance(manifest.get("screenshots"), Mapping):
            manifest["screenshots"] = {
                label: _package_relative_path(Path(str(path)), output_dir.parent)
                for label, path in manifest["screenshots"].items()
            }
        manifest["status"] = "PASS"
        manifest["tradingview_used_as_market_truth"] = False
        _write_json(output_dir / "webbridge_session_manifest.json", manifest)
        _write_json(output_dir / "screenshot_capture_log.json", {"status": "PASS", "screenshots": manifest.get("screenshots", {})})
        return manifest
    except Exception as exc:
        manifest = {
            "status": "FAILED",
            "reason": "visual_capture_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "tradingview_used_as_market_truth": False,
            "screenshots": {},
        }
        _write_json(output_dir / "webbridge_session_manifest.json", manifest)
        _write_json(output_dir / "screenshot_capture_log.json", manifest)
        return manifest


def _analysis_timeframe_dfs(timeframe_dfs: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Bound each timeframe to a practical recent window for the gauntlet.

    The full source remains recorded in manifests. This window is the actual
    decision-visible sample used for rendering, annotation, PEV2, and cognitive
    checks, keeping the operator gauntlet deterministic and fast.
    """
    # Research-depth windows aligned with MIN_RESEARCH_DEPTH in structure_hierarchy.
    # Tail safely returns fewer bars when the source is shorter (e.g. operator gauntlet).
    limits = {"15m": 1500, "1h": 1000, "4h": 500, "1d": 365}
    return {
        tf: timeframe_dfs[tf].tail(limits[tf]).reset_index(drop=True).copy()
        for tf in TIMEFRAMES
    }


def _kimi_status() -> dict[str, Any]:
    cmd = [str(Path.home() / ".kimi-webbridge/bin/kimi-webbridge"), "status"]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"running": False, "extension_connected": False, "error": result.stderr.strip() or result.stdout.strip()}
        return json.loads(result.stdout)
    except Exception as exc:
        return {"running": False, "extension_connected": False, "error_type": type(exc).__name__, "error": str(exc)}


def _annotation_events(timeframe: str, analysis: Mapping[str, Any], df: pd.DataFrame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, event in enumerate(analysis.get("events", []) or []):
        candle_index = int(event.get("index", 0))
        timestamp = _timestamp_at(df, candle_index, event.get("timestamp"))
        events.append(
            {
                "event_id": f"{timeframe}:event:{index}:{event.get('label')}",
                "annotation_type": event.get("label"),
                "timeframe": timeframe,
                "candle_index": candle_index,
                "timestamp": timestamp,
                "price": event.get("price"),
                "direction": event.get("direction"),
                "source": "engine_analysis_event",
            }
        )
    for index, zone in enumerate(analysis.get("zones", []) or []):
        candle_index = int(zone.get("end_index") or zone.get("start_index") or 0)
        timestamp = _timestamp_at(df, candle_index, None)
        events.append(
            {
                "event_id": f"{timeframe}:zone:{index}:{zone.get('kind')}",
                "annotation_type": zone.get("kind"),
                "timeframe": timeframe,
                "candle_index": candle_index,
                "timestamp": timestamp,
                "price": None,
                "price_low": zone.get("low"),
                "price_high": zone.get("high"),
                "direction": zone.get("direction"),
                "lifecycle_status": zone.get("status"),
                "source": "engine_analysis_zone",
            }
        )
    return events


def _thesis_claims(
    symbol: str,
    cognitive_result: Mapping[str, Any],
    annotation_manifest: Mapping[str, Any],
    visual_reconciliation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    final_action = cognitive_result.get("final_action", "NO_SIGNAL")
    regime = cognitive_result.get("regime") or {}
    contradiction = cognitive_result.get("contradiction") or {}
    uncertainty = cognitive_result.get("uncertainty") or {}
    refusal = cognitive_result.get("refusal") or {}
    annotations = annotation_manifest.get("annotations", [])
    first_annotation = annotations[0]["event_id"] if annotations else "annotation_manifest:no_events"
    return [
        {
            "claim_id": "market_context",
            "title": "Market Context",
            "claim": f"{symbol} is evaluated from verified OHLCV with TradingView excluded from market truth.",
            "evidence": ["truth_validation.status", "mtf_package_manifest.verified_source_status"],
        },
        {
            "claim_id": "regime",
            "title": "Regime",
            "claim": (
                f"Regime read is {regime.get('structure_regime')} / {regime.get('volatility_regime')} / "
                f"{regime.get('liquidity_regime')} with confidence {regime.get('confidence')}."
            ),
            "evidence": ["06_cognitive/regime_report.json"],
        },
        {
            "claim_id": "structure_and_poi",
            "title": "Structure / POI",
            "claim": f"SMC annotations were generated as rule-based research objects; first traceable object is `{first_annotation}`.",
            "evidence": ["04_debug_legacy_annotations/smc_annotation_manifest.json", first_annotation],
        },
        {
            "claim_id": "contradiction",
            "title": "Contradiction",
            "claim": (
                f"Timeframe resolution ended as `{contradiction.get('outcome')}` with dominant direction "
                f"`{contradiction.get('dominant_direction')}`."
            ),
            "evidence": ["06_cognitive/contradiction_report.json"],
        },
        {
            "claim_id": "uncertainty",
            "title": "Uncertainty",
            "claim": f"Signal confidence is `{uncertainty.get('signal_confidence')}` and verdict is `{uncertainty.get('final_verdict')}`.",
            "evidence": ["06_cognitive/uncertainty_report.json"],
        },
        {
            "claim_id": "visual_audit",
            "title": "TradingView Visual Audit",
            "claim": f"Visual reconciliation status is `{visual_reconciliation.get('status')}` and did not change market truth.",
            "evidence": ["08_visual_reconciliation/visual_reconciliation_report.json"],
        },
        {
            "claim_id": "final_decision",
            "title": "Final Decision",
            "claim": f"Final colleague action is `{final_action}` because refusal policy returned `{refusal.get('final_action')}`.",
            "evidence": ["06_cognitive/refusal_report.json", "10_memory/decision_memory.jsonl"],
        },
    ]


def _perception_manifest(cognitive_result: Mapping[str, Any]) -> dict[str, Any]:
    by_tf = cognitive_result.get("perception_by_tf", {})
    return {
        "status": "PASS" if by_tf else "NOT_RUN",
        "source": "PerceptionEngineV2",
        "timeframes": sorted(by_tf.keys()),
        "event_counts": {
            tf: {
                "swings": sum(len(v) for v in payload.get("swings", {}).values()),
                "structure_breaks": len(payload.get("structure_breaks", []) or []),
                "fvgs": len(payload.get("fvgs", []) or []),
            }
            for tf, payload in by_tf.items()
        },
    }


def _memory_manifest(memory_path: Path, *, package_root: Path | None = None) -> dict[str, Any]:
    if not memory_path.exists():
        return {"status": "NOT_WRITTEN", "record_count": 0}
    lines = [line for line in memory_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]
    superseded_count = sum(1 for r in records if r.get("superseded_by"))
    root = package_root or memory_path.parent.parent
    active_index_path = memory_path.parent / "active_truth_index.json"
    active_index = json.loads(active_index_path.read_text(encoding="utf-8")) if active_index_path.exists() else None
    return {
        "status": "PASS",
        "path": _package_relative_path(memory_path, root),
        "sha256": file_sha256(memory_path),
        "record_count": len(lines),
        "superseded_count": superseded_count,
        "current_count": len(lines) - superseded_count,
        "active_truth_index": None if active_index is None else {
            "path": _package_relative_path(active_index_path, root),
            "sha256": file_sha256(active_index_path),
            "symbols": sorted((active_index.get("symbols") or {}).keys()),
        },
    }


def _status_from_stage_results(stage_results: Mapping[str, Mapping[str, Any]]) -> tuple[str, str | None]:
    if stage_results.get("02_mtf_package", {}).get("truth_validation", {}).get("status") not in {None, "PASS"}:
        return "FAIL", "02_mtf_package"
    if stage_results.get("04_debug_legacy_annotations", {}).get("status") != "PASS":
        return "FAIL", "04_debug_legacy_annotations"
    if stage_results.get("04a_story_charts", {}).get("status") not in {"PASS", "PARTIAL_PASS"}:
        return "FAIL", "04a_story_charts"
    if "04b_official_charts" in stage_results and stage_results.get("04b_official_charts", {}).get("status") != "PASS":
        return "FAIL", "04b_official_charts"
    if stage_results.get("06_cognitive", {}).get("status") != "PASS":
        return "FAIL", "06_cognitive"
    if stage_results.get("12_research_events", {}).get("status") != "PASS":
        return "FAIL", "12_research_events"
    if stage_results.get("09_smc_thesis", {}).get("status") != "PASS":
        return "FAIL", "09_smc_thesis"
    watch = stage_results.get("06_cognitive", {}).get("watch_state") or {}
    active_poi = watch.get("active_poi") if isinstance(watch, Mapping) else None
    if isinstance(active_poi, Mapping) and active_poi.get("validity_status") != "VALID_ACTIVE_SETUP_POI":
        return "FAIL", "06_cognitive"
    visual_status = stage_results.get("08_visual_reconciliation", {}).get("status")
    review_flags = _review_flags(stage_results)
    if visual_status in {"REVIEW_REQUIRED", "VISUAL_CONTEXT_UNVERIFIED", "VISUAL_CONTEXT_MISMATCH"}:
        return "PARTIAL_PASS", "07_tradingview_visual"
    if review_flags:
        return "PASS_WITH_REVIEW_FLAGS", None
    if visual_status == "VISUAL_AUDIT_AVAILABLE":
        return "PASS", None
    return "PARTIAL_PASS", "07_tradingview_visual"


def _review_flags(stage_results: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    mtf = stage_results.get("02_mtf_package", {})
    derived = mtf.get("derived_htf_consistency") or {}
    if derived.get("status") not in {None, "aligned"}:
        flags.append({
            "flag": "DERIVED_HTF_CONSISTENCY_REVIEW",
            "severity": "important",
            "status": derived.get("status"),
        })
    native = mtf.get("native_htf_audit") or {}
    if native.get("status") == "review":
        flags.append({"flag": "NATIVE_HTF_AUDIT_REVIEW", "severity": "important", "status": native.get("status")})
    for tf, depth in (mtf.get("data_depth") or {}).items():
        if depth.get("status") == "shallow" and tf in {"1d", "4h"}:
            flags.append({
                "flag": "SHALLOW_HTF_CONTEXT",
                "severity": "non_critical",
                "timeframe": tf,
                "shortfall": depth.get("shortfall"),
            })
    story = stage_results.get("04a_story_charts", {})
    if story.get("status") == "PARTIAL_PASS":
        flags.append({"flag": "STORY_CHART_PARTIAL", "severity": "important"})
    official = stage_results.get("04b_official_charts", {})
    if official.get("show_trade_box") and official.get("official_trade_plan_state") != "TRADE_PLAN_READY":
        flags.append({"flag": "PREMATURE_TRADE_BOX", "severity": "critical"})
    watch = stage_results.get("06_cognitive", {}).get("watch_state") or {}
    selection = watch.get("poi_selection") if isinstance(watch, Mapping) else {}
    if isinstance(selection, Mapping) and selection.get("status") not in {None, "SELECTED_ACTIVE_POI"}:
        flags.append({
            "flag": "NO_VALID_ACTIVE_POI",
            "severity": "non_critical",
            "status": selection.get("status"),
        })
    visual = stage_results.get("08_visual_reconciliation", {})
    if visual.get("status") not in {None, "VISUAL_AUDIT_AVAILABLE"}:
        flags.append({
            "flag": "VISUAL_REVIEW_REQUIRED",
            "severity": "important",
            "status": visual.get("status"),
        })
    return flags


def _write_final_report(
    root: Path,
    stage_results: Mapping[str, Mapping[str, Any]],
    *,
    status: str,
    failed_layer: str | None,
) -> dict[str, Any]:
    final_dir = root / "11_final_report"
    final_dir.mkdir(parents=True, exist_ok=True)
    cognitive = stage_results.get("06_cognitive", {})
    review_flags = _review_flags(stage_results)
    confidence = _confidence_summary(stage_results)
    summary = {
        "status": status,
        "failed_layer": failed_layer,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_edge_claimed": False,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "capital_risk": 0,
        "full_summary": {
            "live_route_result": stage_results.get("00_route_health", {}).get("overall") or stage_results.get("00_route_health", {}).get("status"),
            "route_failure_or_success_reason": stage_results.get("00_route_health", {}).get("required_action") or stage_results.get("00_route_health", {}).get("reason"),
            "clean_charts_generated": _count_chart_files(stage_results.get("03_clean_charts", {})),
            "legacy_debug_charts_generated": _count_chart_files(stage_results.get("04_debug_legacy_annotations", {})),
            "decision_authority_story_charts_generated": _count_chart_files(stage_results.get("04a_story_charts", {})),
            "story_charts_generated": _count_chart_files(stage_results.get("04a_story_charts", {})),
            "official_narrative_charts_generated": _count_chart_files(stage_results.get("04b_official_charts", {})),
            "official_state": (cognitive.get("smc_narrative_authority") or {}).get("official_state"),
            "official_model": (cognitive.get("smc_narrative_authority") or {}).get("official_model"),
            "official_trade_plan_state": (cognitive.get("smc_narrative_authority") or {}).get("official_trade_plan_state"),
            "show_trade_box": (cognitive.get("smc_narrative_authority") or {}).get("show_trade_box"),
            "tradingview_screenshots_captured": len(stage_results.get("07_tradingview_visual", {}).get("screenshots", {}) or {}),
            "visual_reconciliation_result": stage_results.get("08_visual_reconciliation", {}).get("status"),
            "perception_event_count": _perception_event_count(stage_results.get("05_perception", {})),
            "research_event_count": stage_results.get("12_research_events", {}).get("event_count", 0),
            "pending_outcome_contract": stage_results.get("12_research_events", {}).get("outcome_contract_status"),
            "regime_result": (cognitive.get("regime") or {}).get("structure_regime"),
            "contradiction_result": (cognitive.get("contradiction") or {}).get("outcome"),
            "uncertainty_score": (cognitive.get("uncertainty") or {}).get("signal_confidence"),
            "pipeline_confidence": confidence["pipeline_confidence"],
            "analysis_confidence": confidence["analysis_confidence"],
            "context_confidence": confidence["context_confidence"],
            "poi_confidence": confidence["poi_confidence"],
            "visual_confidence": confidence["visual_confidence"],
            "execution_readiness_confidence": confidence["execution_readiness_confidence"],
            "final_confidence_label": confidence["final_confidence_label"],
            "execution_readiness_state": (cognitive.get("execution_readiness") or {}).get("state"),
            "inducement_continuation_state": (cognitive.get("inducement_continuation") or {}).get("state"),
            "review_flag_count": len(review_flags),
            "refusal_result": (cognitive.get("refusal") or {}).get("final_action"),
            "final_colleague_action": cognitive.get("final_action"),
            "thesis_generated": stage_results.get("09_smc_thesis", {}).get("status") == "PASS",
            "memory_record_count": stage_results.get("10_memory", {}).get("record_count", 0),
            "final_gauntlet_status": status,
            "failed_layer": failed_layer,
        },
        "review_flags": review_flags,
        "confidence_summary": confidence,
        "stage_results": stage_results,
    }
    _write_json(final_dir / "gauntlet_report.json", summary)
    lines = ["# WP-0020 Market Colleague Gauntlet", "", f"Status: `{status}`", f"Failed layer: `{failed_layer or 'none'}`", ""]
    for key, value in summary["full_summary"].items():
        lines.append(f"- {key}: `{value}`")
    (final_dir / "gauntlet_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def _confidence_summary(stage_results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    uncertainty = (stage_results.get("06_cognitive", {}).get("uncertainty") or {})
    watch = stage_results.get("06_cognitive", {}).get("watch_state") or {}
    active_poi = watch.get("active_poi") if isinstance(watch, Mapping) else None
    visual_status = stage_results.get("08_visual_reconciliation", {}).get("status")
    visual_confidence = 0.9 if visual_status == "VISUAL_AUDIT_AVAILABLE" else 0.0 if visual_status else None
    execution_readiness = stage_results.get("06_cognitive", {}).get("execution_readiness") or {}
    execution_confidence = float(execution_readiness.get("confidence", 0.0) or 0.0)
    poi_confidence = 1.0 if isinstance(active_poi, Mapping) and active_poi.get("validity_status") == "VALID_ACTIVE_SETUP_POI" else 0.0
    pipeline = float(uncertainty.get("pipeline_confidence", uncertainty.get("signal_confidence", 0.0)) or 0.0)
    context = float(uncertainty.get("context_confidence", 0.0) or 0.0)
    structure_analysis = float(uncertainty.get("analysis_confidence", 0.0) or 0.0)
    analysis = _bounded(
        structure_analysis * 0.25
        + context * 0.18
        + poi_confidence * 0.22
        + (visual_confidence or 0.0) * 0.17
        + execution_confidence * 0.18
    )
    return {
        "pipeline_confidence": round(pipeline, 4),
        "analysis_confidence": round(analysis, 4),
        "context_confidence": round(context, 4),
        "poi_confidence": round(poi_confidence, 4),
        "visual_confidence": None if visual_confidence is None else round(visual_confidence, 4),
        "execution_readiness_confidence": round(execution_confidence, 4),
        "final_confidence_label": _confidence_label(analysis),
        "note": "Pipeline confidence measures whether the machinery ran; analysis confidence measures whether the SMC read is reliable enough to trust.",
    }


def _count_chart_files(stage: Mapping[str, Any]) -> int:
    charts = stage.get("charts", {})
    return sum(1 for info in charts.values() if _manifest_path_exists(info))


def _perception_event_count(stage: Mapping[str, Any]) -> int:
    counts = stage.get("event_counts", {})
    return sum(int(v.get("structure_breaks", 0)) + int(v.get("fvgs", 0)) for v in counts.values())


def _image_manifest(path: Path, *, candle_count: int, timeframe: str, package_root: Path | None = None) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "path": _package_relative_path(path, package_root or path.parent),
        "sha256": file_sha256(path),
        "width": width,
        "height": height,
        "timeframe": timeframe,
        "candle_count": candle_count,
        "exists_at_write": True,
    }


def _package_relative_path(path: Path, package_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(package_root.resolve()))
    except ValueError:
        return str(path)


def _manifest_path_exists(info: Mapping[str, Any]) -> bool:
    if info.get("exists_at_write") is True:
        return True
    return _path_exists(info.get("path"))


def _path_exists(value: Any, *, package_root: Path | None = None) -> bool:
    if value in {None, ""}:
        return False
    path = Path(str(value)).expanduser()
    if path.exists():
        return True
    if package_root is not None:
        return (package_root / path).exists()
    return False


def _timestamp_at(df: pd.DataFrame, candle_index: int, fallback: str | None) -> str:
    if 0 <= candle_index < len(df):
        return pd.Timestamp(df["timestamp"].iloc[candle_index]).isoformat()
    return str(fallback or "")


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper().replace("/", "").replace("-", "")
    if normalized.endswith("USD") and not normalized.endswith("USDT"):
        normalized += "T"
    return normalized


def _decision_datetime(value: pd.Timestamp) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def _as_utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _tf_duration(timeframe: str) -> pd.Timedelta:
    return {
        "15m": pd.Timedelta(minutes=15),
        "1h": pd.Timedelta(hours=1),
        "4h": pd.Timedelta(hours=4),
        "1d": pd.Timedelta(days=1),
    }.get(str(timeframe), pd.Timedelta(0))


def _prepare_structure(root: Path) -> None:
    for name in GAUNTLET_STRUCTURE:
        (root / name).mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _payload_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _confidence_label(value: float) -> str:
    if value < 0.35:
        return "VERY_LOW_ANALYSIS_CONFIDENCE"
    if value < 0.55:
        return "LOW_ANALYSIS_CONFIDENCE"
    if value < 0.75:
        return "MODERATE_ANALYSIS_CONFIDENCE"
    return "HIGH_ANALYSIS_CONFIDENCE"


def _forbidden_language_present(claims: list[dict[str, Any]]) -> bool:
    forbidden = ("guaranteed setup", "high probability trade", "enter now", "risk this amount", "live signal")
    text = "\n".join(str(claim.get("claim", "")).lower() for claim in claims)
    return any(phrase in text for phrase in forbidden)
