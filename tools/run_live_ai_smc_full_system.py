#!/usr/bin/env python3
"""Run the observe-only AI SMC v3 pipeline on current market data.

This is a system test harness, not an execution tool. It uses Binance USD-M
futures for crypto symbols and Yahoo chart data for XAU/GC futures proxy.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER
from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest
from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3
from smc_desk.data.historical_backfill import fetch_historical_closed_ohlcv
from smc_desk.data.timeframe_reconstruction import resample_ohlcv as reconstruct_timeframe_ohlcv
from smc_desk.perception.structure_narrative import build_structure_narrative, derive_strict_htf_bias


BINANCE_BASE = "https://fapi.binance.com"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
TIMEFRAME_DELTAS = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}
APPROVED_PUBLIC_DATA_HOSTS = {"fapi.binance.com", "query1.finance.yahoo.com"}
DNS_FALLBACK_AUDIT: list[dict[str, Any]] = []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "SOLUSDT", "XAUUSD"])
    parser.add_argument("--output-root", default="analysis_runs")
    parser.add_argument("--allow-shallow-context", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(args.output_root).expanduser().resolve() / f"LIVE_FULL_SYSTEM_AI_SMC_V3_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for symbol in args.symbols:
        symbol_root = root / normalize_symbol(symbol)
        symbol_root.mkdir(parents=True, exist_ok=True)
        try:
            timeframe_dfs, source_manifest = load_live_timeframes(symbol)
            provider = CallableAISMCProvider(
                lambda request, manifest=source_manifest: build_conservative_ai_payload(request, manifest),
                provider_name="local_codex_thread_brain",
                model_name="prompt_os_v1_conservative_observe_only",
                provider_mode="LOCAL_DETERMINISTIC_PROVIDER",
            )
            result = run_ai_smc_orchestrator_v3(
                symbol=normalize_symbol(symbol),
                timeframe_dfs=timeframe_dfs,
                provider=provider,
                output_dir=symbol_root,
                detector_candidates=None,
                session_context={"source_manifest": source_manifest, "live_system_test": True},
                enforce_minimum_depth=not args.allow_shallow_context,
            )
            summary = {
                "symbol": normalize_symbol(symbol),
                "status": result.status,
                "official_state": result.report.get("official_state"),
                "validation_result": result.report.get("validation_result"),
                "hard_issues": result.report.get("hard_issues", []),
                "provider": result.report.get("provider"),
                "source_manifest": source_manifest,
                "output_dir": str(symbol_root),
                "official_chart": result.report.get("official_chart"),
                "thesis_path": str(symbol_root / "15_ai_thesis" / "thesis.md"),
                "last_prices": {tf: float(df["close"].iloc[-1]) for tf, df in timeframe_dfs.items()},
                "last_timestamps": {tf: str(df["timestamp"].iloc[-1]) for tf, df in timeframe_dfs.items()},
                "last_open_timestamps": {tf: str(df["timestamp"].iloc[-1]) for tf, df in timeframe_dfs.items()},
                "last_close_timestamps": {tf: str(df["timestamp"].iloc[-1] + TIMEFRAME_DELTAS[tf]) for tf, df in timeframe_dfs.items()},
            }
            try:
                colleague = write_colleague_memory_and_narrative_shadow(
                    symbol_root=symbol_root,
                    output_root=args.output_root,
                    symbol=normalize_symbol(symbol),
                )
            except Exception as exc:  # noqa: BLE001 -- additive evidence may never fail a run
                colleague = {
                    "memory_status": f"failed:{type(exc).__name__}",
                    "shadow_status": f"failed:{type(exc).__name__}",
                    "transition_notes": [],
                }
            summary["colleague_memory"] = colleague.get("memory_status")
            summary["memory_store_updated"] = colleague.get("memory_store_updated")
            summary["memory_forward_transition"] = colleague.get("memory_forward_transition")
            summary["memory_market_identity"] = colleague.get("market_identity")
            summary["narrative_shadow_plan"] = colleague.get("shadow_status")
            summary["narrative_shadow_comparison"] = colleague.get("shadow_comparison_status")
            summary["narrative_shadow_metrics"] = colleague.get("shadow_comparison_metrics")
            summary["memory_transition_notes"] = colleague.get("transition_notes")
            summary["perception_failures"] = colleague.get("perception_failures")
            summary.update(
                record_selective_decision(
                    symbol_root=symbol_root,
                    output_root=args.output_root,
                    symbol=normalize_symbol(symbol),
                    summary=summary,
                )
            )
        except Exception as exc:
            summary = {
                "symbol": normalize_symbol(symbol),
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "output_dir": str(symbol_root),
            }
        results.append(summary)

    final = {
        "schema": "live_ai_smc_full_system_test_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(root),
        "symbols": args.symbols,
        "observe_only": True,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "api_llm_called": False,
        "results": results,
    }
    (root / "live_full_system_summary.json").write_text(json.dumps(final, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (root / "live_full_system_summary.md").write_text(render_summary_markdown(final), encoding="utf-8")
    print(json.dumps(final, indent=2, sort_keys=True, default=str))


def _final_evidence_pack_path(symbol_root: Path) -> Path | None:
    """Resolve the evidence pack that owns the orchestrator's final loop."""
    candidates: list[tuple[int, Path]] = []
    for path in symbol_root.glob("10_smc_evidence_pack_run_*/evidence_pack.json"):
        suffix = path.parent.name.rsplit("_", 1)[-1]
        try:
            candidates.append((int(suffix), path))
        except ValueError:
            continue
    path = (
        sorted(candidates)[-1][1]
        if candidates
        else symbol_root / "10_smc_evidence_pack" / "evidence_pack.json"
    )
    return path if path.exists() else None


