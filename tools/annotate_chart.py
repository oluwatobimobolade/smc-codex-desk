#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import load_ohlcv_csv
from smc_desk.models import AnalysisResult
from smc_desk.render import render_annotated_chart, render_screenshot_review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render annotations from an existing analysis JSON file.")
    parser.add_argument("--analysis", required=True, help="Path to analysis.json.")
    parser.add_argument("--ohlcv", help="Path to OHLCV CSV for candlestick rendering.")
    parser.add_argument("--image", help="Path to source screenshot for review rendering.")
    parser.add_argument("--output", required=True, help="Output PNG path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    analysis = AnalysisResult.model_validate(payload)
    if args.ohlcv:
        df = load_ohlcv_csv(args.ohlcv)
        render_annotated_chart(df, analysis, args.output)
        return
    if args.image:
        render_screenshot_review(args.image, analysis, args.output)
        return
    raise SystemExit("Provide --ohlcv for chart rendering or --image for screenshot review rendering.")


if __name__ == "__main__":
    main()
