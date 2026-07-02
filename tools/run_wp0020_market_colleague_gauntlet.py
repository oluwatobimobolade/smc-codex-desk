#!/usr/bin/env python3
"""Run WP-0020 End-to-End Market Colleague Gauntlet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.wp0020_gauntlet import run_wp0020_gauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--source", default=None, help="Local canonical 15m CSV source. Optional in live mode as fallback.")
    parser.add_argument("--decision-time", default=None, help="Availability/as-of time. Defaults to latest closed candle in source.")
    parser.add_argument("--out", required=True, help="Output folder")
    parser.add_argument("--mode", choices=["csv", "live"], default="csv")
    parser.add_argument("--visual-mode", choices=["skip", "capture"], default="skip")
    parser.add_argument("--live-limit", type=int, default=500)
    parser.add_argument("--min-live-bars", type=int, default=100)
    parser.add_argument("--verbose", action="store_true", help="Print full nested report JSON instead of the compact operator summary.")
    args = parser.parse_args()

    result = run_wp0020_gauntlet(
        symbol=args.symbol,
        output_dir=args.out,
        source=args.source,
        decision_time=args.decision_time,
        mode=args.mode,
        visual_mode=args.visual_mode,
        live_limit=args.live_limit,
        min_live_bars=args.min_live_bars,
    )
    payload = result.to_dict()
    if args.verbose:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(
            {
                "output_dir": payload["output_dir"],
                "status": payload["status"],
                "failed_layer": payload["failed_layer"],
                "summary": payload["summary"]["full_summary"],
            },
            indent=2,
            default=str,
        ))
    return 0 if result.status in {"PASS", "PASS_WITH_REVIEW_FLAGS", "PARTIAL_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
