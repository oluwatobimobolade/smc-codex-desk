#!/usr/bin/env python3
"""Assemble a perception anchor batch: diverse source-aligned windows, each rendered as a
clean chart + the engine's object list, for independent vision adjudication.

This produces the inputs for the FIRST real engine-vs-independent-expert agreement check
and for confidence calibration. Vision labels are gestalt/salient (an AI expert), so we
adjudicate at the salient-object level, not sub-0.1% price tolerance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.perception_panel import analysis_to_objects, _atr, _dealing_range, _event_significance, _zone_significance
from smc_desk.render import render_raw_chart
from smc_desk.rules import load_rule_config

DATA = ROOT / "data/ohlcv/binance_futures"
WINDOWS = [
    ("BTC_w1", DATA / "BTCUSDT/BTCUSDT_15m_4year.csv", 20000, 140),
    ("ETH_w1", DATA / "ETHUSDT/ETHUSDT_15m_4year.csv", 40000, 140),
    ("SOL_w1", DATA / "SOLUSDT/SOLUSDT_15m_4year.csv", 70000, 140),
    ("XRP_w1", DATA / "XRPUSDT/XRPUSDT_15m_4year.csv", 100000, 140),
]


def main() -> None:
    cfg = load_rule_config()
    out = ROOT / "backtests/perception/anchor_20260622"
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, csv, start, n in WINDOWS:
        df = load_ohlcv_csv(str(csv)).iloc[start:start + n].reset_index(drop=True)
        res, _ = analyze_dataframe(df=df, symbol=name, timeframe="15m", config=cfg, notes="anchor", input_type="ohlcv")
        png = out / f"{name}.png"
        render_raw_chart(df, name, "15m", str(png))
        atr = _atr(df); dr = _dealing_range(res, atr)
        objs = []
        for e in res.events:
            if e.label in ("BOS", "CHoCH", "Liquidity Sweep"):
                objs.append({"kind": e.label, "dir": e.direction, "time": e.timestamp[5:16],
                             "scope": e.structure_scope, "sig": round(_event_significance(e, df, atr, dr), 2)})
        for z in res.zones:
            if z.kind in ("fvg", "order_block") or z.label in ("Equal Highs", "Equal Lows"):
                objs.append({"kind": z.label, "dir": z.direction, "zone": f"{z.low:.0f}-{z.high:.0f}",
                             "status": z.status, "sig": round(_zone_significance(z, atr, dr), 2)})
        objs.sort(key=lambda o: o["sig"], reverse=True)
        (out / f"{name}.objects.json").write_text(json.dumps(objs, indent=2))
        manifest.append({"name": name, "window": f"{df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}",
                         "last_px": float(df["close"].iloc[-1]), "n_objects": len(objs), "png": str(png)})
        print(f"\n=== {name}  {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}  px={df['close'].iloc[-1]:.2f} ===")
        print(f"  engine objects: {len(objs)} (top by significance)")
        for o in objs[:12]:
            loc = o.get("time") or o.get("zone")
            print(f"    sig={o['sig']:.2f}  {o['kind']:<16} {o['dir']:<8} {loc}  {o.get('scope') or o.get('status','')}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {out}/  ({len(manifest)} windows)")


if __name__ == "__main__":
    main()
