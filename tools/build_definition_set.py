import os
import json
from pathlib import Path

from smc_desk.evaluation.cohort_integrity import (
    case_ids_sha256,
    definition_case_set_sha256,
)

def main():
    print("Building the 20-chart Definition Set for BTCUSDT 15m...")
    base_dir = "data/gold_sets/definition_set_20"
    os.makedirs(base_dir, exist_ok=True)

    # We define 20 specific timestamps to act as the "decision_time" for these cases.
    # An analyst must replace and verify these before any evaluation use.
    
    cases = [
        # 5 Trends
        {"case_id": "trend_01", "type": "trend", "decision_time": "2026-06-01T12:00:00Z"},
        {"case_id": "trend_02", "type": "trend", "decision_time": "2026-06-02T12:00:00Z"},
        {"case_id": "trend_03", "type": "trend", "decision_time": "2026-06-03T12:00:00Z"},
        {"case_id": "trend_04", "type": "trend", "decision_time": "2026-06-04T12:00:00Z"},
        {"case_id": "trend_05", "type": "trend", "decision_time": "2026-06-05T12:00:00Z"},
        
        # 5 Ranges
        {"case_id": "range_01", "type": "range", "decision_time": "2026-06-06T12:00:00Z"},
        {"case_id": "range_02", "type": "range", "decision_time": "2026-06-07T12:00:00Z"},
        {"case_id": "range_03", "type": "range", "decision_time": "2026-06-08T12:00:00Z"},
        {"case_id": "range_04", "type": "range", "decision_time": "2026-06-09T12:00:00Z"},
        {"case_id": "range_05", "type": "range", "decision_time": "2026-06-10T12:00:00Z"},
        
        # 5 Transitions
        {"case_id": "transition_01", "type": "transition", "decision_time": "2026-06-11T12:00:00Z"},
        {"case_id": "transition_02", "type": "transition", "decision_time": "2026-06-12T12:00:00Z"},
        {"case_id": "transition_03", "type": "transition", "decision_time": "2026-06-13T12:00:00Z"},
        {"case_id": "transition_04", "type": "transition", "decision_time": "2026-06-14T12:00:00Z"},
        {"case_id": "transition_05", "type": "transition", "decision_time": "2026-06-15T12:00:00Z"},
        
        # 5 Ambiguous
        {"case_id": "ambiguous_01", "type": "ambiguous", "decision_time": "2026-06-16T12:00:00Z"},
        {"case_id": "ambiguous_02", "type": "ambiguous", "decision_time": "2026-06-17T12:00:00Z"},
        {"case_id": "ambiguous_03", "type": "ambiguous", "decision_time": "2026-06-18T12:00:00Z"},
        {"case_id": "ambiguous_04", "type": "ambiguous", "decision_time": "2026-06-19T12:00:00Z"},
        {"case_id": "ambiguous_05", "type": "ambiguous", "decision_time": "2026-06-20T12:00:00Z"},
    ]
    
    for case in cases:
        case_dir = os.path.join(base_dir, case["case_id"])
        os.makedirs(case_dir, exist_ok=True)
        
        # Write metadata
        with open(os.path.join(case_dir, "metadata.json"), "w") as f:
            json.dump({
                "instrument": "BTCUSDT",
                "timeframe": "15m",
                "decision_time": case["decision_time"],
                "regime_type": case["type"]
            }, f, indent=4)
            
        # Create empty annotation templates for 2 reviewers
        template = {
            "reviewer_id": "",
            "swings": [],
            "protected_structure": {},
            "structure_breaks": [],
            "fair_value_gaps": []
        }
        
        for reviewer in ["reviewer_A", "reviewer_B"]:
            with open(os.path.join(case_dir, f"{reviewer}.json"), "w") as f:
                json.dump(template, f, indent=4)

    # Machine-readable provenance. These cases are scaffolding for the review
    # workflow, not analyst-selected truth, and downstream tools must refuse to
    # turn them into accuracy metrics by default. The metadata hash prevents a
    # later timestamp/label edit from inheriting an earlier review claim.
    case_ids = [case["case_id"] for case in cases]
    base_path = Path(base_dir)
    with open(os.path.join(base_dir, "definition_set_status.json"), "w") as f:
        json.dump({
            "schema": "definition_set_status_v2",
            "selection_status": "PLACEHOLDER_NOT_ANALYST_REVIEWED",
            "analyst_id": None,
            "reviewed_at": None,
            "selection_rationale": "Sequential diagnostic scaffolding; not independently selected.",
            "created_by": "tools/build_definition_set.py",
            "known_limitations": [
                "Decision times are sequential framework placeholders.",
                "Regime labels are date-block labels and were not chart-verified.",
                "This output must not be described as a gold set or scored as perception accuracy."
            ],
            "allowed_use": "tooling diagnostics only",
            "scoreable": False,
            "case_count": len(case_ids),
            "case_ids_sha256": case_ids_sha256(case_ids),
            "case_set_sha256": definition_case_set_sha256(base_path, case_ids),
        }, f, indent=4)
                
    print(f"Successfully generated 20 case shells in {base_dir}")

if __name__ == "__main__":
    main()
