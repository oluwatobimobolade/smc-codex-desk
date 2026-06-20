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
from smc_desk.session import summarize_session_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize the current session context from OHLCV data.")
    parser.add_argument("--ohlcv", required=True, help="Path to OHLCV CSV.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_ohlcv_csv(args.ohlcv)
    print(json.dumps(summarize_session_context(df), indent=2))


if __name__ == "__main__":
    main()
