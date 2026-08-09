"""Local-first SMC evidence pack builder.

The evidence pack gathers market data, chart image references, detector
candidates, profile constraints, and provenance. It deliberately does not make
an official trade decision.
"""
from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.decision.active_range_resolver import resolve_active_range_authority
from smc_desk.perception.causal_poi_authority import build_causal_poi_authority
from smc_desk.perception.formal_causal_episode_graph import build_formal_causal_episode_graph
from smc_desk.perception.evidence_contract import build_object_evidence_contracts
from smc_desk.perception.formal_structure_graph import build_mtf_structure_graph
from smc_desk.perception.structure_engine_v3 import StructureEngineV3Shadow
from smc_desk.perception.structure_narrative import build_structure_narrative, prefer_formal_graph_override
from smc_desk.perception.sweep_lifecycle import enrich_sweep_lifecycles
from smc_desk.profile.smc_intraday_profile import get_intraday_profile


def _coerce_float(value: Any) -> float | None:
    """Read a price without inventing one. Decimals and strings are fine; None stays None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


CANDIDATE_GROUPS = (
    "swings",
    "structure_breaks",
    "fvgs",
    "poi_grade_fvgs",
    "liquidity_levels",
    "sweeps",
    "order_blocks",
    "inducements",
    "active_pois",
    "pois",
)


def build_smc_evidence_pack(
    *,
    symbol: str,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    chart_images: Mapping[str, str | Path] | None = None,
    detector_candidates: Mapping[str, Any] | None = None,
    session_context: Mapping[str, Any] | None = None,
    doctrine_notes: Sequence[str] | None = None,
    max_candles_per_timeframe: int = 120,
    embed_images: bool = False,
    daily_session_profile: str = "exchange_daily_utc",
) -> dict[str, Any]:
    if not timeframe_dfs:
        raise ValueError("timeframe_dfs is required")
    profile = dict(get_intraday_profile())
    ohlcv_summaries: dict[str, Any] = {}
    ohlcv_windows: dict[str, Any] = {}
    dataframe_hashes: dict[str, str] = {}

    for timeframe, df in timeframe_dfs.items():
        if df.empty:
            raise ValueError(f"{timeframe} dataframe is empty")
        normalized = _normalize_df(df)
        ohlcv_summaries[timeframe] = _summarize_df(normalized, timeframe=timeframe)
        ohlcv_windows[timeframe] = _tail_records(normalized, max_candles_per_timeframe)
        dataframe_hashes[timeframe] = _hash_dataframe(normalized)

    active_range_authority = resolve_active_range_authority(
        symbol=symbol,
        timeframe_dfs=timeframe_dfs,
    )
    candidate_manifest = _candidate_manifest(detector_candidates or {})
    decision_time = _latest_closed_decision_time(ohlcv_summaries)
    candidate_manifest = enrich_sweep_lifecycles(
        candidate_manifest,
        timeframe_dfs,
        decision_time=decision_time,
    )
    structure_engine_v3_shadow = StructureEngineV3Shadow().analyze(
        symbol=symbol,
        detector_candidates=candidate_manifest,
        timeframe_dfs=timeframe_dfs,
        decision_time=decision_time,
    ).to_dict()
    formal_structure_graph = build_mtf_structure_graph(
        symbol=symbol,
        detector_candidates=candidate_manifest,
        active_range_authority=active_range_authority,
        timeframe_dfs=timeframe_dfs,
        decision_time=decision_time,
    )
    causal_poi_authority = build_causal_poi_authority(
        detector_candidates=candidate_manifest,
        formal_structure_graph=formal_structure_graph,
    )
    formal_causal_episode_graph = build_formal_causal_episode_graph(
        symbol=symbol,
        decision_time=decision_time,
        detector_candidates=candidate_manifest,
        structure_shadow=structure_engine_v3_shadow,
        formal_structure_graph_v1=formal_structure_graph,
        causal_poi_authority=causal_poi_authority,
    )
    structure_narrative = prefer_formal_graph_override(
        build_structure_narrative(
            candidate_manifest,
            raw_bias={timeframe: _summary_bias(summary) for timeframe, summary in ohlcv_summaries.items()},
        ),
        formal_structure_graph,
    )
    doctrine_hash = _stable_hash({"profile": profile, "notes": list(doctrine_notes or [])})
    object_evidence_contracts = build_object_evidence_contracts(
        detector_candidates=candidate_manifest,
        decision_time=decision_time,
        doctrine_hash=doctrine_hash,
        formal_structure_graph=formal_structure_graph,
    )
    pack = {
        "schema": "smc_evidence_pack_v1",
        "symbol": symbol,
        "daily_candle_mode": daily_session_profile,
        "asset_class": "crypto" if any(crypto in symbol.upper() for crypto in ("BTC", "ETH", "SOL", "AVAX", "DOGE", "USDT")) else "forex",
        "note": "For FX/ICT use NY close daily profile",
        "data_contract": {
            "source": "local_ohlcv",
            "canonical_timeframe": "15m",
            "htf_policy": "derive_from_15m_unless_native_audit",
            "execution_authority": "disabled",
        },
        "doctrine_profile": profile,
        "doctrine_notes": list(doctrine_notes or []),
        "session_context": dict(session_context or {}),
        "chart_images": _image_manifest(chart_images or {}, embed=embed_images),
        "ohlcv_summaries": ohlcv_summaries,
        "ohlcv_windows": ohlcv_windows,
        "active_range_authority": active_range_authority,
        "detector_candidates": candidate_manifest,
        "structure_narrative": structure_narrative,
        "structure_engine_v3_shadow": structure_engine_v3_shadow,
        "formal_structure_graph": formal_structure_graph,
        "formal_causal_episode_graph": formal_causal_episode_graph,
        "causal_poi_authority": causal_poi_authority,
        "object_evidence_contracts": object_evidence_contracts,
        # Which detected objects are structurally significant, and why. The
        # detector legitimately emits thousands of geometric matches; this
        # tells a reader (and the annotation planner) which of them a trader
        # would actually mark. Descriptive only -- no candidate is removed
        # from detector_candidates, and nothing here promotes anything.
        "structural_significance": _significance_report(candidate_manifest, ohlcv_windows),
        "provenance": {
            "dataframe_hashes": dataframe_hashes,
            "pack_hash": None,
        },
        "authority_contract": {
            "evidence_only": True,
            "detectors_are_candidates_only": True,
            "structure_engine_v3_shadow_can_only_downgrade": True,
            "formal_causal_episode_graph_can_only_downgrade": True,
            "probabilistic_confidence_allowed": False,
            "official_decision": None,
            "signal_allowed": False,
            "entry_authorized": False,
            "stop_loss_authorized": False,
            "take_profit_authorized": False,
            "live_execution": "disabled",
            "paper_execution": "disabled",
        },
    }
    # Derived last so it can read the assembled graph, significance report and
    # POI authority in one place. Observe-only: it describes where the setup
    # has got to and what is still missing, and grants no execution authority.
    pack["market_state"] = _market_state(pack)

    pack["provenance"]["pack_hash"] = _stable_hash(pack)
    return pack


def _market_state(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Run the trader confirmation sequence over the assembled evidence."""
    try:
        from smc_desk.perception.market_state import build_market_state
        from smc_desk.perception.liquidity_model import collect_liquidity_evidence
        from smc_desk.perception.narrative_hierarchy import select_primary_poi, read_narrative

        graph = pack.get("formal_structure_graph") or {}
        narrative_payload = graph.get("narrative_context") or {}

        # Collect POI candidates from the causal authority, which already
        # assigns structural roles. Both scenarios are offered; the narrative
        # picks the one aligned with context.
        #
        # Every POI each scenario carries is offered, not just the one it
        # nominated. Taking only `primary_causal_poi` meant the ranking below
        # could never overturn an upstream choice -- it would rank a field of
        # one. The secondaries are the field.
        candidates: list[Mapping[str, Any]] = []
        seen_poi_ids: set[str] = set()
        scenarios = (pack.get("causal_poi_authority") or {}).get("scenarios")
        if isinstance(scenarios, Mapping):
            for direction, scenario in scenarios.items():
                if not isinstance(scenario, Mapping):
                    continue
                offered = [
                    scenario.get("primary_causal_poi"),
                    *(scenario.get("secondary_reaction_pois") or []),
                ]
                for poi in offered:
                    if not isinstance(poi, Mapping):
                        continue
                    poi_id = str(poi.get("object_id") or "")
                    if not poi_id or poi_id in seen_poi_ids:
                        continue
                    seen_poi_ids.add(poi_id)
                    candidates.append({**poi, "direction": poi.get("direction") or direction})

        primary_poi = None
        if candidates and narrative_payload.get("is_coherent"):
            liquidity, swept_ids = collect_liquidity_evidence(
                pack.get("detector_candidates") or {}
            )
            narrative = read_narrative(
                timeframes=graph.get("timeframes") or {},
                active_range=graph.get("active_range") or {},
                current_price=(graph.get("active_range") or {}).get("current_price"),
                liquidity_levels=liquidity,
                swept_object_ids=swept_ids,
            )
            active_range = graph.get("active_range") or {}
            primary_poi = select_primary_poi(
                narrative=narrative,
                poi_candidates=candidates,
                # The resolved dealing range, so premium/discount is measured
                # against the range price is actually trading in rather than
                # against whatever extremes happen to sit in the window.
                equilibrium=_coerce_float(active_range.get("equilibrium")),
                current_price=_coerce_float(active_range.get("current_price")),
            )

        return build_market_state(evidence_pack=pack, primary_poi=primary_poi).to_dict()
    except Exception as exc:  # noqa: BLE001 -- descriptive layer, never fatal
        return {
            "schema": "market_state_v1",
            "state": "NO_CONTEXT",
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
            "authority": "observe_only_market_state",
            "signal_allowed": False,
        }


