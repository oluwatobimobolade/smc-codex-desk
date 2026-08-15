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
from smc_desk.evaluation.mechanism_evidence import certify_mechanism, compare_arms  # noqa: E402
from smc_desk.perception.penetration_events import (  # noqa: E402
    deduplicate_by_bar,
    extract_penetration_events,
)
from smc_desk.perception.significance import grade_timeframe  # noqa: E402
from smc_desk.perception.engine_v2 import PerceptionEngineV2  # noqa: E402

# Which detected family each hypothesis draws its events from.
FAMILY_BY_HYPOTHESIS = {
    "FVG_CONTINUATION_V1": "fvgs",
    "FVG_FILL_RATE_V1": "fvgs",
}

# Hypotheses whose events are penetrations of prior swing extremes rather than
# detected objects. A confirmed swing is not the same event as price trading
# through it: the penetration happens later, may never happen at all, and is
# what Osler's order-book result is actually about.
PENETRATION_HYPOTHESES = {
    "SWING_LIQUIDITY_ACCELERATION_V1": None,        # all grades
    "SWING_GRADE_DISCRIMINATION_V1": ("major", "minor"),  # two arms, compared
}

UNIMPLEMENTED_EVENT_MAPPING: dict[str, str] = {}


def detect_penetrations(
    frame: pd.DataFrame,
    symbol: str,
    timeframe: str,
    session: str,
    *,
    grades: tuple[str, ...] | None = None,
):
    """Penetration events, optionally split by the swing's significance grade.

    Returns ``{grade_or_'all': (indices, diagnostics)}``. Grading happens over
    the same candle window the events are measured in, so a swing's grade and
    its penetration are evaluated against one volatility regime.
    """
    candles = dataframe_to_candles(
        frame, venue="TEST", instrument=symbol, timeframe=timeframe, session_profile=session
    )
    snapshot = PerceptionEngineV2().analyze(candles, candles[-1].close_time).model_dump(mode="json")
    # `swings` is keyed by detection scale (local / internal / external), not a
    # flat list. Iterating it directly yields the scale *names*, which silently
    # produced an empty event set on the first run. Every scale is kept: the
    # preregistration says "a confirmed swing extreme" without qualifying scale,
    # and narrowing it here would answer a different question than the sealed one.
    by_scale = snapshot.get("swings") or {}
    swings = [
        s for scale_swings in by_scale.values()
        for s in (scale_swings or [])
        if isinstance(s, dict)
    ] if isinstance(by_scale, dict) else []

    records = frame.to_dict("records")
    summary = grade_timeframe(candles=records, swings=swings)
    grade_by_id = {s.object_id: s.grade for s in summary.scores}

    events = deduplicate_by_bar(extract_penetration_events(swings, frame))
    buckets: dict[str, list] = {}
    for wanted in (grades or ("all",)):
        chosen = [
            e for e in events
            if wanted == "all" or grade_by_id.get(e.swing_object_id) == wanted
        ]
        buckets[wanted] = chosen
    return buckets, {
        "confirmed_swings": len(swings),
        "penetrations": len(events),
        "closed_beyond": sum(1 for e in events if e.closed_beyond),
        "median_bars_to_penetration": (
            int(pd.Series([e.bars_since_confirmation for e in events]).median())
            if events else None
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


def _print_certificate(label: str, certificate: dict) -> None:
    print(f"\n[{label}] STATUS: {certificate['status']}")
    if certificate.get("reason"):
        print(f"  reason: {certificate['reason']}")
    for entry in certificate.get("per_horizon") or []:
        print(
            f"    h={entry['horizon_bars']:3d}  pairs={entry.get('paired_observations')}  "
            f"treated={entry['treated_mean']}  control={entry['control_mean']}  "
            f"diff={entry.get('observed_difference')}  t={entry['bootstrap_t']}  "
            f"p={entry['p_value']}  passes={entry['passes']}"
        )
    print(f"  balance: {(certificate.get('balance') or {}).get('balanced')}")


def _run_penetration(args, frame: pd.DataFrame) -> int:
    """Run a penetration hypothesis, single-arm or graded two-arm."""
    grades = PENETRATION_HYPOTHESES[args.hypothesis_id]
    buckets, diagnostics = detect_penetrations(
        frame, args.symbol, args.timeframe, args.session, grades=grades
    )
    print(f"penetrations: {json.dumps(diagnostics)}")

    certificates: dict[str, dict] = {}
    for arm, events in buckets.items():
        indices = [e.bar_index for e in events]
        print(f"  arm '{arm}': {len(indices)} events")
        certificates[arm] = certify_mechanism(
            hypothesis_id=args.hypothesis_id, candles=frame,
            event_indices=indices, market=args.symbol,
            timeframe=args.timeframe, seed=args.seed,
        )
        _print_certificate(arm, certificates[arm])

    comparison = None
    if grades and len(grades) == 2:
        # The arms are compared on control-adjusted differences, so the local
        # volatility and location confounds are already removed from both sides.
        first, second = grades
        by_horizon = {}
        for entry_a in certificates[first].get("per_horizon") or []:
            horizon = entry_a["horizon_bars"]
            entry_b = next(
                (e for e in certificates[second].get("per_horizon") or []
                 if e["horizon_bars"] == horizon), None
            )
            if entry_b is None:
                continue
            import numpy as np
            by_horizon[horizon] = compare_arms(
                np.asarray(entry_a.get("paired_differences") or [], dtype=float),
                np.asarray(entry_b.get("paired_differences") or [], dtype=float),
                block_length=horizon, seed=args.seed + horizon,
            )
        comparison = {
            "schema": "smc_mechanism_arm_comparison_v1",
            "hypothesis_id": args.hypothesis_id,
            "arm_a": first, "arm_b": second,
            "per_horizon": by_horizon,
        }
        print(f"\nARM COMPARISON ({first} vs {second}):")
        for horizon, result in sorted(by_horizon.items()):
            print(
                f"  h={horizon:3d}  {first}={result.get('arm_a_mean')} "
                f"{second}={result.get('arm_b_mean')}  "
                f"diff={result.get('observed_difference')}  t={result.get('bootstrap_t')}  "
                f"p={result.get('p_value')}"
            )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {"diagnostics": diagnostics, "certificates": certificates,
                 "arm_comparison": comparison},
                indent=2, default=str,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")
    return 0


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

    is_penetration = args.hypothesis_id in PENETRATION_HYPOTHESES
    group = FAMILY_BY_HYPOTHESIS.get(args.hypothesis_id)
    if args.qualified and group == "fvgs":
        group = "poi_grade_fvgs"
    if group is None and not is_penetration:
        print(f"No detector family mapped for {args.hypothesis_id}")
        return 2

    frame = pd.read_csv(args.candles)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").tail(args.bars).reset_index(drop=True)
    print(f"{args.symbol} {args.timeframe}: {len(frame)} candles "
          f"{frame['timestamp'].iloc[0]} -> {frame['timestamp'].iloc[-1]}")

    if is_penetration:
        return _run_penetration(args, frame)

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
