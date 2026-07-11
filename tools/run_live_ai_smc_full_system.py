#!/usr/bin/env python3
"""Run the observe-only AI SMC v3 pipeline on current market data.

This is a system test harness, not an execution tool. It uses Binance USD-M
futures for crypto symbols and Yahoo chart data for XAU/GC futures proxy.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER
from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest
from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3
from smc_desk.data.historical_backfill import fetch_historical_closed_ohlcv
from smc_desk.perception.structure_narrative import build_structure_narrative, derive_strict_htf_bias


BINANCE_BASE = "https://fapi.binance.com"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEFRAMES = ("15m", "1h", "4h", "1d")


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
            }
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
        }
    return frames, {
        "symbol": symbol,
        "source": "binance_usdm_rest",
        "market_type": "USD-M perpetual futures",
        "timeframes": manifests,
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
    four_hour = resample_ohlcv(one_hour, "4h")
    frames = {"15m": fifteen, "1h": one_hour, "4h": four_hour, "1d": one_day}
    manifest = {
        "symbol": "XAUUSD",
        "source": "yahoo_chart",
        "provider_symbol": ticker,
        "proxy_note": "Yahoo XAUUSD=X returned no data; GC=F COMEX gold futures used as XAUUSD proxy for observe-only system test.",
        "timeframes": {tf: {"row_count": len(df), "last_timestamp": str(df["timestamp"].iloc[-1])} for tf, df in frames.items()},
    }
    return frames, manifest


def load_yahoo_forex_timeframes(symbol: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    ticker = f"{symbol}=X"
    fifteen = yahoo_chart_df(ticker, interval="15m", range_="60d")
    one_hour = yahoo_chart_df(ticker, interval="1h", range_="730d")
    one_day = yahoo_chart_df(ticker, interval="1d", range_="2y")
    four_hour = resample_ohlcv(one_hour, "4h")
    frames = {"15m": fifteen, "1h": one_hour, "4h": four_hour, "1d": one_day}
    manifest = {
        "symbol": symbol,
        "source": "yahoo_chart",
        "provider_symbol": ticker,
        "market_type": "forex_spot_chart_proxy",
        "timeframes": {tf: {"row_count": len(df), "last_timestamp": str(df["timestamp"].iloc[-1])} for tf, df in frames.items()},
    }
    return frames, manifest


def http_get_json(url: str, params: dict[str, Any], timeout: float = 20.0) -> Any:
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "smc-codex-desk-live-system-test/1.0"})
    response.raise_for_status()
    return response.json()


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


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    indexed = df.set_index("timestamp").sort_index()
    out = indexed.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open", "high", "low", "close"]).reset_index()


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
    direction = derive_strict_htf_bias(vote_bias, fallback_bias=raw_tf_bias)
    parent_child_context = structure_narrative.get("parent_child_context") if isinstance(structure_narrative, dict) else {}
    if not isinstance(parent_child_context, dict):
        parent_child_context = {}
    parent_child_conflict = bool(parent_child_context.get("has_parent_child_conflict"))
    parent_child_sentence = str(parent_child_context.get("thesis_sentence") or "").strip()
    if parent_child_conflict:
        direction = "mixed"
    htf_direction = direction

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
        {"text": "No validated sweep or displacement promoted", "kind": "state"},
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
            "narrative": (
                f"{parent_child_sentence} This is a context conflict, so no clean direction is promoted into a trade plan."
                if parent_child_conflict and parent_child_sentence
                else (
                    "A confirmed active POI is mapped for observation, but no validated sweep/displacement/entry confirmation is promoted into a trade plan."
                    if has_active_poi
                    else "This live system test sees context and range liquidity, but no validated sweep/displacement/POI is promoted into a trade plan."
                )
            ),
        },
        "displacement_assessment": {
            "direction": "none",
            "quality": "none",
            "structure_broken": False,
            "evidence_object_ids": [],
            "summary": "No validated displacement candidate was promoted for this observe-only test run.",
        },
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
                    else "Refused executable trade because sweep/displacement/active POI were not validated."
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
                "No confirmed sweep/displacement sequence promoted into execution.",
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
                    else ". The system does not have validated sweep/displacement/active POI/entry evidence, so it refuses a trade plan."
                )
            )
        ),
    }


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
        if isinstance(item, dict) and item.get("label") not in {None, "unknown"}:
            labels[str(timeframe)] = str(item["label"])
    return labels


def _vote_bias_labels(raw_tf_bias: dict[str, str], structure_narrative: dict[str, Any]) -> dict[str, str]:
    labels = dict(raw_tf_bias)
    for timeframe, item in (structure_narrative.get("timeframes") or {}).items():
        if isinstance(item, dict) and item.get("vote_bias") in {"bullish", "bearish"}:
            labels[str(timeframe)] = str(item["vote_bias"])
    return labels


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
        lines.append(f"Last prices: `{item.get('last_prices')}`")
        if item.get("source_manifest", {}).get("proxy_note"):
            lines.append(f"Source note: {item['source_manifest']['proxy_note']}")
        if item.get("hard_issues"):
            lines.append("Hard issues:")
            for issue in item["hard_issues"]:
                lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
