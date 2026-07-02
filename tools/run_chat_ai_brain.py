#!/usr/bin/env python3
"""Run the AI SMC v3 pipeline where the AI brain is the current chat assistant.

This script demonstrates the "chat as AI brain" wiring:
- OHLCV data is fetched live (Yahoo forex for GBPUSD, Binance USD-M for crypto, Yahoo GC=F for XAUUSD).
- Clean candle charts are rendered.
- The human-AI brain (this chat) has already looked at the chart images and produced a strict
  AISMCTraderBrain decision JSON. That JSON is loaded here and injected into the
  CallableAISMCProvider so the rest of the pipeline (validator, annotation renderer, thesis)
  runs as if a real vision LLM produced it.
- All other gates (consistency validator, trade-readiness guard, official chart renderer,
  thesis writer) run unchanged.

This is observe-only: no execution, no capital risk, no edge claim.
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

from smc_desk.brain.ai_smc_trader_brain import AISMCTraderBrain, REASONING_ORDER, parse_ai_smc_decision
from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest, LLMCompletionResult
from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3
from smc_desk.data.historical_backfill import fetch_historical_closed_ohlcv

from tools.run_live_ai_smc_full_system import (
    load_yahoo_forex_timeframes,
    load_yahoo_xau_timeframes,
    load_binance_usdm_timeframes,
    binance_page_fetcher,
    normalize_symbol,
    is_forex_pair,
    format_price,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, help="Symbol e.g. GBPUSD, BTCUSDT, XAUUSD")
    parser.add_argument("--decision-file", required=True, help="Path to a JSON file containing the AI brain decision payload.")
    parser.add_argument("--output-root", default="analysis_runs")
    parser.add_argument("--allow-shallow-context", action="store_true")
    args = parser.parse_args()

    symbol = normalize_symbol(args.symbol)
    decision_path = Path(args.decision_file)
    if not decision_path.exists():
        raise SystemExit(f"Decision file not found: {decision_path}")
    brain_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    validate_brain_payload(brain_payload, symbol)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(args.output_root).expanduser().resolve() / f"CHAT_AI_BRAIN_{symbol}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    symbol_root = root / symbol
    symbol_root.mkdir(parents=True, exist_ok=True)

    # 1. Fetch live OHLCV.
    if symbol.endswith("USDT") and symbol != "XAUUSDT":
        timeframe_dfs, source_manifest = load_binance_usdm_timeframes(symbol)
    elif symbol == "XAUUSD":
        timeframe_dfs, source_manifest = load_yahoo_xau_timeframes()
    elif is_forex_pair(symbol):
        timeframe_dfs, source_manifest = load_yahoo_forex_timeframes(symbol)
    else:
        raise SystemExit(f"Unsupported symbol: {args.symbol}")

    # 2. Build the chat-AI provider.
    provider = CallableAISMCProvider(
        completion_fn=lambda request, payload=brain_payload: payload,
        provider_name="chat_assistant_ai_brain",
        model_name="this_chat_with_vision",
        is_stub=False,
    )

    # 3. Run the full WP-0035 pipeline with the chat-AI decision injected.
    result = run_ai_smc_orchestrator_v3(
        symbol=symbol,
        timeframe_dfs=timeframe_dfs,
        provider=provider,
        output_dir=symbol_root,
        detector_candidates=None,
        session_context={
            "source_manifest": source_manifest,
            "chat_ai_brain": True,
            "decision_source_file": str(decision_path),
        },
        enforce_minimum_depth=not args.allow_shallow_context,
    )

    summary = {
        "schema": "chat_ai_brain_run_v1",
        "symbol": symbol,
        "status": result.status,
        "official_state": result.report.get("official_state"),
        "validation_result": result.report.get("validation_result"),
        "hard_issues": result.report.get("hard_issues", []),
        "soft_issues": result.report.get("soft_issues", []),
        "provider": result.report.get("provider"),
        "is_real_reasoning": result.report.get("is_real_reasoning"),
        "source_manifest": source_manifest,
        "output_dir": str(symbol_root),
        "official_chart": result.report.get("official_chart"),
        "thesis_path": str(symbol_root / "15_ai_thesis" / "thesis.md"),
        "last_prices": {tf: float(df["close"].iloc[-1]) for tf, df in timeframe_dfs.items()},
        "last_timestamps": {tf: str(df["timestamp"].iloc[-1]) for tf, df in timeframe_dfs.items()},
        "brain_decision_file": str(decision_path),
    }
    summary_path = root / "chat_ai_brain_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


def validate_brain_payload(payload: dict[str, Any], symbol: str) -> None:
    """Validate the chat-AI brain decision against the strict AISMCTraderBrain schema."""
    payload_symbol = str(payload.get("symbol", "")).upper()
    if payload_symbol and payload_symbol != symbol:
        raise SystemExit(f"Decision symbol {payload_symbol!r} does not match run symbol {symbol!r}.")
    # Use the same Pydantic schema the validator will use.
    parse_ai_smc_decision(payload)


if __name__ == "__main__":
    main()
