"""
Pilot Runner — Phase 2 Adjudication Case Pack Generator.

Generates reviewer-ready annotation templates from the pilot cohort.
Each template conforms to the annotation_schema.py contract.

Usage:
    python tools/pilot_runner.py --cohort case_library/pilot_cohort --output pilot_v1/reviewer_packs
    python tools/pilot_runner.py --cohort case_library/pilot_cohort --output pilot_v1/reviewer_packs --reviewers 2
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


VALID_PRIMITIVES = [
    "swing_high", "swing_low",
    "bos_bullish", "bos_bearish",
    "choch_bullish", "choch_bearish",
    "fvg_bullish", "fvg_bearish",
    "sweep_bullish", "sweep_bearish",
    "protected_high", "protected_low",
    "ambiguous", "insufficient_context"
]


def generate_annotation_template(case_id: str, reviewer_id: str) -> dict:
    """Generate a blank annotation template for a reviewer."""
    return {
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "annotations": [],
        "completed_at": None,
        "reviewer_notes": "",
        "_instructions": (
            "Fill in the 'annotations' array with structural objects you identify. "
            "Each annotation must have: primitive, direction, scope, timestamp, price. "
            f"Valid primitives: {VALID_PRIMITIVES}. "
            "Valid directions: bullish, bearish. "
            "Valid scopes: local, internal, external. "
            "Set is_ambiguous=true if the structure is unclear. "
            "Set completed_at to an ISO 8601 timestamp when you finish."
        ),
        "_annotation_template": {
            "case_id": case_id,
            "reviewer_id": reviewer_id,
            "primitive": "<FILL>",
            "direction": "<FILL: bullish or bearish>",
            "scope": "<FILL: local, internal, or external>",
            "timestamp": "<FILL: ISO 8601 timestamp of the pivot/event candle>",
            "price": 0.0,
            "confidence": 1.0,
            "notes": "",
            "is_ambiguous": False
        }
    }


def build_reviewer_pack(
    cohort_dir: Path,
    output_dir: Path,
    num_reviewers: int = 2,
) -> dict:
    """Build reviewer packs from a pilot cohort directory."""
    
    cases_dir = cohort_dir / "cases"
    manifest_path = cohort_dir / "cohort_manifest.json"
    
    if not cases_dir.exists():
        raise FileNotFoundError(f"Cases directory not found: {cases_dir}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Cohort manifest not found: {manifest_path}")
    
    with manifest_path.open("r") as f:
        manifest = json.load(f)
    
    case_ids = [c["case_id"] for c in manifest.get("cases", [])]
    
    # Find cases that actually exist on disk
    existing_cases = []
    for case_id in case_ids:
        case_path = cases_dir / case_id
        if case_path.exists() and (case_path / "public_manifest.json").exists():
            existing_cases.append(case_id)
    
    if not existing_cases:
        raise ValueError("No valid cases found in cohort")
    
    # Create reviewer packs
    generated_at = datetime.now(timezone.utc).isoformat()
    pack_summary = {
        "generated_at": generated_at,
        "cohort_source": str(cohort_dir),
        "total_cases": len(existing_cases),
        "num_reviewers": num_reviewers,
        "reviewers": []
    }
    
    for rev_idx in range(num_reviewers):
        reviewer_id = f"reviewer_{rev_idx:02d}"
        reviewer_dir = output_dir / reviewer_id
        
        # Create reviewer directory with case charts and templates
        annotations_dir = reviewer_dir / "annotations"
        charts_dir = reviewer_dir / "charts"
        annotations_dir.mkdir(parents=True, exist_ok=True)
        charts_dir.mkdir(parents=True, exist_ok=True)
        
        for case_id in existing_cases:
            case_path = cases_dir / case_id
            
            # Copy clean review chart (no engine annotations — blind review)
            clean_chart = case_path / "clean_review.png"
            if clean_chart.exists():
                shutil.copy2(clean_chart, charts_dir / f"{case_id}_clean.png")
            
            # Copy public manifest (venue, symbol, timeframe, decision time)
            pub_manifest = case_path / "public_manifest.json"
            if pub_manifest.exists():
                shutil.copy2(pub_manifest, charts_dir / f"{case_id}_manifest.json")
            
            # Generate blank annotation template
            template = generate_annotation_template(case_id, reviewer_id)
            template_path = annotations_dir / f"{case_id}_annotations.json"
            with template_path.open("w") as f:
                json.dump(template, f, indent=2)
        
        # Create reviewer instructions
        instructions = {
            "reviewer_id": reviewer_id,
            "total_cases": len(existing_cases),
            "instructions": (
                "For each case, examine the clean chart image in the charts/ folder. "
                "Open the corresponding annotation template in annotations/. "
                "Add all structural objects you identify to the 'annotations' array. "
                "When finished with all cases, set 'completed_at' in each file. "
                "Do NOT look at other reviewers' work. This is a blind review."
            ),
            "reference_manual": "specs/PERCEPTION_ANNOTATION_MANUAL_V1.md",
            "reference_ontology": "specs/PERCEPTION_ONTOLOGY_V2.yaml"
        }
        with (reviewer_dir / "INSTRUCTIONS.json").open("w") as f:
            json.dump(instructions, f, indent=2)
        
        pack_summary["reviewers"].append({
            "reviewer_id": reviewer_id,
            "pack_path": str(reviewer_dir),
            "cases_assigned": len(existing_cases)
        })
    
    # Write pack summary
    with (output_dir / "pack_summary.json").open("w") as f:
        json.dump(pack_summary, f, indent=2)
    
    return pack_summary


def main():
    parser = argparse.ArgumentParser(description="Generate reviewer packs for Phase 2 adjudication")
    parser.add_argument("--cohort", required=True, help="Path to pilot cohort directory")
    parser.add_argument("--output", required=True, help="Output directory for reviewer packs")
    parser.add_argument("--reviewers", type=int, default=2, help="Number of reviewers (default: 2)")
    args = parser.parse_args()
    
    summary = build_reviewer_pack(
        cohort_dir=Path(args.cohort),
        output_dir=Path(args.output),
        num_reviewers=args.reviewers,
    )
    
    print(f"✅ Generated {summary['num_reviewers']} reviewer packs for {summary['total_cases']} cases")
    print(f"   Output: {args.output}")
    for rev in summary["reviewers"]:
        print(f"   - {rev['reviewer_id']}: {rev['cases_assigned']} cases at {rev['pack_path']}")


if __name__ == "__main__":
    main()
