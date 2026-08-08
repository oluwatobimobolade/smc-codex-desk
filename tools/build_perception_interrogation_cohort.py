#!/usr/bin/env python3
"""Build the sealed 30-case SMC perception interrogation review cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smc_desk.evaluation.interrogation_cohort import build_interrogation_cohort


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data/ohlcv/binance_futures")
    parser.add_argument("--output", default="review_queues/SMC_INTERROGATION_30_V1_20260713")
    parser.add_argument("--cases-per-symbol", type=int, default=6)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--cohort-id", default="SMC-INTERROGATION-30-V1")
    parser.add_argument("--gauntlet-v2", action="store_true", help="Add the 46-probe dual-wording gauntlet and semantic metamorphic pack.")
    args = parser.parse_args()
    data_root = Path(args.data_root).expanduser().resolve()
    paths = {
        symbol: data_root / symbol / f"{symbol}_15m_4year.csv"
        for symbol in args.symbols
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing canonical source files: {missing}")
    manifest = build_interrogation_cohort(
        symbol_csv_paths=paths,
        output_root=args.output,
        cases_per_symbol=args.cases_per_symbol,
        cohort_id=args.cohort_id,
        include_gauntlet_v2=args.gauntlet_v2,
    )
    print(json.dumps({
        "cohort_id": manifest["cohort_id"],
        "case_count": manifest["case_count"],
        "certification_eligible": manifest["certification_eligible"],
        "manifest": str(Path(args.output).expanduser().resolve() / "cohort_manifest.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
