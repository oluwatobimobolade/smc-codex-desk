#!/usr/bin/env python3
"""Capture user overrides and register them as regression/gold cases."""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def capture_override(
    *,
    decision_dir: str | Path,
    expected_state: str,
    expected_direction: str,
    expected_setup_grade: str | None = None,
    poi_low: float | None = None,
    poi_high: float | None = None,
    invalidation_price: float | None = None,
    target_price: float | None = None,
    output_dir: str | Path = "data/gold_sets/ai_smc",
) -> Path:
    decision_path = Path(decision_dir).expanduser().resolve()
    dec_file = decision_path / "13_official_ai_decision" / "official_decision.json"
    if not dec_file.exists():
        # Fallback to direct json file
        if dec_file.parent.parent.glob("*.json"):
            # Check if directory contains a JSON file
            for f in decision_path.rglob("official_decision.json"):
                dec_file = f
                break
    
    if not dec_file.exists():
        raise FileNotFoundError(f"Could not find official_decision.json in {decision_path}")

    decision = json.loads(dec_file.read_text(encoding="utf-8"))
    symbol = decision.get("symbol") or "UNKNOWN"
    
    # Try to find chart images
    chart_images = {}
    for tf in ("15m", "1h", "4h", "1d"):
        chart_images[tf] = f"dummy_{tf}.png" # default dummy values if not present
        
    for p in decision_path.rglob("*.png"):
        for tf in ("15m", "1h", "4h", "1d"):
            if tf in p.name:
                chart_images[tf] = str(p.relative_to(decision_path.parent))

    case_id = f"case_{symbol.lower()}_{uuid.uuid4().hex[:8]}"
    
    expected_poi = None
    if poi_low is not None and poi_high is not None:
        expected_poi = {"price_low": poi_low, "price_high": poi_high}
        
    expected_invalidation = None
    if invalidation_price is not None:
        expected_invalidation = {"price": invalidation_price}
        
    expected_target = None
    if target_price is not None:
        expected_target = {"price": target_price}

    gold_case = {
        "case_id": case_id,
        "symbol": symbol,
        "decision_time": decision.get("decision_time") or datetime.now(timezone.utc).isoformat(),
        "chart_images": chart_images,
        "expected_setup_grade": expected_setup_grade,
        "expected_state": expected_state,
        "expected_direction": expected_direction,
        "expected_poi": expected_poi,
        "expected_invalidation": expected_invalidation,
        "expected_target": expected_target,
        "human_smc_labels": {
            "source": "user_override_capture",
            "captured_at": datetime.now(timezone.utc).isoformat()
        },
        "adjudication_status": "adjudicated"
    }

    out_path = Path(output_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    target_file = out_path / f"{case_id}.json"
    target_file.write_text(json.dumps(gold_case, indent=2, sort_keys=True), encoding="utf-8")
    
    # Also record in a corrections.json file
    corrections_file = out_path / "corrections.json"
    corrections = []
    if corrections_file.exists():
        try:
            corrections = json.loads(corrections_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    corrections.append(gold_case)
    corrections_file.write_text(json.dumps(corrections, indent=2, sort_keys=True), encoding="utf-8")
    
    return target_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-dir", required=True, help="Path to decision output directory.")
    parser.add_argument("--expected-state", required=True, help="The expected/correct official_state.")
    parser.add_argument("--expected-direction", required=True, choices=["bullish", "bearish", "neutral", "mixed"], help="The expected/correct direction.")
    parser.add_argument("--expected-setup-grade", help="Optional expected setup grade.")
    parser.add_argument("--poi-low", type=float, help="Optional expected POI price low.")
    parser.add_argument("--poi-high", type=float, help="Optional expected POI price high.")
    parser.add_argument("--invalidation-price", type=float, help="Optional expected invalidation price.")
    parser.add_argument("--target-price", type=float, help="Optional expected target price.")
    parser.add_argument("--output-dir", default="data/gold_sets/ai_smc", help="Output directory for captured gold cases.")
    args = parser.parse_args()

    try:
        saved_file = capture_override(
            decision_dir=args.decision_dir,
            expected_state=args.expected_state,
            expected_direction=args.expected_direction,
            expected_setup_grade=args.expected_setup_grade,
            poi_low=args.poi_low,
            poi_high=args.poi_high,
            invalidation_price=args.invalidation_price,
            target_price=args.target_price,
            output_dir=args.output_dir,
        )
        print(f"Success! Saved gold override case to {saved_file}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