def _significance_report(
    candidate_manifest: Mapping[str, Any],
    ohlcv_windows: Mapping[str, Any],
) -> dict[str, Any]:
    """Grade each timeframe's swings and confirmed breaks by significance.

    Never raises into the pack build: an ungradeable timeframe is reported as
    such rather than silently dropped, and grading failure must not be able to
    take down evidence assembly.
    """
    from smc_desk.perception.significance import grade_timeframe

    report: dict[str, Any] = {
        "schema": "structural_significance_report_v1",
        "authority": "descriptive_only_no_promotion",
        "timeframes": {},
    }
    for timeframe, payload in (candidate_manifest or {}).items():
        if not isinstance(payload, Mapping):
            continue
        candles = ohlcv_windows.get(timeframe)
        if not isinstance(candles, list) or not candles:
            report["timeframes"][timeframe] = {"error": "no candle window available"}
            continue
        try:
            swings = payload.get("swings") or []
            breaks = [
                b for b in (payload.get("structure_breaks") or [])
                if isinstance(b, Mapping) and b.get("confirmed_at")
                and not ((b.get("evidence") or {}).get("is_unconfirmed_probe"))
            ]
            summary = grade_timeframe(
                candles=candles,
                swings=[s for s in swings if isinstance(s, Mapping)],
                structure_breaks=breaks,
            )
            report["timeframes"][timeframe] = {
                "atr": round(summary.atr, 8),
                "counts": summary.counts,
                "raw_object_count": len(swings) + len(breaks),
                "tradeable_object_ids": [s.object_id for s in summary.tradeable],
                "major_object_ids": [s.object_id for s in summary.by_grade("major")],
            }
        except Exception as exc:  # noqa: BLE001 -- descriptive layer, never fatal
            report["timeframes"][timeframe] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return report