def _load_final_evidence_pack(symbol_root: Path) -> dict[str, Any] | None:
    """Load the last loop's sealed evidence pack artifact, if one exists."""
    pack_path = _final_evidence_pack_path(symbol_root)
    if pack_path is None:
        return None
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def write_colleague_memory_and_narrative_shadow(
    *,
    symbol_root: Path,
    output_root: str | Path,
    symbol: str,
) -> dict[str, Any]:
    """Record cross-run memory and the narrative planner's shadow selection.

    Both artifacts are additive run-package evidence written to a new
    ``18_colleague_memory_narrative`` stage folder, after the canonical run
    has completed:

    * ``market_state_transition.json`` -- what changed since this symbol's
      previous run (the colleague's memory: liquidity taken, bias or POI
      change, advance/regression along the trader sequence).
    * ``narrative_annotation_plan_shadow.json`` -- the narrative planner's
      compositional selection (range, then the draw, then the causal POI,
      then structure per rendered timeframe). It is **not rendered and not
      validated**: the canonical, validator-checked plan remains
      ``annotation_plan_v2``. Recording the shadow lets the analyst-marked
      development cohort (WP-SMC-13) measure the planner against the
      composer before any selector is promoted or retired.

    Fail-soft by contract: every step reports a status string; nothing here
    may fail the run, alter the sealed evidence pack (pack hash stays a pure
    function of evidence), or create signal authority.
    """
    outcome: dict[str, Any] = {
        "memory_status": "not_attempted",
        "shadow_status": "not_attempted",
        "shadow_comparison_status": "not_attempted",
        "transition_notes": [],
    }
    try:
        pack_path = _final_evidence_pack_path(symbol_root)
        pack = _load_final_evidence_pack(symbol_root)
    except Exception as exc:  # noqa: BLE001 -- additive evidence, never fatal
        outcome["memory_status"] = f"evidence_pack_unavailable:{type(exc).__name__}"
        outcome["shadow_status"] = outcome["memory_status"]
        return outcome
    if pack is None:
        outcome["memory_status"] = "evidence_pack_unavailable"
        outcome["shadow_status"] = "evidence_pack_unavailable"
        return outcome

    evidence_fingerprint = _file_sha256(pack_path) if pack_path is not None else None
    market_identity = _market_identity_from_pack(pack, symbol)
    outcome["market_identity"] = market_identity

    try:
        outcome["perception_failures"] = _perception_failures(pack)
    except Exception as exc:  # noqa: BLE001 -- additive evidence, never fatal
        outcome["perception_failures"] = [f"unreadable:{type(exc).__name__}"]

    stage_dir = symbol_root / "18_colleague_memory_narrative"
    session = pack.get("session_context") if isinstance(pack, dict) else None
    certificate = session.get("source_identity_certificate") if isinstance(session, dict) else None
    source_status = (
        str(certificate.get("status") or "")
        if isinstance(certificate, dict)
        else ""
    )
    if source_status in {"MISMATCH", "MISMATCH_PROXY"}:
        failures = list(certificate.get("failures") or []) if isinstance(certificate, dict) else []
        reason = (
            f"Market source identity is {source_status}; cross-run state and narrative comparison "
            "are suppressed for the requested instrument."
        )
        if failures:
            reason = f"{reason} {failures[0]}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        memory_record = {
            "schema": "market_state_transition_v2",
            "symbol": symbol,
            "store_status": "suppressed_source_identity",
            "store_updated": False,
            "forward_transition": False,
            "market_identity": market_identity,
            "source_identity_status": source_status,
            "authority": "source_identity_quarantine",
            "signal_allowed": False,
            "notes": [reason],
            "transition": None,
            "store_path": None,
            "lock_path": None,
        }
        (stage_dir / "market_state_transition.json").write_text(
            json.dumps(memory_record, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        comparison = {
            "status": "SUPPRESSED_SOURCE_IDENTITY",
            "shadow_count": 0,
            "canonical_count": 0,
            "matched_count": 0,
            "shadow_precision": None,
            "canonical_recall": None,
            "human_review_status": "NOT_APPLICABLE",
            "promotion_eligible": False,
            "reason": reason,
        }
        shadow_record = {
            "schema": "narrative_annotation_plan_shadow_v2",
            "shadow_comparison_only": True,
            "rendered": False,
            "plan": {"selections": [], "notes": [reason]},
            "comparison": comparison,
            "authority": "source_identity_quarantine",
            "signal_allowed": False,
            "provenance": {
                "evidence_pack": str(pack_path) if pack_path is not None else None,
                "evidence_pack_sha256": evidence_fingerprint,
                "market_identity": market_identity,
                "source_identity_status": source_status,
            },
        }
        (stage_dir / "narrative_annotation_plan_shadow.json").write_text(
            json.dumps(shadow_record, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        outcome.update(
            {
                "memory_status": "suppressed_source_identity",
                "memory_store_updated": False,
                "memory_forward_transition": False,
                "transition_notes": [reason],
                "shadow_status": "suppressed_source_identity",
                "shadow_comparison_status": "SUPPRESSED_SOURCE_IDENTITY",
                "shadow_comparison_metrics": {
                    key: comparison[key]
                    for key in (
                        "shadow_count",
                        "canonical_count",
                        "matched_count",
                        "shadow_precision",
                        "canonical_recall",
                        "human_review_status",
                        "promotion_eligible",
                    )
                },
            }
        )
        return outcome

    try:
        from smc_desk.perception.market_state_memory import record_run_transition

        market_state = pack.get("market_state") if isinstance(pack, dict) else None
        if isinstance(market_state, dict) and market_state:
            stage_dir.mkdir(parents=True, exist_ok=True)
            record = record_run_transition(
                output_root=output_root,
                symbol=symbol,
                current_market_state=market_state,
                market_identity=market_identity,
                evidence_fingerprint=evidence_fingerprint,
            )
            (stage_dir / "market_state_transition.json").write_text(
                json.dumps(record, indent=2, sort_keys=True, default=str), encoding="utf-8"
            )
            outcome["memory_status"] = str(record.get("store_status") or "recorded_unknown")
            outcome["memory_store_updated"] = bool(record.get("store_updated"))
            outcome["memory_forward_transition"] = bool(record.get("forward_transition"))
            outcome["transition_notes"] = _dedupe_notes(
                [
                    *(record.get("notes") or []),
                    *(record.get("transition", {}).get("notes") or []),
                ]
            )
        else:
            outcome["memory_status"] = "no_market_state_in_pack"
    except Exception as exc:  # noqa: BLE001 -- additive evidence, never fatal
        outcome["memory_status"] = f"failed:{type(exc).__name__}"

    try:
        from smc_desk.brain.narrative_annotation_planner import plan_narrative_annotations

        plan = plan_narrative_annotations(evidence_pack=pack)
        canonical_plan_path = symbol_root / "14_clean_annotation_render" / "annotation_plan_v2.json"
        official_decision_path = symbol_root / "13_official_ai_decision" / "official_decision.json"
        canonical_plan = _read_json_mapping(canonical_plan_path)
        official_decision = _read_json_mapping(official_decision_path)
        comparison = _compare_shadow_to_canonical(
            shadow_plan=plan,
            canonical_plan=canonical_plan,
            evidence_pack=pack,
            official_decision=official_decision,
        )
        shadow = {
            "schema": "narrative_annotation_plan_shadow_v2",
            "shadow_comparison_only": True,
            "rendered": False,
            "canonical_annotation_plan": "14_clean_annotation_render/annotation_plan_v2.json",
            "provenance": {
                "evidence_pack": str(pack_path) if pack_path is not None else None,
                "evidence_pack_sha256": evidence_fingerprint,
                "canonical_annotation_plan_sha256": _file_sha256(canonical_plan_path),
                "official_decision_sha256": _file_sha256(official_decision_path),
                "planner_source_sha256": _file_sha256(
                    REPO_ROOT / "smc_desk" / "brain" / "narrative_annotation_planner.py"
                ),
                "decision_time": (pack.get("market_state") or {}).get("decision_time"),
                "market_identity": market_identity,
            },
            "purpose": (
                "Recorded so the analyst-marked development cohort (WP-SMC-13) can "
                "measure the narrative planner against the canonical composer before "
                "any selector is promoted or retired."
            ),
            "plan": plan,
            "comparison": comparison,
            "authority": "observe_only_shadow_comparison",
            "signal_allowed": False,
        }
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "narrative_annotation_plan_shadow.json").write_text(
            json.dumps(shadow, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        outcome["shadow_status"] = "recorded"
        outcome["shadow_comparison_status"] = comparison["status"]
        outcome["shadow_comparison_metrics"] = {
            "shadow_count": comparison["shadow_count"],
            "canonical_count": comparison["canonical_count"],
            "matched_count": comparison["matched_count"],
            "shadow_precision": comparison["shadow_precision"],
            "canonical_recall": comparison["canonical_recall"],
            "human_review_status": comparison["human_review_status"],
            "promotion_eligible": comparison["promotion_eligible"],
        }
    except Exception as exc:  # noqa: BLE001 -- additive evidence, never fatal
        outcome["shadow_status"] = f"failed:{type(exc).__name__}"
    return outcome


def _market_identity_from_pack(pack: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Extract stable provider identity without dynamic timestamps or row counts."""
    from smc_desk.perception.market_state_memory import normalize_market_identity

    session = pack.get("session_context") if isinstance(pack, dict) else {}
    manifest = session.get("source_manifest") if isinstance(session, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    timeframe_manifest = manifest.get("timeframes")
    timeframe_profile = (
        list(timeframe_manifest)
        if isinstance(timeframe_manifest, dict)
        else list((pack.get("ohlcv_windows") or {}).keys())
    )
    return normalize_market_identity(
        symbol,
        {
            "canonical_symbol": symbol,
            "source": manifest.get("source"),
            "provider_symbol": manifest.get("provider_symbol") or manifest.get("symbol") or symbol,
            "market_type": manifest.get("market_type"),
            "timeframe_profile": timeframe_profile,
        },
    )


def _compare_shadow_to_canonical(
    *,
    shadow_plan: dict[str, Any],
    canonical_plan: dict[str, Any] | None,
    evidence_pack: dict[str, Any],
    official_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create the missing measurable, non-promotional planner comparison."""
    selections = [
        item for item in (shadow_plan.get("selections") or []) if isinstance(item, dict)
    ]
    canonical_objects = [
        item
        for item in ((canonical_plan or {}).get("objects") or [])
        if isinstance(item, dict)
    ]
    unmatched_canonical = set(range(len(canonical_objects)))
    matched: list[dict[str, Any]] = []
    shadow_only: list[dict[str, Any]] = []

    for selection in selections:
        shadow_id = str(selection.get("semantic_object_id") or "")
        match_index = next(
            (
                index
                for index in sorted(unmatched_canonical)
                if shadow_id in _canonical_evidence_ids(canonical_objects[index])
                and selection.get("object_type") == canonical_objects[index].get("object_type")
                and selection.get("timeframe") == canonical_objects[index].get("timeframe")
            ),
            None,
        )
        if match_index is None:
            shadow_only.append(_compact_shadow_selection(selection))
            continue
        unmatched_canonical.remove(match_index)
        matched.append(
            {
                "evidence_object_id": shadow_id,
                "object_type": selection.get("object_type"),
                "timeframe": selection.get("timeframe"),
                "canonical_semantic_object_id": canonical_objects[match_index].get(
                    "semantic_object_id"
                ),
            }
        )

    canonical_only = [
        {
            "semantic_object_id": canonical_objects[index].get("semantic_object_id"),
            "evidence_object_ids": sorted(_canonical_evidence_ids(canonical_objects[index])),
            "object_type": canonical_objects[index].get("object_type"),
            "timeframe": canonical_objects[index].get("timeframe"),
        }
        for index in sorted(unmatched_canonical)
    ]
    market_state = evidence_pack.get("market_state")
    market_state = market_state if isinstance(market_state, dict) else {}
    reasons = [str(item).lower() for item in (market_state.get("reasons") or [])]
    context = market_state.get("context") if isinstance(market_state.get("context"), dict) else {}
    reconciliation_required = (
        str(context.get("narrative_state") or "") == "RECONCILIATION_REQUIRED"
        or any("reconciliation" in reason for reason in reasons)
    )
    status = (
        "CANONICAL_PLAN_UNAVAILABLE"
        if canonical_plan is None
        else "RECONCILIATION_CONFLICT_REVIEW_REQUIRED"
        if reconciliation_required and selections
        else "SHADOW_COMPARISON_RECORDED"
    )
    matched_count = len(matched)
    return {
        "schema": "narrative_shadow_comparison_v1",
        "status": status,
        "shadow_count": len(selections),
        "canonical_count": len(canonical_objects),
        "matched_count": matched_count,
        "shadow_precision": matched_count / len(selections) if selections else None,
        "canonical_recall": matched_count / len(canonical_objects) if canonical_objects else None,
        "matched": matched,
        "shadow_only": shadow_only,
        "canonical_only": canonical_only,
        "official_state": (official_decision or {}).get("official_state"),
        "market_state": market_state.get("state"),
        "market_narrative_state": context.get("narrative_state"),
        "reconciliation_required": reconciliation_required,
        "human_review_status": "NOT_SCORED",
        "human_cohort_score_required": True,
        "promotion_eligible": False,
        "authority": "observe_only_measurement",
        "signal_allowed": False,
    }


def _canonical_evidence_ids(obj: dict[str, Any]) -> set[str]:
    ids = {str(item) for item in (obj.get("evidence_object_ids") or []) if item}
    geometry = obj.get("evidence_geometry")
    if isinstance(geometry, dict):
        ids.update(str(item) for item in (geometry.get("source_object_ids") or []) if item)
    semantic = str(obj.get("semantic_object_id") or "")
    if semantic:
        ids.add(semantic)
        ids.add(semantic.rsplit(":", 1)[0])
    return ids


def _compact_shadow_selection(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "semantic_object_id": selection.get("semantic_object_id"),
        "object_type": selection.get("object_type"),
        "timeframe": selection.get("timeframe"),
        "label": selection.get("label"),
    }


def _read_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _file_sha256(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dedupe_notes(notes: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(note) for note in notes if note))


def normalize_symbol(symbol: str) -> str:
    upper = symbol.upper().replace("/", "").replace("-", "")
    if upper in {"XAU", "XAUUSD", "GCF"}:
        return "XAUUSD"
    return upper


def load_live_timeframes(symbol: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    normalized = normalize_symbol(symbol)
    if normalized.endswith("USDT") and normalized != "XAUUSDT":
        return load_binance_usdm_timeframes(normalized)
    if normalized == "XAUUSD":
        return load_yahoo_xau_timeframes()
    if is_forex_pair(normalized):
        return load_yahoo_forex_timeframes(normalized)
    raise ValueError(f"Unsupported live symbol route: {symbol}")


def is_forex_pair(symbol: str) -> bool:
    currencies = {"AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"}
    return len(symbol) == 6 and symbol[:3] in currencies and symbol[3:] in currencies


def load_binance_usdm_timeframes(symbol: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    audit_start = len(DNS_FALLBACK_AUDIT)
    specs = {"15m": 1500, "1h": 1000, "4h": 500, "1d": 365}
    frames: dict[str, pd.DataFrame] = {}
    manifests: dict[str, Any] = {}
    for interval, limit in specs.items():
        result = fetch_historical_closed_ohlcv(
            symbol=symbol,
            interval=interval,
            required_candles=limit,
            fetcher=binance_page_fetcher,
        )
        df = result.dataframe
        frames[interval] = df
        manifests[interval] = {
            "provider": "binance_usdm_rest",
            "row_count": len(df),
            "page_count": result.manifest["page_count"],
            "server_time_ms": result.manifest["server_time_ms"],
            "last_timestamp": str(df["timestamp"].iloc[-1]),
            "last_open_time": str(df["timestamp"].iloc[-1]),
            "last_close_time": str(df["timestamp"].iloc[-1] + TIMEFRAME_DELTAS[interval]),
        }
    fallback_events = [dict(item) for item in DNS_FALLBACK_AUDIT[audit_start:]]
    return frames, {
        "symbol": symbol,
        "source": "binance_usdm_rest",
        "market_type": "USD-M perpetual futures",
        "timeframes": manifests,
        "network_transport": {
            "default_system_dns_succeeded": not fallback_events,
            "public_dns_fallback_used": bool(fallback_events),
            "fallback_events": fallback_events,
            "tls_certificate_verification": "required",
        },
    }


def binance_page_fetcher(symbol: str, interval: str, limit: int, end_time_ms: int | None) -> tuple[list[Any], int]:
    params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": min(limit, 1500)}
    if end_time_ms is not None:
        params["endTime"] = end_time_ms
    rows = http_get_json(f"{BINANCE_BASE}/fapi/v1/klines", params)
    server_time = int(http_get_json(f"{BINANCE_BASE}/fapi/v1/time", {})["serverTime"])
    return rows, server_time


def load_yahoo_xau_timeframes() -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    ticker = "GC=F"
    fifteen = yahoo_chart_df(ticker, interval="15m", range_="60d")
    one_hour = yahoo_chart_df(ticker, interval="1h", range_="730d")
    one_day = yahoo_chart_df(ticker, interval="1d", range_="2y")
    source_cutoff = pd.Timestamp(one_hour["timestamp"].iloc[-1]) + TIMEFRAME_DELTAS["1h"]
    four_hour = resample_ohlcv(one_hour, "4h", decision_time=source_cutoff)
    frames = {"15m": fifteen, "1h": one_hour, "4h": four_hour, "1d": one_day}
    manifest = {
        "symbol": "XAUUSD",
        "source": "yahoo_chart",
        "provider_symbol": ticker,
        "market_type": "COMEX gold futures proxy",
        "proxy_note": "This observe-only live harness uses GC=F COMEX gold futures as an explicit XAUUSD proxy; it is not an XAUUSD spot feed.",
        "timeframes": {tf: {"row_count": len(df), "last_timestamp": str(df["timestamp"].iloc[-1])} for tf, df in frames.items()},
    }
    return frames, manifest


def load_yahoo_forex_timeframes(symbol: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    ticker = f"{symbol}=X"
    fifteen = yahoo_chart_df(ticker, interval="15m", range_="60d")
    one_hour = yahoo_chart_df(ticker, interval="1h", range_="730d")
    source_cutoff = pd.Timestamp(one_hour["timestamp"].iloc[-1]) + TIMEFRAME_DELTAS["1h"]
    four_hour = resample_ohlcv(one_hour, "4h", decision_time=source_cutoff)
    # Yahoo's standalone FX daily series can contain small but impossible
    # envelope inconsistencies (open/close outside its reported high/low).
    # Build the daily chart from the same closed hourly observations instead,
    # using the explicit New York 17:00 session boundary expected by FX desks.
    # This preserves source identity and OHLC geometry without silently
    # clipping or inventing any provider price.
    one_day = reconstruct_timeframe_ohlcv(
        one_hour,
        "1d",
        source_cutoff,
        daily_session_profile="new_york_close_daily",
    )[["timestamp", "open", "high", "low", "close", "volume"]]
    one_day["timestamp"] = pd.to_datetime(one_day["timestamp"], utc=True)
    frames = {"15m": fifteen, "1h": one_hour, "4h": four_hour, "1d": one_day}
    manifest = {
        "symbol": symbol,
        "source": "yahoo_chart",
        "provider_symbol": ticker,
        "market_type": "forex_spot_chart_proxy",
        "daily_session_profile": "new_york_close_daily",
        "timeframes": {
            tf: {
                "row_count": len(df),
                "last_timestamp": str(df["timestamp"].iloc[-1]),
                **(
                    {
                        "derived_from": "yahoo_chart_1h",
                        "derivation": "closed_hourly_ohlcv_resample",
                        "session_boundary": "America/New_York 17:00",
                    }
                    if tf == "1d"
                    else {}
                ),
            }
            for tf, df in frames.items()
        },
    }
    return frames, manifest


def http_get_json(url: str, params: dict[str, Any], timeout: float = 20.0) -> Any:
    try:
        response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "smc-codex-desk-live-system-test/1.0"})
        response.raise_for_status()
        return response.json()
    except requests.ConnectionError as exc:
        if not _is_name_resolution_error(exc):
            raise
        return _http_get_json_via_public_dns(url, params, timeout=timeout, original_error=exc)


def _is_name_resolution_error(exc: BaseException) -> bool:
    text = repr(exc).lower()
    return any(
        marker in text
        for marker in (
            "nameresolutionerror",
            "failed to resolve",
            "name or service not known",
            "nodename nor servname provided",
        )
    )


def _resolve_public_ipv4(hostname: str) -> tuple[str, list[str]]:
    """Resolve an approved market-data host without changing macOS DNS state."""
    if hostname not in APPROVED_PUBLIC_DATA_HOSTS:
        raise RuntimeError(f"Public DNS fallback is not approved for host: {hostname}")
    failures: list[str] = []
    for resolver in ("1.1.1.1", "8.8.8.8"):
        try:
            result = subprocess.run(
                ["dig", "+short", "+timeout=3", "+tries=1", f"@{resolver}", hostname, "A"],
                capture_output=True,
                text=True,
                check=False,
                timeout=6,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{resolver}:{type(exc).__name__}")
            continue
        addresses: list[str] = []
        for raw_line in result.stdout.splitlines():
            candidate = raw_line.strip().rstrip(".")
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if isinstance(address, ipaddress.IPv4Address):
                addresses.append(str(address))
        if addresses:
            return resolver, list(dict.fromkeys(addresses))
        failures.append(f"{resolver}:no_ipv4_answer")
    raise requests.ConnectionError(
        f"Approved public resolvers could not resolve {hostname}: {failures}"
    )


def _http_get_json_via_public_dns(
    url: str,
    params: dict[str, Any],
    *,
    timeout: float,
    original_error: BaseException,
) -> Any:
    """Use curl's --resolve so HTTPS SNI and certificate checks stay intact."""
    parsed = urlparse(url)
    hostname = str(parsed.hostname or "")
    if parsed.scheme != "https" or hostname not in APPROVED_PUBLIC_DATA_HOSTS:
        raise original_error
    resolver, addresses = _resolve_public_ipv4(hostname)
    failures: list[str] = []
    for address in addresses:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--get",
            "--proto",
            "=https",
            "--connect-timeout",
            "5",
            "--max-time",
            str(max(1, int(timeout))),
            "--resolve",
            f"{hostname}:443:{address}",
            "--header",
            "User-Agent: smc-codex-desk-live-system-test/1.0",
            url,
        ]
        for key, value in sorted(params.items()):
            command.extend(["--data-urlencode", f"{key}={value}"])
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=max(6, int(timeout) + 5),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{address}:{type(exc).__name__}")
            continue
        if result.returncode != 0:
            failures.append(f"{address}:curl_exit_{result.returncode}")
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            failures.append(f"{address}:invalid_json")
            continue
        DNS_FALLBACK_AUDIT.append(
            {
                "route": "public_dns_curl_resolve",
                "hostname": hostname,
                "resolver": resolver,
                "resolved_ip": address,
                "url_path": parsed.path,
                "tls_hostname_verification": True,
            }
        )
        return payload
    raise requests.ConnectionError(
        f"DNS fallback could not reach {hostname} with verified HTTPS: {failures}"
    ) from original_error


def binance_rows_to_df(rows: list[list[Any]], *, server_time_ms: int) -> pd.DataFrame:
    parsed = []
    for row in rows:
        close_ms = int(row[6])
        if close_ms > server_time_ms:
            continue
        parsed.append(
            {
                "timestamp": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )
    return pd.DataFrame(parsed).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def yahoo_chart_df(ticker: str, *, interval: str, range_: str) -> pd.DataFrame:
    url = f"{YAHOO_BASE}/{ticker}"
    payload = http_get_json(url, {"interval": interval, "range": range_})
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no chart result for {ticker} {interval} {range_}")
    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        }
    )
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    if interval == "1d":
        # Yahoo can append the final FX daily candle at regularMarketTime
        # instead of the exchange-local session boundary, duplicating the
        # same local trading date. Canonicalize by exchange session date and
        # retain the final (complete) record for that date.
        exchange_tz = str(result.get("meta", {}).get("exchangeTimezoneName") or "UTC")
        local_session = df["timestamp"].dt.tz_convert(exchange_tz).dt.normalize()
        df["_session_date"] = local_session.dt.date
        df["timestamp"] = local_session.dt.tz_convert("UTC")
        df = df.drop_duplicates("_session_date", keep="last").drop(columns=["_session_date"])
    minutes = interval_to_minutes(interval)
    now = pd.Timestamp.now(tz="UTC")
    df = df[df["timestamp"] + pd.to_timedelta(minutes, unit="min") <= now]
    return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def interval_to_minutes(interval: str) -> int:
    if interval.endswith("m"):
        return int(interval[:-1])
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    if interval.endswith("d"):
        return int(interval[:-1]) * 1440
    return 1


def resample_ohlcv(
    df: pd.DataFrame,
    rule: str,
    *,
    decision_time: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Aggregate OHLCV and exclude any target bucket still forming at cutoff."""
    indexed = df.set_index("timestamp").sort_index()
    out = indexed.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index()
    if decision_time is None:
        return out

    cutoff = pd.Timestamp(decision_time)
    timestamps = pd.to_datetime(out["timestamp"])
    if timestamps.dt.tz is not None and cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    elif timestamps.dt.tz is None and cutoff.tzinfo is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    duration = pd.to_timedelta(rule)
    return out.loc[timestamps + duration <= cutoff].reset_index(drop=True)


def build_basic_detector_candidates(timeframe_dfs: dict[str, pd.DataFrame], symbol: str) -> dict[str, Any]:
    candidates: dict[str, Any] = {}
    for tf, df in timeframe_dfs.items():
        tail = df.tail(120)
        high_idx = tail["high"].idxmax()
        low_idx = tail["low"].idxmin()
        high = float(df.loc[high_idx, "high"])
        low = float(df.loc[low_idx, "low"])
        candidates[tf] = {
            "liquidity_levels": [
                {
                    "object_id": f"{symbol}:{tf}:recent_high_liquidity",
                    "timeframe": tf,
                    "side": "buy_side",
                    "price": high,
                    "label": "recent range high liquidity",
                },
                {
                    "object_id": f"{symbol}:{tf}:recent_low_liquidity",
                    "timeframe": tf,
                    "side": "sell_side",
                    "price": low,
                    "label": "recent range low liquidity",
                },
            ],
            "sweeps": [],
            "structure_breaks": [],
            "fvgs": [],
            "order_blocks": [],
        }
    return candidates


def build_conservative_ai_payload(request: LLMCompletionRequest, source_manifest: dict[str, Any]) -> dict[str, Any]:
    pack = request.evidence_pack
    symbol = str(pack.get("symbol"))
    summaries = pack["ohlcv_summaries"]
    range_authority = pack.get("active_range_authority") or {}
    selected_range = range_authority.get("selected_range") if isinstance(range_authority, dict) else None
    raw_tf_bias = {tf: timeframe_bias(summary) for tf, summary in summaries.items()}
    structure_narrative = pack.get("structure_narrative")
    if not isinstance(structure_narrative, dict):
        structure_narrative = build_structure_narrative(
            pack.get("detector_candidates", {}) or {},
            raw_bias=raw_tf_bias,
        )
    tf_bias = _display_bias_labels(raw_tf_bias, structure_narrative)
    vote_bias = _vote_bias_labels(raw_tf_bias, structure_narrative)
    direction = derive_strict_htf_bias(
        vote_bias,
        fallback_bias=_formal_graph_aware_fallback_bias(raw_tf_bias, structure_narrative),
    )
    parent_child_context = structure_narrative.get("parent_child_context") if isinstance(structure_narrative, dict) else {}
    if not isinstance(parent_child_context, dict):
        parent_child_context = {}
    parent_child_conflict = bool(parent_child_context.get("has_parent_child_conflict"))
    parent_child_sentence = str(parent_child_context.get("thesis_sentence") or "").strip()
    if parent_child_conflict:
        direction = "mixed"
    htf_direction = direction
    causal_episode_graph = pack.get("formal_causal_episode_graph") or {}
    causal_episode_invariants = causal_episode_graph.get("invariants") if isinstance(causal_episode_graph, dict) else {}
    causal_episode_graph_present = isinstance(causal_episode_graph, dict) and causal_episode_graph.get("schema") == "formal_causal_episode_graph_v2"
    causal_episode_requires_review = bool(
        causal_episode_graph_present
        and (
            not isinstance(causal_episode_invariants, dict)
            or causal_episode_invariants.get("status") != "PASS"
        )
    )
    causal_story = causal_episode_graph.get("current_story") if isinstance(causal_episode_graph, dict) else {}
    if not isinstance(causal_story, dict):
        causal_story = {}
    if isinstance(causal_story, dict) and causal_story.get("status") == "MIXED_CONTEXT":
        direction = "mixed"

    fresh_v3_external = _fresh_v3_external_event(pack, timeframe="15m", maximum_age_bars=32)
    if fresh_v3_external is not None:
        displacement_score = float(fresh_v3_external.get("displacement_score") or 0.0)
        displacement_quality = "strong" if displacement_score >= 0.75 else "clean"
        displacement_payload = {
            "direction": str(fresh_v3_external.get("direction")),
            "quality": displacement_quality,
            "structure_broken": True,
            "evidence_object_ids": [str(fresh_v3_external.get("source_break_object_id"))],
            "summary": (
                f"V3 accepted the fresh 15m {fresh_v3_external.get('event_type')} at "
                f"{fresh_v3_external.get('confirmation_time')}; it remains structure evidence only "
                "until higher-timeframe reconciliation, causal POI, and entry confirmation all pass."
            ),
        }
    else:
        displacement_payload = {
            "direction": "none",
            "quality": "none",
            "structure_broken": False,
            "evidence_object_ids": [],
            "summary": "No fresh V3-accepted 15m displacement is available for this observe-only test run.",
        }

    if isinstance(selected_range, dict) and selected_range.get("status") == "RESOLVED_ACTIVE_RANGE":
        active_tf = str(selected_range["timeframe"])
        high = float(selected_range["range_high"])
        low = float(selected_range["range_low"])
        mid = float(selected_range["equilibrium"])
        price_location = str(selected_range["price_location"])
        range_direction = str(selected_range.get("direction", ""))
        official_state = "WATCH_ONLY" if direction in {"bullish", "bearish"} else "THESIS_ONLY"
        active_range_payload = {
            "timeframe": active_tf,
            "high": high,
            "low": low,
            "equilibrium": mid,
            "price_location": price_location,
            "source": "protected_swing_pair",
            "range_id": selected_range.get("range_id"),
            "protected_high": float(selected_range["protected_high"]),
            "protected_low": float(selected_range["protected_low"]),
            "width_atr": float(selected_range["width_atr"]),
            "max_allowed_width_atr": float(selected_range["max_width_atr"]),
            "evidence_object_ids": [
                str(selected_range.get("protected_high_pivot_id")),
                str(selected_range.get("protected_low_pivot_id")),
            ],
            "evidence": list(selected_range.get("authority_notes") or []),
        }
    else:
        active_tf = "1h" if "1h" in summaries else next(iter(summaries))
        high = low = mid = None
        price_location = "unknown"
        official_state = "REVIEW_REQUIRED"
        active_range_payload = {
            "timeframe": active_tf,
            "high": None,
            "low": None,
            "equilibrium": None,
            "price_location": "unknown",
            "source": "active_range_authority",
            "range_id": None,
            "protected_high": None,
            "protected_low": None,
            "width_atr": None,
            "max_allowed_width_atr": None,
            "evidence_object_ids": [],
            "evidence": ["Active range authority could not certify a protected swing pair."],
        }
    if causal_episode_requires_review:
        official_state = "REVIEW_REQUIRED"
        # A stricter enforcement-ready causal replay disagreement invalidates
        # promotion of the provisional V1 vote into an official direction.
        # Keep the original HTF vote in evidence, but expose mixed/unresolved
        # decision authority until reconciliation succeeds.
        direction = "mixed"

    target_side = "sell_side" if direction == "bearish" else "buy_side" if direction == "bullish" else "unknown"
    target_price = low if direction == "bearish" and low is not None else high if direction == "bullish" and high is not None else None
    invalidation_price = high if direction == "bearish" and high is not None else low if direction == "bullish" and low is not None else None
    labels = [
        {
            "text": _short_parent_child_label(parent_child_context) if parent_child_conflict else f"HTF bias {direction}",
            "kind": "context",
            "timeframe": str(parent_child_context.get("parent_timeframe") or "1h") if parent_child_conflict else "1h",
        },
        {
            "text": f"{active_tf} structural range {format_price(low)}-{format_price(high)}"
            if low is not None and high is not None
            else "Active range unresolved",
            "kind": "liquidity" if low is not None and high is not None else "state",
            "timeframe": active_tf,
        },
        {
            "text": (
                f"15m {fresh_v3_external.get('event_type')} accepted · not promoted"
                if fresh_v3_external is not None
                else "No fresh V3 15m displacement accepted"
            ),
            "kind": "structure" if fresh_v3_external is not None else "state",
            "timeframe": "15m",
        },
        {"text": "Watch only - wait for real POI confirmation", "kind": "state"},
    ]
    levels = []
    if target_price is not None:
        levels.append({"label": f"{target_side} liquidity watch", "kind": "liquidity", "price": target_price, "timeframe": active_tf})
    if invalidation_price is not None:
        levels.append({"label": "watch invalidation, not SL", "kind": "invalidation", "price": invalidation_price, "timeframe": active_tf})
    from smc_desk.brain.annotation_candidate_composer import compose_local_annotation_plan_v2, select_local_active_poi

    active_poi_payload = select_local_active_poi(
        evidence_pack=pack,
        direction=direction,
        active_range=active_range_payload,
    )
    has_active_poi = active_poi_payload is not None
    range_conflict = bool(
        isinstance(selected_range, dict)
        and selected_range.get("status") == "RESOLVED_ACTIVE_RANGE"
        and range_direction in {"bullish", "bearish"}
        and direction in {"bullish", "bearish"}
        and range_direction != direction
    )

    annotation_plan_v2 = compose_local_annotation_plan_v2(
        evidence_pack=pack,
        official_state=official_state,
        direction=direction,
        active_range=active_range_payload,
        active_poi=active_poi_payload,
    )
    base_liquidity_narrative = (
        f"{parent_child_sentence} This is a context conflict, so no clean direction is promoted into a trade plan."
        if parent_child_conflict and parent_child_sentence
        else (
            "A confirmed active POI is mapped for observation, but no validated sweep/displacement/entry confirmation is promoted into a trade plan."
            if has_active_poi
            else (
                f"{_source_mode_subject(source_manifest)} sees context and range liquidity plus a fresh V3-accepted 15m displacement, "
                "but no validated sweep/causal POI/entry sequence is promoted into a trade plan."
                if fresh_v3_external is not None
                else f"{_source_mode_subject(source_manifest)} sees context and range liquidity, but no validated sweep/displacement/POI is promoted into a trade plan."
            )
        )
    )
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": symbol,
        "official_state": official_state,
        "setup_grade": "C" if official_state == "WATCH_ONLY" else "THESIS_ONLY",
        "direction": direction if direction in {"bullish", "bearish"} else "mixed",
        "setup_model": "observe_only_context_watch",
        "bias_summary": {
            "daily": tf_bias.get("1d", "unknown"),
            "4h": tf_bias.get("4h", "unknown"),
            "1h": tf_bias.get("1h", "unknown"),
            "final_bias": direction if direction in {"bullish", "bearish"} else "mixed",
            "evidence": [
                *[f"{tf}: {bias}" for tf, bias in sorted(tf_bias.items())],
                *list(structure_narrative.get("evidence", []) or []),
                *list(parent_child_context.get("evidence", []) or []),
                str((causal_story or {}).get("summary") or "Causal episode story unavailable."),
                f"causal_episode_graph_invariants: {(causal_episode_invariants or {}).get('status', 'REVIEW_REQUIRED')}",
                (
                    f"active_range_direction: {range_direction} (map only; HTF consensus {htf_direction})"
                    if isinstance(selected_range, dict) and selected_range.get("status") == "RESOLVED_ACTIVE_RANGE"
                    else "active_range_direction: unresolved"
                ),
            ],
        },
        "active_range": active_range_payload,
        "liquidity_story": {
            "obvious_liquidity": [
                {"timeframe": active_tf, "side": "buy_side", "price": high, "label": "active range high"},
                {"timeframe": active_tf, "side": "sell_side", "price": low, "label": "active range low"},
            ],
            "swept_liquidity": [],
            "unswept_liquidity": [
                {"timeframe": active_tf, "side": target_side, "price": target_price, "label": "possible model-completion draw"}
            ]
            if target_price is not None
            else [],
            "narrative": _with_narrative_draw(base_liquidity_narrative, pack),
        },
        "displacement_assessment": displacement_payload,
        "active_poi": active_poi_payload or {
            "poi_id": None,
            "timeframe": None,
            "kind": None,
            "direction": "unknown",
            "price_low": None,
            "price_high": None,
            "freshness": None,
            "evidence_object_ids": [],
            "summary": "No validated active POI. Wait for clean retrace/rejection before trade readiness.",
        },
        "entry_plan": {
            "entry_ready": False,
            "entry_timeframe": "15m",
            "refinement_timeframe": "5m",
            "entry_price": None,
            "entry_zone_low": None,
            "entry_zone_high": None,
            "signal_type": None,
            "required_confirmation": ["validated sweep/displacement/POI", "15m rejection or continuation confirmation"],
            "evidence_object_ids": [],
            "summary": "No entry: the run is watch/thesis only.",
        },
        "stop_loss_plan": {
            "stop_price": None,
            "structural_invalidation_price": None,
            "source": None,
            "buffer_notes": None,
            "evidence_object_ids": [],
            "summary": "No stop loss because there is no trade plan.",
        },
        "target_plan": {
            "targets": [],
            "model_completion_liquidity_id": None,
            "summary": "No executable target because there is no trade-ready entry.",
        },
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "RR not evaluated because this is not TRADE_PLAN_READY."},
        "invalidation": {
            "invalidation_price": invalidation_price,
            "condition": "Watch invalidation only; not an executable stop loss.",
            "source": f"{active_tf}_range_extreme" if invalidation_price is not None else None,
            "evidence_object_ids": [],
        },
        "annotation_plan": {
            "chart_template": "watch_chart" if official_state == "WATCH_ONLY" else "context_chart",
            "show_trade_box": False,
            "labels": labels[:7],
            "levels": levels,
            "reasoning_order": REASONING_ORDER,
        },
        "annotation_plan_v2": annotation_plan_v2,
        "self_review": {
            "active_range_check": "passed" if selected_range else "failed",
            "poi_check": "passed" if has_active_poi else "not_applicable",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [
                (
                    "Kept the confirmed active POI as watch evidence only because sweep/displacement/entry confirmation were not validated."
                    if has_active_poi
                    else (
                        "Recognized the fresh V3-accepted 15m displacement but refused execution because the sweep/causal POI/entry sequence was not validated."
                        if fresh_v3_external is not None
                        else "Refused executable trade because sweep/displacement/active POI were not validated."
                    )
                ),
                "Used structural active range authority instead of OHLCV summary extremes.",
                "Reconciled raw OHLC summary bias with confirmed structure narrative.",
                *(
                    ["Kept the directional thesis conditional because the active-range direction opposes HTF consensus."]
                    if range_conflict
                    else []
                ),
                *(
                    ["Downgraded to mixed/THESIS_ONLY because parent and child context timeframes conflict."]
                    if parent_child_conflict
                    else []
                ),
            ]
            if selected_range
            else ["Downgraded to review because active range authority was unresolved."],
            "remaining_uncertainties": [
                (
                    "The mapped active POI has not produced validated entry confirmation."
                    if has_active_poi
                    else "No validated active POI promoted into trade readiness."
                ),
                (
                    "A fresh V3 displacement exists, but no complete sweep/causal POI/entry sequence is authorized for execution."
                    if fresh_v3_external is not None
                    else "No confirmed sweep/displacement sequence promoted into execution."
                ),
            ],
        },
        "final_thesis": (
            (
                f"{symbol}: {official_state}. {parent_child_sentence} "
                "This is not clean bullish or clean bearish; the system refuses a trade plan until one side confirms."
            )
            if parent_child_conflict and parent_child_sentence
            else (
                f"{symbol}: {official_state}. Directional context is {direction}"
                + (
                    f", while the certified active-range map remains {range_direction}"
                    if range_conflict
                    else ""
                )
                + (
                    ". A confirmed active POI is mapped, but sweep/displacement/entry confirmation is absent, so it remains watch evidence and no trade plan is allowed."
                    if has_active_poi
                    else (
                        f". A fresh V3-accepted 15m {fresh_v3_external.get('event_type')} exists, but no validated sweep/causal POI/entry sequence exists, so it refuses a trade plan."
                        if fresh_v3_external is not None
                        else ". The system does not have validated sweep/displacement/active POI/entry evidence, so it refuses a trade plan."
                    )
                )
            )
        ),
    }


def _narrative_draw_note(pack: dict[str, Any]) -> str:
    """Name the standing liquidity draw when the hierarchical narrative read found one.

    Descriptive only: the draw is the nearest unswept pool in the direction of
    the narrative bias, computed by ``narrative_hierarchy``. It is not a
    validated sweep, not a POI, and not a target -- but a liquidity story that
    never names the draw is a story with its central fact removed.
    """
    graph = pack.get("formal_structure_graph") if isinstance(pack, dict) else {}
    narrative = graph.get("narrative_context") if isinstance(graph, dict) else {}
    draw = narrative.get("draw") if isinstance(narrative, dict) else {}
    if not isinstance(draw, dict):
        return ""
    try:
        price = float(draw.get("target_price"))
    except (TypeError, ValueError):
        return ""
    direction = str(draw.get("direction") or "")
    if direction not in {"bullish", "bearish"}:
        return ""
    kind = str(draw.get("target_kind") or "liquidity").replace("_", " ")
    return (
        f" The hierarchical read names the standing draw: {direction} toward "
        f"{kind} at {format_price(price)} -- descriptive and unpromoted, not a "
        "validated sweep target."
    )


def _fresh_v3_external_event(
    pack: dict[str, Any],
    *,
    timeframe: str,
    maximum_age_bars: int,
) -> dict[str, Any] | None:
    """Return recent accepted structure evidence without promoting a trade.

    The age bound is an explanation/display contract, not a profitability
    threshold: stale accepted history still remains in the graph, but it is
    not described as a fresh execution-timeframe displacement.
    """
    shadow = pack.get("structure_engine_v3_shadow") if isinstance(pack, dict) else None
    timeframe_node = shadow.get("timeframes", {}).get(timeframe) if isinstance(shadow, dict) else None
    event = timeframe_node.get("latest_accepted_external") if isinstance(timeframe_node, dict) else None
    if not isinstance(event, dict) or event.get("accepted_for_shadow_story") is not True:
        return None
    event_time_raw = event.get("confirmation_time") or event.get("body_close_time")
    decision_time_raw = shadow.get("decision_time") if isinstance(shadow, dict) else None
    if not event_time_raw or not decision_time_raw:
        return None
    bar_duration = TIMEFRAME_DELTAS.get(timeframe)
    if bar_duration is None:
        return None
    event_time = pd.Timestamp(event_time_raw)
    decision_time = pd.Timestamp(decision_time_raw)
    if event_time.tzinfo is None:
        event_time = event_time.tz_localize("UTC")
    if decision_time.tzinfo is None:
        decision_time = decision_time.tz_localize("UTC")
    age = decision_time - event_time
    if age < pd.Timedelta(0) or age > bar_duration * maximum_age_bars:
        return None
    if str(event.get("direction") or "") not in {"bullish", "bearish"}:
        return None
    if not event.get("source_break_object_id"):
        return None
    return dict(event)


def _with_narrative_draw(base_narrative: str, pack: dict[str, Any]) -> str:
    """Append the descriptive draw in every thesis branch, including active POIs."""
    return f"{base_narrative}{_narrative_draw_note(pack)}"


def _perception_failures(pack: dict[str, Any]) -> list[str]:
    """Name any timeframe whose canonical perception failed closed.

    A bare chart must never read as "nothing here" when the truth is "not
    analysed". These failures already exist inside the pack's perception
    report; surfacing them keeps fail-closed honest instead of silent.
    """
    session_context = pack.get("session_context") if isinstance(pack, dict) else {}
    report = session_context.get("perception_candidates") if isinstance(session_context, dict) else {}
    timeframes = report.get("timeframes") if isinstance(report, dict) else {}
    failures: list[str] = []
    for timeframe in ("15m", "1h", "4h", "1d"):
        node = timeframes.get(timeframe) if isinstance(timeframes, dict) else None
        if isinstance(node, dict) and node.get("status") == "FAILED":
            failures.append(f"{timeframe}: {node.get('error_type')} - {node.get('error')}")
    return failures


def _source_mode_subject(source_manifest: dict[str, Any]) -> str:
    """Describe the sealed data route without overstating replay freshness."""
    mode_text = " ".join(
        str(source_manifest.get(key) or "")
        for key in ("data_mode", "status", "source")
    ).upper()
    live_read = source_manifest.get("live_read")
    live_route = source_manifest.get("live_route_used")
    if (
        "OFFLINE" in mode_text
        or "LOCAL_CSV_REPLAY" in mode_text
        or live_read is False
        or live_route is False
    ):
        return "This offline source-bound replay"
    return "This live source-bound system test"


def _build_conservative_annotation_plan_v2(
    *,
    pack: dict[str, Any],
    active_tf: str,
    direction: str,
    high: float | None,
    low: float | None,
    mid: float | None,
    target_price: float | None,
    target_side: str,
    invalidation_price: float | None,
    range_id: str | None,
    official_state: str,
) -> dict[str, Any]:
    window = (pack.get("ohlcv_windows") or {}).get("15m") or []
    n = len(window) if isinstance(window, list) else 120
    left = max(0, n - 26)
    right = max(left + 4, n - 2)
    path_left = max(0, n - 2)
    path_right = n + 6
    evidence_ids = [range_id] if range_id else []
    objects: list[dict[str, Any]] = []
    if target_price is not None and evidence_ids:
        objects.append(
            {
                "object_type": "liquidity_line",
                "semantic_object_id": f"{range_id}:target_liquidity",
                "timeframe": "15m",
                "label": f"{target_side.upper()} WATCH",
                "reason": f"Model-completion liquidity from certified {active_tf} active range.",
                "kind": "liquidity",
                "direction": direction if direction in {"bullish", "bearish"} else "mixed",
                "price": target_price,
                "start_index": left,
                "end_index": right,
                "line_style": "dotted",
                "evidence_object_ids": evidence_ids,
                "importance": 2,
            }
        )
    if invalidation_price is not None and evidence_ids:
        objects.append(
            {
                "object_type": "structure_segment",
                "semantic_object_id": f"{range_id}:watch_invalidation",
                "timeframe": "15m",
                "label": "WATCH INVALIDATION",
                "reason": "Watch invalidation from the opposite side of the certified active range; not an executable SL.",
                "kind": "structure",
                "direction": direction if direction in {"bullish", "bearish"} else "mixed",
                "price": invalidation_price,
                "start_index": left,
                "end_index": right,
                "line_style": "dashed",
                "evidence_object_ids": evidence_ids,
                "importance": 3,
            }
        )
    if official_state == "WATCH_ONLY" and mid is not None and target_price is not None:
        objects.append(
            {
                "object_type": "path_projection",
                "semantic_object_id": f"{range_id or 'active_range'}:conditional_path",
                "timeframe": "15m",
                "label": "POSSIBLE PATH",
                "reason": "Conditional watch path only; it is not a prediction guarantee or trade signal.",
                "kind": "path",
                "direction": direction if direction in {"bullish", "bearish"} else "mixed",
                "price_low": mid,
                "price_high": target_price,
                "start_index": path_left,
                "end_index": path_right,
                "line_style": "dashed",
                "evidence_object_ids": [],
                "importance": 3,
            }
        )
    return {
        "schema": "professional_smc_annotation_plan_v2",
        "style": "professional_smc_sparse",
        "objects": objects,
        "notes": [
            "Local deterministic provider emitted conservative v2 markup only from certified active range evidence.",
            "No POI, BOS, CHoCH, entry, SL, TP, or trade box is drawn unless separately validated.",
        ],
    }


def timeframe_bias(summary: dict[str, Any]) -> str:
    close = float(summary["last_close"])
    first = float(summary["first_open"])
    high = float(summary["high"])
    low = float(summary["low"])
    span = max(high - low, 1e-9)
    move = (close - first) / span
    if move > 0.18:
        return "bullish"
    if move < -0.18:
        return "bearish"
    return "mixed"


def _display_bias_labels(raw_tf_bias: dict[str, str], structure_narrative: dict[str, Any]) -> dict[str, str]:
    labels = dict(raw_tf_bias)
    for timeframe, item in (structure_narrative.get("timeframes") or {}).items():
        if not isinstance(item, dict):
            continue
        if item.get("formal_graph_authority") is True:
            labels[str(timeframe)] = str(item.get("label") or "unknown")
        elif item.get("label") not in {None, "unknown"}:
            labels[str(timeframe)] = str(item["label"])
    return labels


def _vote_bias_labels(raw_tf_bias: dict[str, str], structure_narrative: dict[str, Any]) -> dict[str, str]:
    labels = dict(raw_tf_bias)
    for timeframe, item in (structure_narrative.get("timeframes") or {}).items():
        if not isinstance(item, dict):
            continue
        if item.get("formal_graph_authority") is True:
            vote = str(item.get("vote_bias") or "unknown")
            labels[str(timeframe)] = vote if vote in {"bullish", "bearish"} else "unknown"
        elif item.get("vote_bias") in {"bullish", "bearish"}:
            labels[str(timeframe)] = str(item["vote_bias"])
    return labels


def _formal_graph_aware_fallback_bias(
    raw_tf_bias: dict[str, str],
    structure_narrative: dict[str, Any],
) -> dict[str, str]:
    """Allow raw drift fallback only where no formal graph node exists."""
    timeframes = structure_narrative.get("timeframes") or {}
    authoritative = {
        str(timeframe)
        for timeframe, item in timeframes.items()
        if isinstance(item, dict) and item.get("formal_graph_authority") is True
    }
    return {
        timeframe: bias
        for timeframe, bias in raw_tf_bias.items()
        if timeframe not in authoritative
    }


def format_price(value: float | None) -> str:
    if value is None:
        return "n/a"
    abs_value = abs(float(value))
    if abs_value >= 1000:
        return f"{float(value):,.1f}"
    if abs_value >= 100:
        return f"{float(value):.2f}"
    if abs_value >= 1:
        return f"{float(value):.4g}"
    return f"{float(value):.6g}"


def _short_parent_child_label(parent_child_context: dict[str, Any]) -> str:
    parent_tf = str(parent_child_context.get("parent_timeframe") or "HTF")
    parent_bias = str(parent_child_context.get("parent_bias") or "parent")
    child_tf = str(parent_child_context.get("child_timeframe") or "LTF")
    child_bias = str(parent_child_context.get("child_bias") or "child")
    return f"{parent_tf} {parent_bias} parent / {child_tf} {child_bias} child"


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Live AI SMC Full System Test", ""]
    lines.append(f"Created: `{summary['created_at']}`")
    lines.append(f"Run dir: `{summary['run_dir']}`")
    lines.append("Observe-only: `true`")
    lines.append("")
    for item in summary["results"]:
        lines.append(f"## {item['symbol']}")
        lines.append("")
        lines.append(f"Status: `{item.get('status')}`")
        if item.get("error"):
            lines.append(f"Error: `{item.get('error_type')}` {item.get('error')}")
            lines.append("")
            continue
        lines.append(f"Official state: `{item.get('official_state')}`")
        lines.append(f"Validation: `{item.get('validation_result')}`")
        lines.append(f"Output: `{item.get('output_dir')}`")
        lines.append(f"Official chart: `{item.get('official_chart')}`")
        lines.append(f"Thesis: `{item.get('thesis_path')}`")
        if item.get("colleague_memory"):
            lines.append(
                "Colleague memory: "
                f"`{item.get('colleague_memory')}` "
                f"(store updated: `{str(bool(item.get('memory_store_updated'))).lower()}`, "
                f"forward: `{str(bool(item.get('memory_forward_transition'))).lower()}`)"
            )
        identity = item.get("memory_market_identity")
        if isinstance(identity, dict):
            lines.append(
                "Memory source identity: "
                f"`{identity.get('source')} / {identity.get('provider_symbol')} / "
                f"{identity.get('market_type')}`"
            )
        if item.get("narrative_shadow_comparison"):
            lines.append(
                f"Narrative shadow comparison: `{item.get('narrative_shadow_comparison')}`"
            )
            metrics = item.get("narrative_shadow_metrics")
            if isinstance(metrics, dict):
                lines.append(
                    "Shadow/canonical overlap: "
                    f"`{metrics.get('matched_count')}` matched of "
                    f"`{metrics.get('shadow_count')}` shadow and "
                    f"`{metrics.get('canonical_count')}` canonical objects; "
                    f"human score: `{metrics.get('human_review_status')}`; "
                    f"promotion eligible: `{str(bool(metrics.get('promotion_eligible'))).lower()}`"
                )
        if item.get("memory_transition_notes"):
            lines.append("Since last look:")
            for note in item["memory_transition_notes"]:
                lines.append(f"- {note}")
        if item.get("perception_failures"):
            lines.append("Perception gaps (fail-closed, not 'nothing here'):")
            for failure in item["perception_failures"]:
                lines.append(f"- {failure}")
        lines.append(f"Last prices: `{item.get('last_prices')}`")
        if item.get("source_manifest", {}).get("proxy_note"):
            lines.append(f"Source note: {item['source_manifest']['proxy_note']}")
        if item.get("hard_issues"):
            lines.append("Hard issues:")
            for issue in item["hard_issues"]:
                lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
        lines.append("")
    return "\n".join(lines)


def record_selective_decision(
    *,
    symbol_root: Path,
    output_root: str | Path,
    symbol: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Append this run's decision to the selective-outcome ledger.

    The ledger apparatus existed but nothing ever wrote to it, so the metric
    that matters most for a system whose default output is refusal --
    ``missed_favorable_outcome_rate`` -- had no data, and "correctly cautious"
    was indistinguishable from "broken and silent".

    Every run is one decision. Refusals carry the read the system *would* have
    taken, which is what lets a later outcome pass score them. Nothing here may
    fail the run or create any authority: it records what already happened.
    """
    from smc_desk.evaluation.selective_outcomes import (
        append_selective_ledger_event,
        build_shadow_decision_from_run,
    )

    outcome: dict[str, Any] = {"selective_ledger_status": "not_attempted"}
    try:
        pack = _load_final_evidence_pack(symbol_root)
        pack = pack if isinstance(pack, dict) else {}
        graph = pack.get("formal_structure_graph") or {}
        episode_graph = pack.get("formal_causal_episode_graph") or {}
        decision_raw = (pack.get("market_state") or {}).get("decision_time") or summary.get(
            "last_close_timestamps", {}
        ).get("15m")
        decision_time = pd.Timestamp(decision_raw)
        if decision_time.tzinfo is None:
            decision_time = decision_time.tz_localize("UTC")

        ledger_path = Path(output_root) / "selective_outcome_ledger.jsonl"
        event = build_shadow_decision_from_run(
            # Identity must include the decision time: the same symbol observed
            # at two different closes is two cases, not a duplicate.
            case_id=f"{symbol}:{decision_time.isoformat()}",
            symbol=symbol,
            decision_time=decision_time.to_pydatetime(),
            horizon="next_20_bars_15m",
            official_state=str(summary.get("official_state") or ""),
            hard_issue_codes=[
                str((issue or {}).get("code") or "")
                for issue in (summary.get("hard_issues") or [])
                if isinstance(issue, dict)
            ],
            narrative_context=graph.get("narrative_context") or {},
            invariants=episode_graph.get("invariants") or {},
            source_hashes={
                # The pack carries its hash at provenance.pack_hash. Reading a
                # non-existent top-level key silently wrote "" into every real
                # ledger entry, so decisions could not be tied to the evidence
                # that produced them -- the one thing a hash chain is for.
                "evidence_pack_sha256": str(
                    (pack.get("provenance") or {}).get("pack_hash") or ""
                ),
            },
            data_failed=str(summary.get("status") or "").upper().startswith("FAILED"),
        )
        entry = append_selective_ledger_event(ledger_path, event)
        outcome["selective_ledger_status"] = "recorded"
        outcome["selective_ledger_path"] = str(ledger_path)
        outcome["selective_decision"] = entry.get("decision")
        outcome["selective_shadow_prediction"] = entry.get("shadow_prediction")
        outcome["selective_uncertainty"] = entry.get("uncertainty_score")
    except Exception as exc:  # noqa: BLE001 -- additive evidence, never fatal
        outcome["selective_ledger_status"] = f"failed:{type(exc).__name__}"
    return outcome

if __name__ == "__main__":
    main()
