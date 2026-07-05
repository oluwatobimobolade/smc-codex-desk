#!/usr/bin/env python3
"""Export a complete review packet for an external AI agent.

Usage:
    python tools/run_export_agent_packet.py --symbol BTCUSDT \\
        --output-root analysis_runs/AGENT_PACKET_BTCUSDT_*

The system fetches live data, builds the evidence pack, renders clean charts,
and exports a packet directory. The external AI agent (Codex, Gemini Antigravity,
ChatGPT, Kimi, etc.) reviews the packet and writes a response directory.

Then use tools/run_import_agent_response.py to import the response and run
the full validation + rendering pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smc_desk.brain.agent_handoff.export_agent_packet import export_agent_packet
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack as build_ai_smc_evidence_pack
from smc_desk.data.historical_backfill import fetch_historical_closed_ohlcv

from tools.run_live_ai_smc_full_system import (
    binance_page_fetcher,
    is_forex_pair,
    load_binance_usdm_timeframes,
    load_yahoo_forex_timeframes,
    load_yahoo_xau_timeframes,
    normalize_symbol,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--output-root", default="analysis_runs")
    parser.add_argument("--allow-shallow-context", action="store_true")
    args = parser.parse_args()

    symbol = normalize_symbol(args.symbol)
    if symbol.endswith("USDT") and symbol != "XAUUSDT":
        timeframe_dfs, _ = load_binance_usdm_timeframes(symbol)
    elif symbol == "XAUUSD":
        timeframe_dfs, _ = load_yahoo_xau_timeframes()
    elif is_forex_pair(symbol):
        timeframe_dfs, _ = load_yahoo_forex_timeframes(symbol)
    else:
        raise SystemExit(f"Unsupported symbol: {args.symbol}")

    evidence_pack = build_ai_smc_evidence_pack(
        symbol=symbol,
        timeframe_dfs=timeframe_dfs,
        embed_images=False,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(args.output_root).expanduser().resolve() / f"AGENT_PACKET_{symbol}_{stamp}"
    packet_dir = root / "ai_agent_packet"
    chart_paths: dict[str, Path] = {}
    for tf in ("1d", "4h", "1h", "15m", "5m"):
        chart_dir = root / "ai_agent_packet" / "charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        chart_path = chart_dir / f"clean_{tf}_chart.png"
        if tf in timeframe_dfs:
            from smc_desk.rendering.clean_mtf_chart_pack import render_clean_candle_chart
            render_clean_candle_chart(timeframe_dfs[tf], chart_path, timeframe=tf, symbol=symbol)
            if chart_path.exists():
                chart_paths[tf] = chart_path

    manifest = export_agent_packet(
        symbol=symbol,
        evidence_pack=evidence_pack,
        chart_paths=chart_paths,
        output_dir=packet_dir,
    )

    summary = {
        "schema": "agent_packet_export_v1",
        "symbol": symbol,
        "packet_dir": str(packet_dir),
        "manifest": manifest,
    }
    summary_path = root / "packet_export_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
