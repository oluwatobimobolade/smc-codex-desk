#!/usr/bin/env python3
"""Validate and attach an externally reviewed perception label file to a case."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.perception_legacy import PerceptionAnnotationSet


def import_labels(case_path: Path, labels_path: Path) -> dict:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    if labels.get("case_id") and labels["case_id"] != case.get("case_id"):
        raise ValueError("label file case_id does not match target case")
    raw_annotations = labels.get("perception_annotations", labels)
    annotations = PerceptionAnnotationSet.model_validate(raw_annotations).model_dump(mode="json")
    expert_label = case.setdefault("expert_label", {})
    expert_label["perception_annotations"] = annotations
    case_path.write_text(json.dumps(case, indent=2), encoding="utf-8")
    return {
        "case_id": case.get("case_id"),
        "case_path": str(case_path),
        "label_status": annotations["label_status"],
        "annotation_count": len(annotations["objects"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import validated perception labels into one case.json.")
    parser.add_argument("--case", required=True, help="Target case.json path")
    parser.add_argument("--labels", required=True, help="Reviewed label JSON path")
    args = parser.parse_args()
    result = import_labels(Path(args.case), Path(args.labels))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
