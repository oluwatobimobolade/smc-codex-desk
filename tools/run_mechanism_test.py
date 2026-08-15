#!/usr/bin/env python
"""Run a preregistered mechanism hypothesis against real market data.

Detects the objects with the production detector, pairs each with matched
controls, and returns a certificate for the MECHANISM_SUPPORTED rung.

Usage:
    run_mechanism_test.py HYPOTHESIS_ID --candles PATH --symbol SYM
                          --timeframe 15m [--bars N] [--out PATH]

Observe-only. A certificate here proves a preregistered association with a
named observable. It cannot establish forecast quality or economic value, and
it creates no signal, paper, or live authority.
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
from smc_desk.evaluation.mechanism_evidence import certify_mechanism  # noqa: E402
from smc_desk.perception.engine_v2 import PerceptionEngineV2  # noqa: E402

# Which detected family each hypothesis draws its events from.
FAMILY_BY_HYPOTHESIS = {
    "FVG_CONTINUATION_V1": "fvgs",
    "FVG_FILL_RATE_V1": "fvgs",
}

# Hypotheses whose event definition is not the same thing as a detected object.
# SWING_LIQUIDITY_ACCELERATION_V1 is about the moment price *trades through* a
# confirmed swing extreme -- a penetration, which happens later than and
# separately from the swing's own confirmation, and may never happen at all.
# Anchoring it on swing confirmations would measure a different event and stamp
# it with this hypothesis id, which is precisely the substitution the observable
# dispatch was added to prevent. Refusing is the honest state until a
# penetration-event extractor exists.
UNIMPLEMENTED_EVENT_MAPPING = {
    "SWING_LIQUIDITY_ACCELERATION_V1": (
        "needs a penetration-event extractor; a confirmed swing is not the same "
        "event as price trading through it"
    ),
}


def detect_events(frame: pd.DataFrame, symbol: str, timeframe: str, group: str, session: str):
    """Return (indices, signs) for confirmed objects, anchored at confirmation.

    Anchoring on ``confirmed_at`` rather than ``pivot_time`` matters: an object
    is only knowable once confirmed, so measuring forward from the pivot would
    score the system on information it did not have.
    """
    candles = dataframe_to_candles(
        frame, venue="TEST", instrument=symbol, timeframe=timeframe, session_profile=session
    )
    snapshot = PerceptionEngineV2().analyze(candles, candles[-1].close_time).model_dump(mode="json")
    stamps = pd.to_datetime(frame["timestamp"], utc=True)
    position = {stamp: index for index, stamp in enumerate(stamps)}

    indices: list[int] = []
    signs: list[float] = []
    skipped = 0
    for item in snapshot.get(group) or []:
        confirmed = item.get("confirmed_at")
        if not confirmed or str(item.get("confirmation_status")) != "confirmed":
            skipped += 1
            continue
        index = position.get(pd.Timestamp(confirmed).tz_convert("UTC"))
        if index is None:
            skipped += 1
            continue
        indices.append(index)
        signs.append(-1.0 if str(item.get("direction")) == "bearish" else 1.0)
    order = sorted(range(len(indices)), key=lambda i: indices[i])
    return [indices[i] for i in order], [signs[i] for i in order], {
        "detected": len(snapshot.get(group) or []), "usable": len(indices), "skipped": skipped
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hypothesis_id")
    parser.add_argument("--candles", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--session", default="continuous")
    parser.add_argument("--bars", type=int, default=20_000)
    parser.add_argument(
        "--qualified", action="store_true",
        help="use the qualified (poi_grade) subset. The constitution keeps "
             "qualification separate from raw geometry, so these are two "
             "different objects and both runs must be reported.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.hypothesis_id in UNIMPLEMENTED_EVENT_MAPPING:
        print(f"REFUSED: {args.hypothesis_id} — {UNIMPLEMENTED_EVENT_MAPPING[args.hypothesis_id]}")
        return 3

    group = FAMILY_BY_HYPOTHESIS.get(args.hypothesis_id)
    if args.qualified and group == "fvgs":
        group = "poi_grade_fvgs"
    if group is None:
        print(f"No detector family mapped for {args.hypothesis_id}")
        return 2

    frame = pd.read_csv(args.candles)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").tail(args.bars).reset_index(drop=True)
    print(f"{args.symbol} {args.timeframe}: {len(frame)} candles "
          f"{frame['timestamp'].iloc[0]} -> {frame['timestamp'].iloc[-1]}")

    indices, signs, counts = detect_events(frame, args.symbol, args.timeframe, group, args.session)
    print(f"events: {json.dumps(counts)}")
    if len(indices) > 1:
        spacing = pd.Series(indices).diff().dropna()
        print(f"median spacing between events: {spacing.median():.0f} bars")

    certificate = certify_mechanism(
        hypothesis_id=args.hypothesis_id, candles=frame,
        event_indices=indices, event_signs=signs,
        market=args.symbol, timeframe=args.timeframe, seed=args.seed,
    )

    print(f"\nSTATUS: {certificate['status']}")
    if certificate.get("reason"):
        print(f"reason: {certificate['reason']}")
    for entry in certificate.get("per_horizon") or []:
        print(
            f"  h={entry['horizon_bars']:3d}  pairs={entry.get('paired_observations')}  "
            f"treated={entry['treated_mean']}  control={entry['control_mean']}  "
            f"paired_diff={entry.get('observed_difference')}  t={entry['bootstrap_t']}  "
            f"p={entry['p_value']}  passes={entry['passes']}"
        )
    balance = certificate.get("balance") or {}
    print(f"balance: {balance.get('balanced')}")
    if certificate.get("matching"):
        print(f"matching: {json.dumps(certificate['matching'])}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(certificate, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
