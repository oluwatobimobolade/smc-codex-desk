#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import build_trade_plan_markdown
from smc_desk.models import AnalysisResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Markdown trade plan from analysis JSON.")
    parser.add_argument("--analysis", required=True, help="Path to analysis.json.")
    parser.add_argument("--output", required=True, help="Path to trade_plan.md.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    analysis = AnalysisResult.model_validate(payload)
    Path(args.output).write_text(build_trade_plan_markdown(analysis), encoding="utf-8")


if __name__ == "__main__":
    main()
