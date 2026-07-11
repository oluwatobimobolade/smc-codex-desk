#!/usr/bin/env python3
"""Offline full-system AI SMC v3 run on local XAUUSD CSVs (stale-data demo).

Mirrors ``tools/run_live_ai_smc_full_system.py`` exactly — same orchestrator
call, same conservative local provider, same minimum-depth enforcement — but
loads candles from local TradingView/OANDA CSVs instead of fetching over the
network. Used when the live data route (Yahoo/Binance/WebBridge) is not
reachable from the current environment.

IMPORTANT: this is an OFFLINE observe-only pipeline exercise on STALE data.
It must never be presented as a live read or used for a trade call. Every
artifact it writes is tagged OFFLINE / STALE-DATA.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest
from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3
from smc_desk.data.ohlcv_contract import normalize_ohlcv_timestamps
from smc_desk.data.historical_backfill import build_context_depth_report
from smc_desk.data.timeframe_reconstruction import resample_ohlcv
from tools.run_live_ai_smc_full_system import build_conservative_ai_payload

TIMEFRAMES = ("15m", "1h", "4h", "1d")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Offline full AI SMC v3 run on local XAUUSD CSVs (stale-data demo).")
    p.add_argument("--data-dir", required=True, help="Directory containing a canonical XAUUSD_15m.csv or XAUUSDT_15m_live_full.csv")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--output-root", default="analysis_runs")
    p.add_argument("--run-tag", default="OFFLINE_FULL_SYSTEM_XAUUSD_STALE")
    p.add_argument("--stale-as-of", required=True, help="ISO decision cutoff; only candles fully closed by this time are used")
    p.add_argument("--allow-shallow-context", action="store_true")
    return p.parse_args()


def load_local_timeframes(data_dir: Path, stale_as_of: str, symbol: str = "XAUUSD") -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    decision_cutoff = _parse_utc(stale_as_of)
    clean_symbol = symbol.upper().replace("/", "").replace("-", "")
    candidates = [
        data_dir / f"{clean_symbol}_15m.csv",
        data_dir / f"{clean_symbol}_15m_live_full.csv",
        data_dir / "XAUUSDT_15m_live_full.csv",
        data_dir / "XAUUSDT_15m.csv",
        data_dir / "XAUUSD_15m.csv",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"No canonical 15m CSV found in {data_dir}")
    canonical = normalize_ohlcv_timestamps(pd.read_csv(path))
    _validate_ohlcv(canonical, path)
    canonical = canonical.sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(canonical["timestamp"], utc=True)
    canonical = canonical.loc[timestamps + pd.Timedelta("15min") <= decision_cutoff].reset_index(drop=True)
    if canonical.empty:
        raise ValueError(f"{path} has no fully closed 15m candles by {decision_cutoff.isoformat()}")
    frames: dict[str, pd.DataFrame] = {"15m": canonical}
    mtf_cutoff = decision_cutoff.tz_localize(None)
    for tf in ("1h", "4h", "1d"):
        frames[tf] = resample_ohlcv(canonical, tf, mtf_cutoff)

    manifests: dict[str, Any] = {}
    for tf, df in frames.items():
        manifests[tf] = {
            "provider": "local_csv_offline" if tf == "15m" else "derived_from_canonical_15m",
            "row_count": len(df),
            "first_timestamp": str(df["timestamp"].iloc[0]) if not df.empty else None,
            "last_timestamp": str(df["timestamp"].iloc[-1]) if not df.empty else None,
            "source_path": str(path),
            "canonical_timeframe": "15m",
            "decision_cutoff": decision_cutoff.isoformat(),
        }
    latest_close = pd.Timestamp(canonical["timestamp"].iloc[-1]).tz_localize("UTC") + pd.Timedelta("15min") if pd.Timestamp(canonical["timestamp"].iloc[-1]).tzinfo is None else pd.Timestamp(canonical["timestamp"].iloc[-1]).tz_convert("UTC") + pd.Timedelta("15min")
    manifest = {
        "symbol": clean_symbol,
        "source": "local_csv_offline",
        "market_type": "spot_gold_oanda_proxy",
        "data_mode": "OFFLINE_STALE_DEMO",
        "decision_cutoff": decision_cutoff.isoformat(),
        "latest_closed_15m": latest_close.isoformat(),
        "data_lag_seconds_at_cutoff": max(0.0, (decision_cutoff - latest_close).total_seconds()),
        "network_fetch_attempted": False,
        "live_read": False,
        "canonical_source": "15m_local_csv",
        "htf_policy": "derived_from_15m_completed_buckets_only",
        "timeframes": manifests,
    }
    return frames, manifest


def main() -> None:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(args.output_root).expanduser().resolve() / f"{args.run_tag}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    symbol = args.symbol.upper()
    symbol_root = root / symbol
    symbol_root.mkdir(parents=True, exist_ok=True)

    timeframe_dfs, source_manifest = load_local_timeframes(Path(args.data_dir), args.stale_as_of, symbol)
    provider = CallableAISMCProvider(
        lambda request, manifest=source_manifest: build_conservative_ai_payload(request, manifest),
        provider_name="local_codex_thread_brain",
        model_name="prompt_os_v1_conservative_observe_only_offline_stale",
        provider_mode="LOCAL_DETERMINISTIC_PROVIDER",
    )
    result = run_ai_smc_orchestrator_v3(
        symbol=symbol,
        timeframe_dfs=timeframe_dfs,
        provider=provider,
        output_dir=symbol_root,
        detector_candidates=None,
        session_context={"source_manifest": source_manifest, "live_system_test": False, "offline_stale_demo": True},
        enforce_minimum_depth=not args.allow_shallow_context,
    )

    depth_profile = {tf: {"15m": 1500, "1h": 1000, "4h": 500, "1d": 365}[tf] for tf in TIMEFRAMES}
    depth_report = build_context_depth_report(timeframe_dfs, minimum_depths=depth_profile)
    summary = {
        "schema": "offline_full_system_ai_smc_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(root),
        "symbol": symbol,
        "observe_only": True,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "api_llm_called": False,
        "data_mode": "OFFLINE_STALE_DEMO",
        "decision_cutoff": source_manifest["decision_cutoff"],
        "network_fetch_attempted": False,
        "live_read": False,
        "status": result.status,
        "official_state": result.report.get("official_state"),
        "validation_result": result.report.get("validation_result"),
        "hard_issues": result.report.get("hard_issues", []),
        "provider": result.report.get("provider"),
        "context_depth_report": depth_report,
        "source_manifest": source_manifest,
        "output_dir": str(symbol_root),
        "official_chart": result.report.get("official_chart"),
        "thesis_path": str(symbol_root / "15_ai_thesis" / "thesis.md"),
        "last_prices": {tf: float(df["close"].iloc[-1]) for tf, df in timeframe_dfs.items()},
        "last_timestamps": {tf: str(df["timestamp"].iloc[-1]) for tf, df in timeframe_dfs.items()},
    }
    (root / "offline_full_system_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("symbol", "status", "official_state", "validation_result", "data_mode", "decision_cutoff", "output_dir", "hard_issues")}, indent=2, default=str))


def _parse_utc(value: str) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid stale-as-of timestamp: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _validate_ohlcv(df: pd.DataFrame, path: Path) -> None:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    if df.empty:
        raise ValueError(f"{path} is empty")
    if df[list(required)].isna().any().any():
        raise ValueError(f"{path} contains NaN OHLCV values")
    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    if timestamps.duplicated().any():
        raise ValueError(f"{path} contains duplicate timestamps")
    numeric = df[["open", "high", "low", "close"]].astype(float)
    invalid = (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)) | (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1))
    if invalid.any():
        raise ValueError(f"{path} contains invalid OHLC geometry")


if __name__ == "__main__":
    main()
