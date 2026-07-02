"""One-off WP-0035 AVAXUSDT analysis runner."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests

from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.data.historical_backfill import MINIMUM_CONTEXT_DEPTH, fetch_historical_closed_ohlcv
from smc_desk.session import summarize_session_context


BASE_URL = "https://fapi.binance.com"
SYMBOL = "AVAXUSDT"
OUTPUT = Path("/Users/tobimobolade/smc-codex-desk/analysis_runs/WP0035_AVAXUSDT_LIVE_20260629")


def _http_json(url: str, timeout: float = 20.0):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _server_time() -> int:
    return int(_http_json(f"{BASE_URL}/fapi/v1/time")["serverTime"])


def _fetch_page(symbol: str, interval: str, limit: int, end_time_ms: int | None) -> tuple[list, int]:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if end_time_ms is not None:
        params["endTime"] = int(end_time_ms)
    url = f"{BASE_URL}/fapi/v1/klines?{urlencode(params)}"
    time.sleep(0.25)  # be polite
    rows = _http_json(url)
    server_time = _server_time()
    return rows, server_time


def fetch_tf(interval: str, required: int | None = None) -> pd.DataFrame:
    result = fetch_historical_closed_ohlcv(
        symbol=SYMBOL,
        interval=interval,
        required_candles=required or MINIMUM_CONTEXT_DEPTH.get(interval, 1500),
        fetcher=_fetch_page,
        cache_dir=OUTPUT / "data" / interval,
    )
    df = result.dataframe
    print(f"[{interval}] fetched {len(df)} rows from {result.manifest['page_count']} pages "
          f"({df['timestamp'].min()} -> {df['timestamp'].max()})")
    return df


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    # Fetch all timeframes
    timeframe_dfs = {
        "15m": fetch_tf("15m"),
        "1h": fetch_tf("1h"),
        "4h": fetch_tf("4h"),
        "1d": fetch_tf("1d"),
    }

    # Build session context from 15m
    session_context = summarize_session_context(timeframe_dfs["15m"])
    print("Session context:", json.dumps(session_context, default=str, indent=2))

    # Build detector candidates from simple heuristics (placeholder; real detectors would run here)
    # For this run, we pass empty candidates so the AI must rely on chart images + OHLCV.
    detector_candidates = {}

    # Build evidence pack
    evidence_pack = build_smc_evidence_pack(
        symbol=SYMBOL,
        timeframe_dfs=timeframe_dfs,
        chart_images=None,  # orchestrator will render
        detector_candidates=detector_candidates,
        session_context=session_context,
        doctrine_notes=["WP-0035 AVAXUSDT live analysis"],
    )

    # Write evidence pack for inspection
    (OUTPUT / "00_evidence_pack").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "00_evidence_pack" / "evidence_pack.json").write_text(
        json.dumps(evidence_pack, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    print(f"Evidence pack written to {OUTPUT / '00_evidence_pack'}")
    print(f"Active range authority: {json.dumps(evidence_pack['active_range_authority'], indent=2, default=str)}")

    # At this point, a real AI would reason over the evidence pack and chart images.
    # For this runner, we pause and emit the evidence summary so the operator can decide.
    print("\n=== EVIDENCE PACK READY ===")
    print(f"Output directory: {OUTPUT}")
    print("Next: generate AISMCDecision JSON and re-run with ManualJSONProvider.")


if __name__ == "__main__":
    main()
