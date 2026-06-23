#!/usr/bin/env python3
"""Mark any chart with clean, confidence-gated SMC annotations — one command.

  # historical window from the local Binance CSVs:
  python3 tools/mark_chart.py --symbol BTCUSDT --source csv --start 60000 --n 140

  # LIVE chart, fetched through kimi-webbridge (the browser reaches Binance; the sandbox can't):
  python3 tools/mark_chart.py --symbol BTCUSDT --source live --n 200 --min-conf high

Output is a dark, TradingView-style PNG drawn 100% in Python from the OHLCV, with only the
heuristically scored high- (and optionally medium-) confidence objects marked. Visual quality
and salience are not evidence of real-market accuracy; that requires adjudicated gold labels.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.perception_panel import analysis_to_objects
from smc_desk.render import render_smc_annotated
from smc_desk.rules import load_rule_config

BRIDGE = "http://127.0.0.1:10086/command"


def _bridge(action: str, args: dict, session: str = "mark") -> dict:
    body = json.dumps({"action": action, "args": args, "session": session}).encode()
    req = urllib.request.Request(BRIDGE, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def require_healthy_bridge() -> None:
    binary = Path.home() / ".kimi-webbridge/bin/kimi-webbridge"
    result = subprocess.run([str(binary), "status"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Kimi WebBridge health check failed: {result.stderr.strip() or result.stdout.strip()}")
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Kimi WebBridge returned unreadable status: {result.stdout.strip()}") from exc
    if not status.get("running") or not status.get("extension_connected"):
        raise SystemExit("Kimi WebBridge is not ready; start the daemon and connect the browser extension first.")


def drop_unclosed_candles(df: pd.DataFrame, interval: str, now: datetime | None = None) -> pd.DataFrame:
    seconds = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
    if interval not in seconds:
        raise ValueError(f"Unsupported live interval for closed-candle validation: {interval}")
    reference = pd.Timestamp(now or datetime.now(timezone.utc))
    if reference.tzinfo is None:
        reference = reference.tz_localize("UTC")
    else:
        reference = reference.tz_convert("UTC")
    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    closed = timestamps + pd.Timedelta(seconds=seconds[interval]) <= reference
    return df.loc[closed].reset_index(drop=True)


def bridge_value(response: dict[str, Any], action: str) -> Any:
    """Return a WebBridge evaluation value with an actionable failure message."""
    if response.get("ok") is False:
        raise RuntimeError(f"Kimi WebBridge {action} failed: {response}")
    try:
        return response["data"]["value"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Kimi WebBridge {action} returned no usable value: {response}") from exc


def validate_live_ohlcv(df: pd.DataFrame) -> None:
    """Reject malformed exchange responses before the engine can analyze them."""
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in df]
    if missing or df.empty:
        raise ValueError(f"Live OHLCV is empty or missing columns: {', '.join(missing) or 'no rows'}")
    if not df["timestamp"].is_monotonic_increasing or df["timestamp"].duplicated().any():
        raise ValueError("Live OHLCV timestamps must be strictly ordered and unique.")
    numeric = df[["open", "high", "low", "close", "volume"]]
    if numeric.isna().any().any() or not numeric.apply(lambda column: pd.api.types.is_numeric_dtype(column)).all():
        raise ValueError("Live OHLCV contains missing or non-numeric price/volume values.")
    if (numeric[["open", "high", "low", "close"]] <= 0).any().any() or (numeric["volume"] < 0).any():
        raise ValueError("Live OHLCV contains non-positive prices or negative volume.")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any() or (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Live OHLCV violates candle high/low consistency.")


def fetch_live(symbol: str, interval: str, limit: int, session: str) -> pd.DataFrame:
    """Fetch live Binance futures klines via the kimi-webbridge browser."""
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    _bridge("navigate", {"url": url, "newTab": True, "group_title": "SMC Mark"}, session=session)
    code = ("(function(){var k=JSON.parse(document.body.innerText);"
            "return JSON.stringify(k.map(function(c){return [c[0],c[1],c[2],c[3],c[4],c[5]];}));})()")
    r = _bridge("evaluate", {"code": code}, session=session)
    rows = json.loads(bridge_value(r, "evaluate"))
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["timestamp"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_localize(None)
    df = drop_unclosed_candles(df[["timestamp", "open", "high", "low", "close", "volume"]], interval).tail(limit).reset_index(drop=True)
    validate_live_ohlcv(df)
    return df


def write_artifacts(output: Path, analysis, df: pd.DataFrame, min_conf: str, source: str) -> None:
    analysis_path = output.with_suffix(".analysis.json")
    objects_path = output.with_suffix(".objects.json")
    analysis_path.write_text(json.dumps(analysis.model_dump(mode="json"), indent=2), encoding="utf-8")
    objects = [item.model_dump(mode="json") for item in analysis_to_objects(analysis, timeframe=analysis.timeframe, df=df)]
    objects_path.write_text(
        json.dumps(
            {
                "provenance": "deterministic_engine_with_heuristic_salience",
                "minimum_display_confidence": min_conf,
                "accuracy_claim": "none; requires independent adjudicated gold labels",
                "unsupported_primitives": ["inducement", "supply", "demand", "breaker", "mitigation_block"],
                "source": source,
                "window": {
                    "start": pd.Timestamp(df["timestamp"].iloc[0]).isoformat(),
                    "end": pd.Timestamp(df["timestamp"].iloc[-1]).isoformat(),
                    "closed_candles_only": source == "live_binance_futures_webbridge",
                    "row_count": len(df),
                },
                "objects": objects,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--source", choices=["csv", "live"], default="csv")
    p.add_argument("--csv", help="OHLCV CSV (default: data/ohlcv/binance_futures/<SYM>/<SYM>_15m_4year.csv)")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--n", type=int, default=140)
    p.add_argument("--interval", default="15m")
    p.add_argument("--min-conf", choices=["low", "medium", "high"], default="high")
    p.add_argument("--rules")
    p.add_argument("--out")
    p.add_argument("--no-swings", action="store_true")
    p.add_argument("--medium-labels", action="store_true", help="Label medium-confidence objects as well as high-confidence ones.")
    p.add_argument("--session", default="smc-mark", help="Kimi WebBridge session name for --source live.")
    p.add_argument("--keep-browser-session", action="store_true", help="Leave the tool-created browser tab group open after a live render.")
    a = p.parse_args()

    try:
        cfg = load_rule_config(a.rules)
        if a.source == "live":
            require_healthy_bridge()
            df = fetch_live(a.symbol, a.interval, a.n + 1, a.session)
            if df.empty:
                raise SystemExit("No closed live candles were returned.")
            tag = "live"
            source = "live_binance_futures_webbridge"
        else:
            csv = a.csv or str(ROOT / f"data/ohlcv/binance_futures/{a.symbol}/{a.symbol}_15m_4year.csv")
            df = load_ohlcv_csv(csv).iloc[a.start:a.start + a.n].reset_index(drop=True)
            tag = str(a.start)
            source = "local_ohlcv_csv"

        res, _ = analyze_dataframe(df=df, symbol=a.symbol, timeframe=a.interval, config=cfg, notes="mark", input_type="ohlcv")
        out = Path(a.out or str(ROOT / f"backtests/perception/marked/{a.symbol}_{tag}_{a.min_conf}.png"))
        out.parent.mkdir(parents=True, exist_ok=True)
        render_smc_annotated(df, res, str(out), config=cfg, min_conf=a.min_conf, show_swings=not a.no_swings,
                             show_medium_labels=a.medium_labels,
                             title=f"{a.symbol} {a.interval} — SMC ({a.min_conf}+){'  LIVE' if a.source=='live' else ''}")
        write_artifacts(out, res, df, a.min_conf, source)
        print(f"window: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}  | last px {df['close'].iloc[-1]:.2f}")
        print(f"engine verdict: {res.trade_plan.verdict}  bias: {res.trade_plan.direction}")
        print(f"wrote {out}")
        print(f"wrote {out.with_suffix('.analysis.json')} and {out.with_suffix('.objects.json')}")
    finally:
        if a.source == "live" and not a.keep_browser_session:
            try:
                _bridge("close_session", {}, session=a.session)
            except Exception as exc:  # Do not replace a data/render failure with cleanup noise.
                print(f"warning: could not close Kimi WebBridge session {a.session!r}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