def _latest_closed_decision_time(summaries: Mapping[str, Mapping[str, Any]]) -> str:
    close_times = [
        pd.Timestamp(summary["last_close_time"])
        for summary in summaries.values()
        if summary.get("last_close_time") is not None
    ]
    if not close_times:
        raise ValueError("Cannot derive a closed-candle decision time for the evidence pack.")
    decision_time = max(close_times)
    if decision_time.tzinfo is None:
        decision_time = decision_time.tz_localize("UTC")
    else:
        decision_time = decision_time.tz_convert("UTC")
    return decision_time.isoformat().replace("+00:00", "Z")


def assert_evidence_pack_has_no_decision(evidence_pack: Mapping[str, Any]) -> None:
    contract = evidence_pack.get("authority_contract") or {}
    if contract.get("evidence_only") is not True:
        raise AssertionError("Evidence pack must be evidence_only.")
    if contract.get("official_decision") is not None:
        raise AssertionError("Evidence pack cannot carry an official decision.")
    for forbidden in ("official_state", "entry", "stop_loss", "take_profit", "target_plan"):
        if forbidden in evidence_pack:
            raise AssertionError(f"Evidence pack cannot decide {forbidden}.")


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"OHLC dataframe missing required columns: {missing}")
    out = df.copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={"index": "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return out.sort_values("timestamp").reset_index(drop=True)


def _summarize_df(df: pd.DataFrame, *, timeframe: str) -> dict[str, Any]:
    high = float(df["high"].max())
    low = float(df["low"].min())
    close = float(df["close"].iloc[-1])
    duration = {"5m": pd.Timedelta(minutes=5), "15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "12h": pd.Timedelta(hours=12), "1d": pd.Timedelta(days=1)}.get(timeframe)
    last_open = df["timestamp"].iloc[-1]
    return {
        "candle_count": int(len(df)),
        "first_timestamp": str(df["timestamp"].iloc[0]),
        "last_timestamp": str(last_open),
        "last_open_time": str(last_open),
        "last_close_time": str(last_open + duration) if duration is not None else None,
        "decision_cutoff_semantics": "closed_candle_time",
        "first_open": float(df["open"].iloc[0]),
        "last_close": close,
        "high": high,
        "low": low,
        "range_mid": (high + low) / 2.0,
        "volume_sum": float(df["volume"].sum()),
    }


def _summary_bias(summary: Mapping[str, Any]) -> str:
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


def _tail_records(df: pd.DataFrame, max_rows: int) -> list[dict[str, Any]]:
    columns = [col for col in ("timestamp", "open", "high", "low", "close", "volume") if col in df.columns]
    records = df[columns].tail(max_rows).to_dict(orient="records")
    for row in records:
        row["timestamp"] = str(row["timestamp"])
        for key in ("open", "high", "low", "close", "volume"):
            if key in row:
                row[key] = float(row[key])
    return records


def _hash_dataframe(df: pd.DataFrame) -> str:
    columns = [col for col in ("timestamp", "open", "high", "low", "close", "volume") if col in df.columns]
    payload = df[columns].to_json(orient="records", date_format="iso", double_precision=10)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _image_manifest(chart_images: Mapping[str, str | Path], *, embed: bool = False) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    for timeframe, raw_path in chart_images.items():
        path = Path(raw_path)
        item = {
            "path": str(path),
            "exists": path.exists(),
            "sha256": None,
            "role": "clean_chart_image",
        }
        if path.exists() and path.is_file():
            image_bytes = path.read_bytes()
            item["sha256"] = hashlib.sha256(image_bytes).hexdigest()
            if embed:
                item["base64"] = base64.b64encode(image_bytes).decode("ascii")
                item["media_type"] = "image/png"
        manifest[timeframe] = item
    return manifest


def _candidate_manifest(detector_candidates: Mapping[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    for timeframe, raw in detector_candidates.items():
        if raw is None:
            manifest[timeframe] = {group: [] for group in CANDIDATE_GROUPS}
            continue
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="json")
        if not isinstance(raw, Mapping):
            raise TypeError(f"Detector candidates for {timeframe} must be a mapping or PerceptionSnapshot-like object")
        timeframe_payload: dict[str, Any] = {}
        timeframe_payload["poi_lifecycle_contract"] = [{
            "object_id": f"{timeframe}:poi_lifecycle_contract",
            "available": "active_pois" in raw and "pois" in raw,
            "candidate_role": "candidate_only",
            "truth_status": "pipeline_contract_metadata",
            "official_decision_authority": False,
        }]
        structure_state = raw.get("structure_state") or {}
        if hasattr(structure_state, "model_dump"):
            structure_state = structure_state.model_dump(mode="json")
        timeframe_payload["structure_state"] = dict(structure_state) if isinstance(structure_state, Mapping) else {}
        for group in CANDIDATE_GROUPS:
            items = raw.get(group, [])
            if group == "swings" and isinstance(items, Mapping):
                merged = []
                for scale, scale_items in items.items():
                    window_name = scale
                    if scale == "local":
                        window_name = "raw_pivot_candidate_window_1"
                    elif scale == "internal":
                        window_name = "raw_pivot_candidate_window_3"
                    elif scale == "external":
                        window_name = "raw_pivot_candidate_window_5"
                    for item in scale_items or []:
                        normalized = _candidate_dict(item)
                        normalized["scale"] = window_name
                        merged.append(normalized)
                items = merged
            timeframe_payload[group] = [_candidate_dict(item) for item in items or []]
        manifest[timeframe] = timeframe_payload
    return manifest


def _candidate_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        raw = item.model_dump(mode="json")
    elif isinstance(item, Mapping):
        raw = dict(item)
    else:
        raise TypeError(f"Unsupported candidate item: {type(item)!r}")

    obj_id = str(raw.get("object_id") or "")
    if obj_id.startswith("fvg_"):
        is_qualified = (raw.get("metadata") or {}).get("is_qualified", True)
        raw["raw_fvg"] = {
            "exists": True,
            "definition": "three candle wick non-overlap"
        }
        raw["qualified_fvg"] = {
            "passes_quality_filter": is_qualified,
            "reason": "large enough, aligned with displacement, in valid model" if is_qualified else "failed minimum gap width threshold"
        }

    if raw.get("confidence") is not None:
        raw["evidence_strength"] = raw.pop("confidence")
        raw["evidence_strength_semantics"] = "heuristic_not_probability"
    raw.setdefault("candidate_role", "candidate_only")
    raw.setdefault("truth_status", "weak_detector_candidate")
    raw.setdefault("official_decision_authority", False)
    return raw


def _stable_hash(value: Any) -> str:
    import json

    payload = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
