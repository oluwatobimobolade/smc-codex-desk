#!/usr/bin/env python3
"""Live dual-lens analysis: fresh data -> engine -> (vision) -> reconcile -> case.

STATUS: COMPARISON_ONLY (WP-0043, GATE-CANONICAL-RUNTIME-001).

This tool is retained for historical evidence and side-by-side comparison
with the canonical AI SMC V3 path (``python -m smc_desk.colleague`` /
``tools/run_live_ai_smc_full_system.py``). It imports the legacy
``smc_desk.engine`` and ``smc_desk.rules`` modules and therefore must NOT be
treated as canonical authority.

One command runs the whole loop for a single live decision:

1. Pull fresh OHLCV from the venue (seconds).
2. Run the deterministic engine -> the authoritative plan (levels, POI, verdict).
3. Load a vision read if provided (produced by an AI looking at the live chart,
   e.g. captured via Kimi WebBridge). Optional — engine-only still works.
4. Reconcile the two lenses -> agreement score + combined confidence.
5. Save a timestamped case folder (engine analysis + reconciliation + summary).

The vision step is the clean plug-in point: today you pass a vision_read.json
written by a human/AI looking at the chart; later Kimi WebBridge captures the
chart and a vision model fills the same schema automatically. The reconciler
does not care who produced the vision read.

Usage:
    python3 tools/analyze_live_dual_lens.py --symbol BTCUSDT --provider binance_futures --days 20
    python3 tools/analyze_live_dual_lens.py --symbol BTCUSD --provider bitstamp --market btcusd --vision path/to/vision_read.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.dual_lens import reconcile, render_markdown
from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.mtf import build_mtf_snapshot, derive_htf_consensus_bias, snapshot_to_dict
from smc_desk.rules import load_rule_config
from tools.download_binance_futures_ohlcv import (
    INTERVAL_SECONDS as BINANCE_INTERVAL_SECONDS,
    download_ohlcv as download_binance_futures_ohlcv,
    write_csv as write_binance_futures_csv,
)
from tools.download_bitstamp_ohlcv import download_ohlcv as download_bitstamp_ohlcv
from tools.download_bitstamp_ohlcv import write_csv as write_bitstamp_csv


def normalize_binance_futures_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def drop_unclosed_candles(df: pd.DataFrame, now: datetime, step_seconds: int) -> pd.DataFrame:
    """Keep only candles whose full interval has closed by ``now``.

    Venue candles are normally timestamped at candle open. A 12:30 candle is
    still unclosed at 12:42 even though its timestamp sits exactly on a 15m
    boundary, so boundary checks are not enough.
    """
    if df.empty:
        return df.copy()

    timestamps = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")

    close_times = timestamps + pd.Timedelta(seconds=step_seconds)
    closed = close_times <= now_ts
    return df.loc[closed].reset_index(drop=True)


def _zone_dict(zone: Any) -> dict[str, Any] | None:
    if zone is None:
        return None
    return {
        "label": zone.label, "kind": zone.kind, "direction": zone.direction,
        "low": zone.low, "high": zone.high, "status": zone.status, "score": zone.score,
    }


def engine_analysis_dict(result: Any) -> dict[str, Any]:
    plan = result.trade_plan
    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "input_type": result.input_type,
        "generated_at": result.generated_at,
        "metrics": result.metrics,
        "trade_plan": {
            "direction": plan.direction, "verdict": plan.verdict, "setup_grade": plan.setup_grade,
            "risk_pct": plan.risk_pct, "confluence_score": plan.confluence_score, "confidence": plan.confidence,
            "entry_low": plan.entry_low, "entry_high": plan.entry_high,
            "structural_invalidation": plan.structural_invalidation,
            "execution_invalidation": plan.execution_invalidation,
            "invalidation": plan.invalidation,
            "stop_buffer": plan.stop_buffer,
            "stop_buffer_atr": plan.stop_buffer_atr,
            "stop_quality": plan.stop_quality,
            "targets": plan.targets, "risk_reward": plan.risk_reward, "liquidity_target": plan.liquidity_target,
            "checklist": dict(plan.checklist), "selected_poi": _zone_dict(plan.selected_poi),
            "selected_htf_poi": (
                {
                    "timeframe": plan.selected_htf_poi.timeframe,
                    "state": plan.selected_htf_poi.state,
                    "distance_atr": plan.selected_htf_poi.distance_atr,
                    "rank": plan.selected_htf_poi.rank,
                    "zone": _zone_dict(plan.selected_htf_poi.zone),
                }
                if plan.selected_htf_poi
                else None
            ),
            "thesis": plan.thesis, "warnings": plan.warnings, "conditions": plan.conditions,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Live dual-lens (engine + vision) SMC analysis.")
    p.add_argument("--symbol", required=True, help="e.g. BTCUSDT for Binance futures, BTCUSD for Bitstamp legacy.")
    p.add_argument("--provider", choices=["binance_futures", "bitstamp", "csv"], default="binance_futures")
    p.add_argument("--ohlcv", help="Use an existing live/recent OHLCV CSV instead of downloading from a provider.")
    p.add_argument("--market", help="Venue market override. Binance example: BTCUSDT. Bitstamp example: btcusd.")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--step", type=int, default=900, help="Candle seconds (900=15m).")
    p.add_argument("--days", type=int, default=20, help="How many days of fresh history to pull.")
    p.add_argument("--rules")
    p.add_argument("--bias", help="Optional bias hint: bullish or bearish.")
    p.add_argument("--vision", help="Optional path to a vision_read.json.")
    p.add_argument("--output-dir", help="Defaults to case_library/<SYMBOL>/<ts>_live_dual.")
    p.add_argument(
        "--max-candle-age-minutes",
        type=float,
        default=120.0,
        help="Protect live reads: fail if the latest closed candle is older than this unless --allow-stale is set.",
    )
    p.add_argument("--allow-stale", action="store_true", help="Allow archive-only/stale data for research, never for live trade calls.")
    args = p.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    provider = "csv" if args.ohlcv else args.provider

    if args.ohlcv:
        symbol = normalize_binance_futures_symbol(args.symbol)
        market = args.market or symbol
        step_seconds = BINANCE_INTERVAL_SECONDS.get(args.timeframe, args.step)
        rows = None
        write_csv_fn = None
        venue = "CSV OHLCV"
        data_mode = "provided_csv"
        print(f"Using provided OHLCV CSV for {symbol}: {args.ohlcv}")
    elif provider == "binance_futures":
        symbol = normalize_binance_futures_symbol(args.symbol)
        market = normalize_binance_futures_symbol(args.market or symbol)
        step_seconds = BINANCE_INTERVAL_SECONDS.get(args.timeframe, args.step)
        print(f"Pulling {symbol} {args.timeframe} from Binance USD-M Futures ({args.days}d, archive + optional REST tail)...")
        rows = download_binance_futures_ohlcv(
            symbol=market,
            interval=args.timeframe,
            start=start,
            end=end,
            sleep_seconds=0.03,
            retries=4,
            retry_delay=1.5,
            allow_missing=True,
            tail_rest=True,
            require_rest_tail=False,
        )
        write_csv_fn = write_binance_futures_csv
        venue = "Binance USD-M Futures"
        data_mode = "archive_plus_optional_rest_tail"
    else:
        symbol = args.symbol.upper().replace("/", "").replace("-", "")
        market = (args.market or args.symbol).lower().replace("/", "").replace("-", "")
        step_seconds = args.step
        print(f"Pulling {symbol} {args.timeframe} from Bitstamp ({args.days}d)...")
        rows = download_bitstamp_ohlcv(market=market, step=step_seconds, start=start, end=end, sleep_seconds=0.15)
        write_csv_fn = write_bitstamp_csv
        venue = "Bitstamp"
        data_mode = "rest_paginated"

    if args.ohlcv:
        raw_row_count = 0
    elif not rows:
        raise SystemExit("No data returned from venue.")
    else:
        raw_row_count = len(rows)

    ts = end.strftime("%Y%m%d_%H%M")
    out_dir = Path(args.output_dir) if args.output_dir else ROOT / "case_library" / symbol.upper() / f"{ts}_live_dual"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{symbol}_{args.timeframe}_live.csv"
    if args.ohlcv:
        provided_path = Path(args.ohlcv)
        csv_path.write_text(provided_path.read_text(encoding="utf-8"), encoding="utf-8")
        raw_row_count = len(pd.read_csv(csv_path))
    else:
        write_csv_fn(csv_path, rows)

    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(str(csv_path))
    df = drop_unclosed_candles(df, now=end, step_seconds=step_seconds)
    if df.empty:
        raise SystemExit("No fully closed candles remained after dropping unclosed data.")
    df.to_csv(csv_path, index=False)
    closed_row_count = len(df)
    latest_open = pd.Timestamp(df["timestamp"].iloc[-1])
    if latest_open.tzinfo is None:
        latest_open = latest_open.tz_localize("UTC")
    else:
        latest_open = latest_open.tz_convert("UTC")
    latest_close = latest_open + pd.Timedelta(seconds=step_seconds)
    age_minutes = max(0.0, (pd.Timestamp(end) - latest_close).total_seconds() / 60)
    if age_minutes > args.max_candle_age_minutes and not args.allow_stale:
        raise SystemExit(
            f"Latest closed candle is too stale for a live read: opened {latest_open.isoformat()}, "
            f"closed {latest_close.isoformat()}, age {age_minutes:.1f} minutes. "
            "REST tail may be unavailable. Re-run with --allow-stale only for research/no-signal review."
        )

    # MTF: resample 15m -> 1H/4H/1D, read each bias, get alignment, anchor the
    # engine to the 1H bias (same convention as the backtester) so the live
    # read is not myopic to the execution timeframe.
    decision_time = df["timestamp"].iloc[-1]
    mtf_snapshot = build_mtf_snapshot(df, decision_time, config)
    snap = snapshot_to_dict(mtf_snapshot)
    htf_bias = derive_htf_consensus_bias(snap)
    bias_hint = args.bias or (htf_bias if htf_bias in ("bullish", "bearish") else None)

    result, _df = analyze_dataframe(
        df=df, symbol=symbol, timeframe=args.timeframe,
        config=config, bias_hint=bias_hint, notes="live dual-lens + MTF", input_type="ohlcv",
        htf_poi=mtf_snapshot.selected_htf_poi,
    )
    engine = engine_analysis_dict(result)
    engine["mtf"] = snap
    engine["source"] = {
        "provider": provider,
        "venue": venue,
        "market": market,
        "data_mode": data_mode,
        "csv_path": str(csv_path),
        "downloaded_at": end.isoformat(),
        "decision_time": pd.Timestamp(decision_time).isoformat(),
        "latest_candle_open": latest_open.isoformat(),
        "latest_candle_close": latest_close.isoformat(),
        "latest_candle_age_minutes": round(age_minutes, 2),
        "raw_rows_downloaded": raw_row_count,
        "closed_rows_used": closed_row_count,
        "dropped_unclosed_rows": raw_row_count - closed_row_count,
        "candle_step_seconds": step_seconds,
        "unclosed_candle_rule": "Use only rows where candle_open + step <= downloaded_at.",
    }
    (out_dir / "engine_analysis.json").write_text(json.dumps(engine, indent=2, default=str), encoding="utf-8")

    plan = engine["trade_plan"]
    print(f"\nMTF -> 1H {snap['1h']['bias']} / 4H {snap['4h']['bias']} / 1D {snap['1d']['bias']} "
          f"| execution consensus {snap['execution_consensus']}  bias->engine: {bias_hint}")
    print(f"ENGINE: {plan['verdict']} (grade {plan['setup_grade']}) · {plan['direction']} · "
          f"confluence {plan['confluence_score']} · last close {engine['metrics'].get('latest_close')}")

    # Near-miss surfacing: show top failed checklist items
    checklist = plan.get("checklist", {})
    failed = [k for k, v in checklist.items() if not v]
    if failed and plan["verdict"] != "Execute":
        print(f"\nNear-miss: {len(failed)} checklist items failed:")
        for item in failed[:3]:
            print(f"  - {item.replace('_', ' ')}")
        if len(failed) > 3:
            print(f"  ... and {len(failed) - 3} more")

    if args.vision:
        vision = json.loads(Path(args.vision).read_text(encoding="utf-8"))
        recon = reconcile(engine, vision)
        recon.update({"symbol": symbol, "timeframe": args.timeframe, "decision_time": pd.Timestamp(decision_time).isoformat()})
        (out_dir / "reconciliation.json").write_text(json.dumps(recon, indent=2), encoding="utf-8")
        md = render_markdown(recon, symbol=symbol, timeframe=args.timeframe)
        (out_dir / "reconciliation.md").write_text(md, encoding="utf-8")
        print("\n" + md)
    else:
        print("\nNo vision read supplied (engine-only). To complete the dual lens:")
        print("  1. Capture the live chart with Kimi WebBridge.")
        print("  2. Have a vision model fill a vision_read.json (see dual_lens.VisionRead).")
        print(f"  3. Re-run with --vision <file> or reconcile against {out_dir/'engine_analysis.json'}.")

    print(f"\nSaved case to {out_dir}")


if __name__ == "__main__":
    main()
