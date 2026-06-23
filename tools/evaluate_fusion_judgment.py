#!/usr/bin/env python3
"""Evaluate fusion verdicts against adjudicated human gold-set labels.

This is the measurement instrument. Without it, every confidence number in the
system is fiction and "A+ judgment" is literally unmeasurable.

Reports:
    - Direction accuracy (including "no_trade")
    - Brier score on confidence predictions
    - Reliability curve data
    - Hard-gate violation count

Usage:
    python3 tools/evaluate_fusion_judgment.py --gold-dir case_library/fusion_gold/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DIRECTION_MAP = {
    "long": "bullish",
    "short": "bearish",
    "no_trade": "neutral",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate fusion verdicts against adjudicated gold-set labels."
    )
    parser.add_argument("--gold-dir", required=True, help="Directory containing adjudicated cases.")
    parser.add_argument("--min-cases", type=int, default=10, help="Minimum adjudicated cases required.")
    parser.add_argument("--output", help="Optional JSON output path for the report.")
    return parser.parse_args()


def _load_cases(gold_dir: Path) -> list[dict[str, Any]]:
    """Load all adjudicated cases from the gold directory."""
    cases: list[dict[str, Any]] = []
    for case_dir in sorted(gold_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        label_path = case_dir / "label.json"
        machine_path = case_dir / "machine_sealed.json"
        if not label_path.exists() or not machine_path.exists():
            continue

        label = json.loads(label_path.read_text(encoding="utf-8"))
        machine = json.loads(machine_path.read_text(encoding="utf-8"))

        # Only include adjudicated cases (label is filled in).
        lbl = label.get("label", {})
        if not lbl.get("direction") or not lbl.get("reviewer"):
            continue

        fusion = machine.get("fusion", {})
        cases.append({
            "case_id": label.get("case_id", case_dir.name),
            "human_direction": lbl.get("direction", ""),
            "human_conviction": lbl.get("conviction", ""),
            "human_why": lbl.get("why", ""),
            "fusion_verdict": fusion.get("recommended_verdict", "Pass"),
            "fusion_direction": fusion.get("recommended_direction", "neutral"),
            "fusion_confidence": fusion.get("fused_confidence", 0.0),
            "fusion_contested": fusion.get("contested", False),
            "engine_verdict": fusion.get("engine_primary_verdict", "Pass"),
            "engine_direction": fusion.get("engine_primary_bias", "neutral"),
        })
    return cases


def _direction_match(human: str, machine: str) -> bool:
    """Check if human direction matches machine direction."""
    mapped = DIRECTION_MAP.get(human.lower(), human.lower())
    return mapped == machine


def _brier_score(predictions: np.ndarray, outcomes: np.ndarray) -> float:
    """Compute Brier score: mean((predicted_prob - actual_outcome)^2).

    For direction: outcome = 1 if correct, 0 if wrong.
    """
    return float(np.mean((predictions - outcomes) ** 2))


def _reliability_curve(
    predictions: np.ndarray, outcomes: np.ndarray, n_bins: int = 5
) -> list[dict[str, float]]:
    """Compute reliability curve data (binned calibration)."""
    bins = np.linspace(0, 1, n_bins + 1)
    curve: list[dict[str, float]] = []
    for i in range(n_bins):
        mask = (predictions >= bins[i]) & (predictions < bins[i + 1])
        if mask.sum() == 0:
            continue
        mean_pred = float(predictions[mask].mean())
        mean_outcome = float(outcomes[mask].mean())
        count = int(mask.sum())
        curve.append({
            "bin_low": round(bins[i], 2),
            "bin_high": round(bins[i + 1], 2),
            "mean_prediction": round(mean_pred, 4),
            "mean_outcome": round(mean_outcome, 4),
            "count": count,
        })
    return curve


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce the evaluation report."""
    n = len(cases)
    if n == 0:
        return {"status": "no_adjudicated_cases", "message": "No adjudicated cases found."}

    # Direction accuracy
    correct = sum(1 for c in cases if _direction_match(c["human_direction"], c["fusion_direction"]))
    direction_accuracy = correct / n

    # Engine-only direction accuracy (baseline comparison)
    engine_correct = sum(
        1 for c in cases if _direction_match(c["human_direction"], c["engine_direction"])
    )
    engine_accuracy = engine_correct / n

    # Brier score: use fusion confidence as predicted probability,
    # outcome = 1 if direction matched, 0 if not.
    predictions = np.array([c["fusion_confidence"] for c in cases])
    outcomes = np.array([
        1.0 if _direction_match(c["human_direction"], c["fusion_direction"]) else 0.0
        for c in cases
    ])
    brier = _brier_score(predictions, outcomes)

    # Reliability curve
    reliability = _reliability_curve(predictions, outcomes)

    # No-trade accuracy: did fusion correctly say Pass/neutral when human said no_trade?
    no_trade_cases = [c for c in cases if c["human_direction"].lower() == "no_trade"]
    no_trade_correct = sum(
        1 for c in no_trade_cases if c["fusion_verdict"] == "Pass" or c["fusion_direction"] == "neutral"
    )
    no_trade_accuracy = no_trade_correct / len(no_trade_cases) if no_trade_cases else None

    # Contested cases
    contested = sum(1 for c in cases if c["fusion_contested"])

    # Conviction correlation (if human conviction is available)
    conviction_map = {"high": 1.0, "medium": 0.5, "low": 0.25}
    conviction_pairs = [
        (c["fusion_confidence"], conviction_map.get(c["human_conviction"].lower(), 0.5))
        for c in cases
        if c["human_conviction"]
    ]
    conviction_correlation = None
    if len(conviction_pairs) >= 5:
        preds = np.array([p for p, _ in conviction_pairs])
        actuals = np.array([a for _, a in conviction_pairs])
        if preds.std() > 0 and actuals.std() > 0:
            conviction_correlation = float(np.corrcoef(preds, actuals)[0, 1])

    # Acceptance gates
    gates = {
        "direction_accuracy_gte_85": direction_accuracy >= 0.85,
        "brier_lte_25": brier <= 0.25,
        "min_cases_met": n >= 10,
    }
    all_pass = all(gates.values())

    return {
        "status": "ok",
        "total_cases": n,
        "direction_accuracy": round(direction_accuracy, 4),
        "engine_baseline_accuracy": round(engine_accuracy, 4),
        "fusion_vs_engine_delta": round(direction_accuracy - engine_accuracy, 4),
        "brier_score": round(brier, 4),
        "reliability_curve": reliability,
        "no_trade_accuracy": round(no_trade_accuracy, 4) if no_trade_accuracy is not None else None,
        "no_trade_cases": len(no_trade_cases),
        "contested_cases": contested,
        "conviction_correlation": round(conviction_correlation, 4) if conviction_correlation is not None else None,
        "acceptance_gates": gates,
        "all_gates_pass": all_pass,
        "verdict": "GO" if all_pass else "NO-GO",
    }


