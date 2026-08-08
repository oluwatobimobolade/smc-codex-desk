#!/usr/bin/env python3
"""Verify a sealed SMC perception interrogation cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smc_desk.evaluation.interrogation_cohort import verify_interrogation_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = verify_interrogation_cohort(args.root)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if args.strict and report["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
