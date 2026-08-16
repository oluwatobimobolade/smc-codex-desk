#!/usr/bin/env python
"""Turn stored history into a POI case library, then answer a live zone from it.

    build_poi_case_library.py build --candles PATH --symbol SYM [--bars N] --out FILE
    build_poi_case_library.py ask   --library FILE --candles PATH --symbol SYM

`build` walks the history, records every order block with the features knowable
at its formation, and resolves what price then did about it. `ask` featurizes the
POIs on the latest bar and answers each from its historical analogues.

Observe-only. A retrieved distribution describes the past. It creates no signal,
paper, or live authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smc_desk.colleague.run_context import dataframe_to_candles  # noqa: E402
from smc_desk.evaluation.poi_outcomes import (  # noqa: E402
    PoiCase,
    featurize,
    resolve_outcome,
    retrieve_analogues,
)
from smc_desk.perception.engine_v2 import PerceptionEngineV2  # noqa: E402
from smc_desk.perception.significance import average_true_range  # noqa: E402

SWEEP_LOOKBACK = 12   # bars before formation searched for a liquidity sweep
IMBALANCE_LOOKAHEAD = 3  # bars after formation in which a departure gap may appear


def _snapshot(frame: pd.DataFrame, symbol: str, timeframe: str, session: str) -> dict:
    candles = dataframe_to_candles(
        frame, venue="LIB", instrument=symbol, timeframe=timeframe, session_profile=session
    )
    return PerceptionEngineV2().analyze(candles, candles[-1].close_time).model_dump(mode="json")


def _index_by_time(frame: pd.DataFrame) -> dict:
    stamps = pd.to_datetime(frame["timestamp"], utc=True)
    return {stamp: i for i, stamp in enumerate(stamps)}


def build(args) -> int:
    frame = pd.read_csv(args.candles)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").tail(args.bars).reset_index(drop=True)
    print(f"{args.symbol} {args.timeframe}: {len(frame)} candles "
          f"{frame['timestamp'].iloc[0]} -> {frame['timestamp'].iloc[-1]}")

    snap = _snapshot(frame, args.symbol, args.timeframe, args.session)
    position = _index_by_time(frame)
    obs = [o for o in (snap.get("order_blocks") or []) if isinstance(o, dict)]
    print(f"order blocks detected: {len(obs)}")

    # Sweep and FVG bar indices, used as formation-context features.
    sweep_bars = set()
    for s in snap.get("sweeps") or []:
        idx = position.get(pd.Timestamp(s.get("confirmed_at") or s.get("pivot_time") or 0, tz="UTC"))
        if idx is not None:
            sweep_bars.add(idx)
    fvg_bars = set()
    for g in snap.get("fvgs") or []:
        idx = position.get(pd.Timestamp(g.get("confirmed_at") or 0, tz="UTC"))
        if idx is not None:
            fvg_bars.add(idx)

    records = frame.to_dict("records")
    atr_all = average_true_range(records)
    range_low = float(frame["low"].min())
    range_high = float(frame["high"].max())

    cases: list[PoiCase] = []
    for ob in obs:
        stamp = ob.get("confirmed_at") or ob.get("pivot_time")
        if not stamp:
            continue
        formed = position.get(pd.Timestamp(stamp).tz_convert("UTC"))
        if formed is None:
            continue
        direction = str(ob.get("direction") or "").lower()
        if direction not in {"bullish", "bearish"}:
            continue

        swept = any(b in sweep_bars for b in range(max(0, formed - SWEEP_LOOKBACK), formed + 1))
        imbalance = any(b in fvg_bars for b in range(formed, formed + IMBALANCE_LOOKAHEAD + 1))

        features = featurize(
            ob, atr=atr_all, range_low=range_low, range_high=range_high,
            swept_before=swept, left_imbalance=imbalance,
        )
        outcome, bars_to_return, r = resolve_outcome(
            frame, formed_index=formed, direction=direction, atr=atr_all,
            price_low=float(ob.get("price_low") or 0.0),
            price_high=float(ob.get("price_high") or 0.0),
        )
        cases.append(PoiCase(
            case_id=f"{args.symbol}:{args.timeframe}:{ob.get('object_id')}",
            symbol=args.symbol, timeframe=args.timeframe, direction=direction,
            formed_index=formed,
            price_low=float(ob.get("price_low") or 0.0),
            price_high=float(ob.get("price_high") or 0.0),
            features=features, outcome=outcome,
            bars_to_return=bars_to_return, r_achieved=r,
        ))

    from collections import Counter
    tally = Counter(c.outcome for c in cases)
    print(f"cases: {len(cases)}  {json.dumps(dict(tally))}")

    existing = []
    if args.out.exists() and args.append:
        existing = json.loads(args.out.read_text(encoding="utf-8")).get("cases") or []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "schema": "poi_case_library_v1",
        "authority": "descriptive_historical_only_no_signal",
        "cases": existing + [c.to_dict() for c in cases],
    }, indent=1), encoding="utf-8")
    print(f"wrote {args.out} ({len(existing) + len(cases)} total cases)")
    return 0


def ask(args) -> int:
    payload = json.loads(args.library.read_text(encoding="utf-8"))
    library = [
        PoiCase(
            case_id=c["case_id"], symbol=c["symbol"], timeframe=c["timeframe"],
            direction=c["direction"], formed_index=c["formed_index"],
            price_low=c["price_low"], price_high=c["price_high"],
            features=c["features"], outcome=c["outcome"],
            bars_to_return=c.get("bars_to_return"), r_achieved=c.get("r_achieved"),
        )
        for c in payload.get("cases") or []
    ]
    print(f"library: {len(library)} cases")

    frame = pd.read_csv(args.candles)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").tail(args.bars).reset_index(drop=True)
    snap = _snapshot(frame, args.symbol, args.timeframe, args.session)
    records = frame.to_dict("records")
    atr = average_true_range(records)
    range_low, range_high = float(frame["low"].min()), float(frame["high"].max())
    price = float(frame["close"].iloc[-1])

    obs = [o for o in (snap.get("order_blocks") or []) if isinstance(o, dict)]
    # Only zones price has not already passed through are actionable.
    live = []
    for ob in obs:
        lo, hi = sorted((float(ob.get("price_low") or 0), float(ob.get("price_high") or 0)))
        direction = str(ob.get("direction") or "").lower()
        if direction == "bearish" and lo <= price:
            continue
        if direction == "bullish" and hi >= price:
            continue
        live.append((ob, lo, hi, direction))

    print(f"\n{args.symbol} {args.timeframe}  price {price:,.2f}  "
          f"{len(live)} untouched zones ahead of price\n")
    rows = []
    for ob, lo, hi, direction in live:
        features = featurize(ob, atr=atr, range_low=range_low, range_high=range_high)
        report = retrieve_analogues(features, library, direction=direction, k=args.k)
        rows.append((abs((lo + hi) / 2 - price), ob, lo, hi, direction, report))

    for _, ob, lo, hi, direction, report in sorted(rows, key=lambda r: r[0]):
        rate = report.rejection_rate
        ret = report.return_rate
        print(f"  {direction:8s} {lo:11,.2f} - {hi:11,.2f}")
        if rate is None:
            print(f"      {report.notes[0] if report.notes else 'no comparable history'}")
        else:
            print(f"      analogues={report.matched}  came back={ret:.0%}  "
                  f"held when it did={rate:.0%}  median R={report.median_r}  "
                  f"(rejected {report.rejected} / broke {report.broke} / never returned {report.never_returned})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("build", "ask"):
        p = sub.add_parser(name)
        p.add_argument("--candles", required=True, type=Path)
        p.add_argument("--symbol", required=True)
        p.add_argument("--timeframe", default="15m")
        p.add_argument("--session", default="continuous")
        p.add_argument("--bars", type=int, default=20_000)
        if name == "build":
            p.add_argument("--out", required=True, type=Path)
            p.add_argument("--append", action="store_true")
        else:
            p.add_argument("--library", required=True, type=Path)
            p.add_argument("--k", type=int, default=40)
    args = parser.parse_args()
    return build(args) if args.cmd == "build" else ask(args)


if __name__ == "__main__":
    raise SystemExit(main())
