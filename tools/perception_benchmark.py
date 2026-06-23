#!/usr/bin/env python3
"""Synthetic detector contract benchmark.

Runs every synthetic ground-truth builder (smc_desk/synthetic.py) across multiple
price scales (0.5 .. 60000, a scale-invariance test) and seeds, feeds each case to
the real engine detectors, and scores:
  - RECALL: of cases that contain primitive X, how often the engine detects X
    (correct type AND direction).
  - CONFUSION: cases where the same detector fired the WRONG direction/label.
  - FALSE POSITIVES (chop control): structural breaks / sweeps that fire on noise.

This is a detector regression suite, not real-market perception accuracy. Its
fixtures are intentional, canonical constructions and cannot substitute for
the adjudicated real-chart gold set scored by evaluate_perception_gold.py.

Usage:
  python3 tools/perception_benchmark.py --output-dir backtests/perception/run1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import (
    detect_equal_levels,
    detect_fvgs,
    detect_liquidity_sweeps,
    detect_order_blocks,
    detect_structure_events,
    detect_swings,
)
from smc_desk.rules import load_rule_config
from smc_desk.synthetic import BUILDERS

PRICES = [0.5, 5.0, 100.0, 3500.0, 60000.0]


def detect_all(df, config):
    swings = detect_swings(df, config)
    events = detect_structure_events(df, swings, config, structure_scope="swing")
    fvgs = detect_fvgs(df, config)
    sweeps = detect_liquidity_sweeps(df, swings, config)
    obs = detect_order_blocks(df, events, config)
    equals = detect_equal_levels(swings, config)
    return {"swings": swings, "events": events, "fvgs": fvgs,
            "sweeps": sweeps, "obs": obs, "equals": equals}


def hit_and_confusion(truth, det):
    """Return (detected_correct: bool, confused: bool) for one case."""
    kind, d = truth["kind"], truth["direction"]
    if kind in ("BOS", "CHoCH"):
        same = [e for e in det["events"] if e.label == kind]
        correct = any(e.direction == d for e in same)
        confused = any(e.direction != d for e in same) or any(
            e.label != kind and e.label in ("BOS", "CHoCH") for e in det["events"])
        return correct, confused
    if kind == "fvg":
        correct = any(z.direction == d for z in det["fvgs"])
        confused = any(z.direction != d for z in det["fvgs"])
        return correct, confused
    if kind == "Liquidity Sweep":
        correct = any(s.direction == d for s in det["sweeps"])
        confused = any(s.direction != d for s in det["sweeps"])
        return correct, confused
    if kind == "order_block":
        correct = any(z.direction == d for z in det["obs"])
        confused = any(z.direction != d for z in det["obs"])
        return correct, confused
    if kind in ("Equal Highs", "Equal Lows"):
        correct = any(z.label == kind for z in det["equals"])
        confused = any(z.label not in (kind,) and z.kind == "liquidity" for z in det["equals"])
        return correct, confused
    return False, False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rules")
    p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--output-dir", default="backtests/perception/run")
    args = p.parse_args()
    config = load_rule_config(args.rules)

    rows = []
    fp_total = fp_cases = 0
    for name, builder in BUILDERS.items():
        if name == "Chop":
            n = hits = 0
            for price in PRICES:
                for seed in range(args.seeds):
                    df, _ = builder(price, seed)
                    det = detect_all(df, config)
                    n += 1
                    nfp = len([e for e in det["events"] if e.label in ("BOS", "CHoCH")]) + len(det["sweeps"])
                    fp_total += nfp
                    if nfp:
                        fp_cases += 1
            continue
        n = correct = confused = 0
        for price in PRICES:
            for seed in range(args.seeds):
                df, truth = builder(price, seed)
                det = detect_all(df, config)
                c, cf = hit_and_confusion(truth, det)
                n += 1
                correct += int(c)
                confused += int(cf)
        rows.append((name, n, correct, confused))

    L = ["# Synthetic SMC Detector Contract Benchmark", ""]
    L.append("> This is not real-market accuracy. It verifies expected behavior on controlled fixtures; "
             "use `tools/evaluate_perception_gold.py` for expert-labelled perception metrics.")
    L.append("")
    L.append(f"Variants per primitive: {len(PRICES)} prices x {args.seeds} seeds = {len(PRICES)*args.seeds}. "
             f"Prices: {PRICES} (scale-invariance).")
    L.append("")
    L += ["| primitive | n | recall | confusion |", "|---|--:|--:|--:|"]
    tot_n = tot_c = 0
    for name, n, correct, confused in rows:
        tot_n += n; tot_c += correct
        L.append(f"| {name} | {n} | {correct/n:.0%} ({correct}/{n}) | {confused} |")
    L.append("")
    L.append(f"**Overall recall: {tot_c/tot_n:.1%} ({tot_c}/{tot_n})**")
    nchop = len(PRICES) * args.seeds
    L.append(f"**Chop false positives: {fp_cases}/{nchop} cases had a spurious break/sweep ({fp_total} total).**")
    L.append("")
    L.append("> Contract target: expected fixtures should pass and explicit chop controls should not emit spurious "
             "structure/sweep events. This result must never be reported as real-chart accuracy.")

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "perception_report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWrote {out/'perception_report.md'}")


if __name__ == "__main__":
    main()
