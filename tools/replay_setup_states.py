#!/usr/bin/env python3
"""Replay closed-candle SMC events through the experimental setup state machine.

This is observability only. It produces transitions and terminal reasons; it
does not create trade plans, simulate fills, or promote a live rule.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe, load_ohlcv_csv
from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, assert_not_in_holdout
from smc_desk.models import StructureEvent, Zone
from smc_desk.mtf import build_mtf_snapshot, derive_htf_consensus_bias, precompute_htf_series
from smc_desk.rules import load_rule_config
from smc_desk.state_machine import PoiAnchor, SetupMemory, StateInput, StateMachineConfig, advance_setup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay deterministic SMC setup states without generating trades.")
    parser.add_argument("--ohlcv", required=True, help="15m OHLCV CSV.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--rules", help="Optional rules JSON.")
    parser.add_argument("--warmup-bars", type=int, default=400)
    parser.add_argument("--max-bars", type=int, default=500, help="Closed candles to replay after warmup; use a small smoke window first.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--displacement-timeout-bars", type=int, default=3)
    parser.add_argument("--retrace-timeout-bars", type=int, default=48)
    parser.add_argument("--confirmation-timeout-bars", type=int, default=24)
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--allow-holdout", action="store_true", help="Only for deliberate final-evaluation replay.")
    return parser.parse_args()


def _scope_rank(event: StructureEvent) -> tuple[int, int]:
    scope = {"external": 3, "swing": 2, "internal": 1, "unknown": 0}.get(event.structure_scope, 0)
    strength = {"strong": 2, "valid": 1, "weak": 0}.get(event.strength, 0)
    return (scope, strength)


def _current_event(events: list[StructureEvent], index: int, label: str, direction: str | None = None) -> StructureEvent | None:
    candidates = [
        event
        for event in events
        if event.index == index and event.label == label and (direction is None or event.direction == direction)
    ]
    return max(candidates, key=_scope_rank) if candidates else None


def _candidate_poi(zones: list[Zone], direction: str, current_index: int) -> PoiAnchor | None:
    candidates = [
        zone
        for zone in zones
        if zone.kind in {"fvg", "order_block"}
        and zone.direction == direction
        and zone.status in {"fresh", "partial"}
        and (zone.end_index is None or zone.end_index <= current_index)
    ]
    if not candidates:
        return None
    zone = max(candidates, key=lambda item: (item.score, item.end_index or -1))
    return PoiAnchor(
        kind=zone.kind,
        low=float(zone.low),
        high=float(zone.high),
        source_bar_index=int(zone.end_index if zone.end_index is not None else current_index),
        score=float(zone.score),
    )


def _state_input(
    *,
    symbol: str,
    decision_index: int,
    analyzed_df: pd.DataFrame,
    direction: str,
    events: list[StructureEvent],
    zones: list[Zone],
    active: SetupMemory | None,
) -> StateInput:
    local_index = len(analyzed_df) - 1
    bar = analyzed_df.iloc[-1]
    sweep = _current_event(events, local_index, "Liquidity Sweep", direction)
    structure = None
    if direction in {"bullish", "bearish"}:
        candidates = [
            event
            for event in events
            if event.index == local_index
            and event.label in {"BOS", "CHoCH"}
            and event.direction == direction
            and event.strength != "weak"
        ]
        structure = max(candidates, key=_scope_rank) if candidates else None

    poi_touched = False
    poi_fully_mitigated = False
    sweep_invalidated = False
    if active is not None and active.poi is not None:
        poi_touched = float(bar["low"]) <= active.poi.high and float(bar["high"]) >= active.poi.low
        poi_fully_mitigated = (
            float(bar["close"]) <= active.poi.low
            if active.direction == "bullish"
            else float(bar["close"]) >= active.poi.high
        )
        sweep_invalidated = (
            float(bar["low"]) < active.sweep_price
            if active.direction == "bullish"
            else float(bar["high"]) > active.sweep_price
        )

    return StateInput(
        symbol=symbol,
        timeframe="15m",
        bar_index=decision_index,
        timestamp=pd.Timestamp(bar["timestamp"]).isoformat(),
        htf_direction=direction,
        sweep_direction=sweep.direction if sweep else None,
        sweep_price=sweep.swept_level if sweep and sweep.swept_level is not None else (sweep.price if sweep else None),
        displacement_direction=structure.direction if structure else None,
        displacement_price=structure.price if structure else None,
        candidate_poi=_candidate_poi(zones, direction, local_index) if structure else None,
        poi_touched=poi_touched,
        poi_fully_mitigated=poi_fully_mitigated,
        sweep_invalidated=sweep_invalidated,
        confirmation=False,
    )


def replay(args: argparse.Namespace) -> dict[str, Any]:
    config = load_rule_config(args.rules)
    df = load_ohlcv_csv(args.ohlcv)
    if args.warmup_bars < config.lookback_bars:
        raise ValueError("--warmup-bars must be at least the engine lookback to keep event indices stable.")
    if len(df) <= args.warmup_bars:
        raise ValueError("Not enough candles after warmup.")

    state_config = StateMachineConfig(
        displacement_timeout_bars=args.displacement_timeout_bars,
        retrace_timeout_bars=args.retrace_timeout_bars,
        confirmation_timeout_bars=args.confirmation_timeout_bars,
    )
    precomputed = precompute_htf_series(df)
    active: SetupMemory | None = None
    transition_rows: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    terminal_reasons: Counter[str] = Counter()
    attempts: set[str] = set()
    final_index = min(len(df) - 1, args.warmup_bars + args.max_bars - 1)
    holdout_matches = assert_not_in_holdout(
        start=pd.Timestamp(df["timestamp"].iloc[args.warmup_bars]),
        end=pd.Timestamp(df["timestamp"].iloc[final_index]),
        symbol=args.symbol,
        action="state_replay",
        policy_path=args.holdout_policy,
        allow_holdout=args.allow_holdout,
    )
    state_observations: list[dict[str, Any]] = []

    for decision_index in range(args.warmup_bars, final_index + 1):
        history = df.iloc[: decision_index + 1].copy()
        decision_time = pd.Timestamp(history["timestamp"].iloc[-1])
        snapshot = build_mtf_snapshot(df, decision_time, config, precomputed=precomputed)
        direction = derive_htf_consensus_bias(snapshot)
        analysis, analyzed_df = analyze_dataframe(
            history,
            symbol=args.symbol.upper(),
            timeframe="15m",
            config=config,
            bias_hint=direction if direction in {"bullish", "bearish"} else None,
            notes="state_machine_observability",
            input_type="ohlcv",
        )
        event = _state_input(
            symbol=args.symbol.upper(),
            decision_index=decision_index,
            analyzed_df=analyzed_df,
            direction=direction,
            events=analysis.events,
            zones=analysis.zones,
            active=active,
        )
        update = advance_setup(event, active, state_config)
        active = update.active_setup
        state_counts[update.display_state.value] += 1
        bar = history.iloc[-1]
        state_observations.append(
            {
                "decision_index": decision_index,
                "decision_time": pd.Timestamp(bar["timestamp"]).isoformat(),
                "display_state": update.display_state.value,
                "active_attempt_id": active.attempt_id if active else None,
                "active_direction": active.direction if active else None,
                "htf_direction": direction,
                "transition_count": len(update.transitions),
                "transition_reasons": ";".join(transition.reason for transition in update.transitions),
            }
        )
        for transition in update.transitions:
            attempts.add(transition.attempt_id)
            row = asdict(transition)
            row["display_state_after"] = update.display_state.value
            transition_rows.append(row)
            if transition.to_state.value in {"INVALIDATED", "EXPIRED"}:
                terminal_reasons[transition.reason] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "observability_only_no_trade_plans_or_fills",
        "event_store_schema_version": "1.0",
        "symbol": args.symbol.upper(),
        "source_csv": str(Path(args.ohlcv).resolve()),
        "window": {
            "start": pd.Timestamp(df["timestamp"].iloc[args.warmup_bars]).isoformat(),
            "end": pd.Timestamp(df["timestamp"].iloc[final_index]).isoformat(),
            "bars_replayed": final_index - args.warmup_bars + 1,
        },
        "state_config": asdict(state_config),
        "holdout_windows_touched": [
            {
                "name": window.name,
                "start": window.start.isoformat(),
                "end": None if window.end is None else window.end.isoformat(),
                "reason": window.reason,
            }
            for window in holdout_matches
        ],
        "attempts_started": len(attempts),
        "state_counts": dict(state_counts),
        "terminal_reasons": dict(terminal_reasons),
        "active_setup_at_end": asdict(active) if active else None,
        "state_observations": state_observations,
        "transitions": transition_rows,
    }


def main() -> None:
    args = parse_args()
    result = replay(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "state_machine_replay.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pd.DataFrame(result["state_observations"]).to_csv(output_dir / "state_observations.csv", index=False)
    pd.DataFrame(result["transitions"]).to_csv(output_dir / "state_transitions.csv", index=False)
    print(f"Replayed {result['window']['bars_replayed']} closed bars for {result['symbol']}")
    print(f"Attempts: {result['attempts_started']} | state counts: {result['state_counts']}")
    print(f"Wrote {output_dir / 'state_machine_replay.json'}")


if __name__ == "__main__":
    main()
