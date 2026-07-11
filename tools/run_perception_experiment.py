#!/usr/bin/env python3
"""Run sealed, observe-only perception research experiments."""
from __future__ import annotations

import argparse
import json

from smc_desk.research.perception_experiment import run_deterministic_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline", help="Run deterministic PerceptionEngineV2 baseline.")
    baseline.add_argument("--symbol", required=True)
    baseline.add_argument("--source", required=True)
    baseline.add_argument("--decision-time", default=None)
    baseline.add_argument("--out", required=True)
    baseline.add_argument("--window-15m", type=int, default=3000)
    baseline.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()

    manifest = run_deterministic_baseline(
        symbol=args.symbol,
        source=args.source,
        decision_time=args.decision_time,
        output_dir=args.out,
        window_15m=args.window_15m,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "experiment_fingerprint": manifest["experiment_fingerprint"],
                "manifest_sha256": manifest["manifest_sha256"],
                "output_dir": args.out,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
