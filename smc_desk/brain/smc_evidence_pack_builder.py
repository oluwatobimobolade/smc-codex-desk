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
from smc_desk.perception.formal_structure_graph import build_mtf_structure_graph
from smc_desk.perception.structure_narrative import build_structure_narrative, prefer_formal_graph_override
from smc_desk.profile.smc_intraday_profile import get_intraday_profile


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
        ohlcv_summaries[timeframe] = _summarize_df(normalized)
        ohlcv_windows[timeframe] = _tail_records(normalized, max_candles_per_timeframe)
        dataframe_hashes[timeframe] = _hash_dataframe(normalized)

    active_range_authority = resolve_active_range_authority(
        symbol=symbol,
        timeframe_dfs=timeframe_dfs,
    )
    candidate_manifest = _candidate_manifest(detector_candidates or {})
    formal_structure_graph = build_mtf_structure_graph(
        symbol=symbol,
        detector_candidates=candidate_manifest,
        active_range_authority=active_range_authority,
        timeframe_dfs=timeframe_dfs,
    )
    structure_narrative = prefer_formal_graph_override(
        build_structure_narrative(
            candidate_manifest,
            raw_bias={timeframe: _summary_bias(summary) for timeframe, summary in ohlcv_summaries.items()},
        ),
        formal_structure_graph,
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
        "formal_structure_graph": formal_structure_graph,
        "provenance": {
            "dataframe_hashes": dataframe_hashes,
            "pack_hash": None,
        },
        "authority_contract": {
            "evidence_only": True,
            "detectors_are_candidates_only": True,
            "official_decision": None,
            "signal_allowed": False,
            "entry_authorized": False,
            "stop_loss_authorized": False,
            "take_profit_authorized": False,
            "live_execution": "disabled",
            "paper_execution": "disabled",
        },
    }
    pack["provenance"]["pack_hash"] = _stable_hash(pack)
    return pack


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


def _summarize_df(df: pd.DataFrame) -> dict[str, Any]:
    high = float(df["high"].max())
    low = float(df["low"].min())
    close = float(df["close"].iloc[-1])
    return {
        "candle_count": int(len(df)),
        "first_timestamp": str(df["timestamp"].iloc[0]),
        "last_timestamp": str(df["timestamp"].iloc[-1]),
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
        timeframe_payload: dict[str, list[dict[str, Any]]] = {}
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

    raw.setdefault("candidate_role", "candidate_only")
    raw.setdefault("truth_status", "weak_detector_candidate")
    raw.setdefault("official_decision_authority", False)
    return raw


def _stable_hash(value: Any) -> str:
    import json

    payload = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
