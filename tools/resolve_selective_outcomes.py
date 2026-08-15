#!/usr/bin/env python
"""Resolve logged decisions in a selective-outcome ledger against the market.

Reads DECISION events, finds candles that opened at or after each decision, and
appends an OUTCOME event scoring the read the system recorded at the time.

Cases whose forward data has not arrived yet are reported and skipped, not
written: an UNRESOLVED event would claim the case was examined and settled. The
ledger refuses duplicate ownership per case, so a case is scored once and only
once, when the market has actually produced the horizon.

Usage:
    resolve_selective_outcomes.py LEDGER --candles SYMBOL=PATH [SYMBOL=PATH ...]
                                 [--horizon-bars 20] [--atr-period 14] [--dry-run]

Observe-only. Resolution feeds no detector, tunes no threshold, and creates no
signal, paper, or live authority.
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

from smc_desk.data.hashing import dataframe_sha256  # noqa: E402
from smc_desk.evaluation.outcome_resolution import (  # noqa: E402
    DEFAULT_HORIZON_BARS,
    forward_window,
    resolve_decision_outcome,
)
from smc_desk.evaluation.selective_outcomes import (  # noqa: E402
    append_selective_ledger_event,
    build_selective_outcome_report,
    read_selective_ledger,
)


def average_true_range(candles: pd.DataFrame, period: int) -> float | None:
    """Wilder-style ATR over the candles available BEFORE the decision."""
    if candles is None or len(candles) < period + 1:
        return None
    high, low = candles["high"].astype(float), candles["low"].astype(float)
    previous_close = candles["close"].astype(float).shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    value = float(true_range.tail(period).mean())
    return value if value > 0 else None


def load_candles(spec: str) -> tuple[str, pd.DataFrame]:
    symbol, _, path = spec.partition("=")
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return symbol.strip().upper(), frame.sort_values("timestamp").reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--candles", nargs="+", required=True, metavar="SYMBOL=PATH")
    parser.add_argument("--horizon-bars", type=int, default=DEFAULT_HORIZON_BARS)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    candles_by_symbol = dict(load_candles(spec) for spec in args.candles)
    events = read_selective_ledger(args.ledger)
    decisions = [item for item in events if item.get("event_type") == "DECISION"]
    already = {item["case_id"] for item in events if item.get("event_type") == "OUTCOME"}

    counts = {"resolved": 0, "awaiting_market": 0, "no_candles": 0, "already_scored": 0, "data_failed": 0}
    for decision in decisions:
        case_id = str(decision.get("case_id") or "")
        if case_id in already:
            counts["already_scored"] += 1
            continue
        symbol = str(decision.get("symbol") or "").upper()
        candles = candles_by_symbol.get(symbol)
        if candles is None:
            counts["no_candles"] += 1
            print(f"  {case_id}: no candles supplied for {symbol}")
            continue

        decision_time = pd.Timestamp(decision["decision_time"])
        if decision_time.tzinfo is None:
            decision_time = decision_time.tz_localize("UTC")
        history = candles.loc[pd.to_datetime(candles["timestamp"], utc=True) < decision_time]
        forward = forward_window(candles, decision_time=decision_time, limit=args.horizon_bars)

        outcome = resolve_decision_outcome(
            decision,
            forward,
            atr=average_true_range(history, args.atr_period),
            horizon_bars=args.horizon_bars,
            source_hashes={"forward_candles_sha256": dataframe_sha256(forward) if len(forward) else ""},
        )
        if outcome.state == "UNRESOLVED":
            # The market has not produced the horizon yet. Writing this would
            # claim the case was settled; leaving it lets a later pass score it.
            counts["awaiting_market"] += 1
            print(f"  {case_id}: awaiting market ({len(forward)}/{args.horizon_bars} bars)")
            continue
        if not args.dry_run:
            append_selective_ledger_event(args.ledger, outcome)
        counts["data_failed" if outcome.state == "DATA_FAILED" else "resolved"] += 1
        print(
            f"  {case_id}: {outcome.state}"
            + (
                f" correct={outcome.shadow_prediction_correct}"
                f" favorable={outcome.favorable_opportunity}"
                f" return={outcome.outcome_return_bps}bps"
                if outcome.state == "RESOLVED"
                else ""
            )
        )

    print(f"\n{json.dumps(counts)}")
    report = build_selective_outcome_report(read_selective_ledger(args.ledger))
    print("case_counts:", json.dumps(report["case_counts"]))
    print("metrics:", json.dumps(report["metrics"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