def main() -> int:
    args = parse_args()
    gold_dir = Path(args.gold_dir)
    if not gold_dir.exists():
        print(f"Error: {gold_dir} does not exist.")
        return 1

    cases = _load_cases(gold_dir)
    if len(cases) < args.min_cases:
        print(f"Insufficient ground truth: {len(cases)} cases (need {args.min_cases}).")
        report = {"status": "insufficient_ground_truth", "found": len(cases), "required": args.min_cases}
        if args.output:
            Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    report = evaluate(cases)

    print(f"=== Fusion Judgment Evaluation ===")
    print(f"Total adjudicated cases: {report['total_cases']}")
    print(f"Direction accuracy: {report['direction_accuracy']:.1%}")
    print(f"Engine baseline:    {report['engine_baseline_accuracy']:.1%}")
    print(f"Delta (fusion-engine): {report['fusion_vs_engine_delta']:+.1%}")
    print(f"Brier score: {report['brier_score']:.4f}")
    if report["no_trade_accuracy"] is not None:
        print(f"No-trade accuracy: {report['no_trade_accuracy']:.1%} ({report['no_trade_cases']} cases)")
    print(f"Contested cases: {report['contested_cases']}")
    if report["conviction_correlation"] is not None:
        print(f"Conviction correlation: {report['conviction_correlation']:.4f}")
    print(f"\nAcceptance gates:")
    for gate, passed in report["acceptance_gates"].items():
        print(f"  {'PASS' if passed else 'FAIL'} {gate}")
    print(f"\nVerdict: {report['verdict']}")

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {args.output}")

    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
