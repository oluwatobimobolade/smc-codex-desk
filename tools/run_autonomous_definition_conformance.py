#!/usr/bin/env python3
"""Run the human-independent definition-conformance gate on closed OHLCV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.evaluation.autonomous_conformance import run_autonomous_definition_conformance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="CSV with timestamp, OHLC, and optional volume")
    parser.add_argument("--market", required=True, help="Exact instrument identifier used by the production engine")
    parser.add_argument("--timeframe", required=True, choices=("5m", "15m", "1h", "4h", "12h", "1d"))
    parser.add_argument("--decision-time", help="UTC ISO-8601; defaults to the final candle close")
    parser.add_argument("--session-profile", choices=("continuous", "forex_5d"), default="continuous")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {args.output}")
    frame = pd.read_csv(args.input)
    if "timestamp" not in frame.columns:
        for alias in ("open_time", "date", "datetime"):
            if alias in frame.columns:
                frame = frame.rename(columns={alias: "timestamp"})
                break
    if "timestamp" not in frame.columns:
        raise SystemExit("Input CSV has no timestamp/open_time/date/datetime column.")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    decision_time = args.decision_time or _final_close(frame, args.timeframe).isoformat().replace("+00:00", "Z")
    result = run_autonomous_definition_conformance(
        frame,
        market=args.market,
        timeframe=args.timeframe,
        decision_time=decision_time,
        session_profile=args.session_profile,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    _write_json(args.output / "certificate.json", result["certificate"])
    _write_json(args.output / "reference_oracle.json", result["reference"])
    _write_json(args.output / "production_claims.json", result["production"])
    _write_json(args.output / "diagnostics.json", result["diagnostics"])
    _write_json(args.output / "robustness_profiles.json", result["robustness_profiles"])
    print(json.dumps({
        "status": result["certificate"]["status"],
        "certificate_sha256": result["certificate"]["certificate_sha256"],
        "output": str(args.output.resolve()),
        "signal_allowed": False,
    }, indent=2))
    return 0 if result["certificate"]["status"] in {"DEFINITION_CONFORMANT", "BOUNDARY_SENSITIVE"} else 2


def _final_close(frame: pd.DataFrame, timeframe: str) -> pd.Timestamp:
    durations = {
        "5m": pd.Timedelta(minutes=5),
        "15m": pd.Timedelta(minutes=15),
        "1h": pd.Timedelta(hours=1),
        "4h": pd.Timedelta(hours=4),
        "12h": pd.Timedelta(hours=12),
        "1d": pd.Timedelta(days=1),
    }
    return pd.Timestamp(frame["timestamp"].max()) + durations[timeframe]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
