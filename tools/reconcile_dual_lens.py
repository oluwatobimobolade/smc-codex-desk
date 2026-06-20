#!/usr/bin/env python3
"""Reconcile the engine lens and the vision lens for a case.

Usage:
    python3 tools/reconcile_dual_lens.py \
        --case case_library/BTCUSD/<case>/case.json \
        --vision case_library/BTCUSD/<case>/vision_read.json

Writes ``reconciliation.json`` and ``reconciliation.md`` beside the case and
prints the human-readable report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.dual_lens import reconcile, render_markdown


def _infer_symbol_from_path(path: Path) -> str:
    parts = path.parts
    if "case_library" in parts:
        index = parts.index("case_library")
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Dual-lens (engine + vision) reconciliation for an SMC case.")
    parser.add_argument("--case", required=True, help="Path to case.json")
    parser.add_argument("--vision", required=True, help="Path to vision_read.json")
    parser.add_argument("--output-dir", help="Where to write outputs. Defaults to the case directory.")
    args = parser.parse_args()

    case_path = Path(args.case)
    vision_path = Path(args.vision)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    vision = json.loads(vision_path.read_text(encoding="utf-8"))

    engine_analysis = case.get("machine_analysis", case)
    symbol = case.get("symbol") or engine_analysis.get("symbol") or _infer_symbol_from_path(case_path)
    timeframe = engine_analysis.get("timeframe", vision.get("timeframe", ""))
    decision_time = (
        case.get("decision_time")
        or engine_analysis.get("source", {}).get("decision_time")
        or engine_analysis.get("mtf", {}).get("decision_time")
    )

    recon = reconcile(engine_analysis, vision)
    recon["symbol"] = symbol
    recon["timeframe"] = timeframe
    recon["decision_time"] = decision_time
    recon["case_path"] = str(case_path)
    recon["vision_path"] = str(vision_path)

    out_dir = Path(args.output_dir) if args.output_dir else case_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reconciliation.json").write_text(json.dumps(recon, indent=2), encoding="utf-8")
    markdown = render_markdown(recon, symbol=symbol, timeframe=timeframe)
    (out_dir / "reconciliation.md").write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"\nWrote {out_dir / 'reconciliation.json'}")
    print(f"Wrote {out_dir / 'reconciliation.md'}")


if __name__ == "__main__":
    main()
