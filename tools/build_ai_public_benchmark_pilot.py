#!/usr/bin/env python3
"""Register public AI research cases without populating the blind benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smc_desk.research.benchmark_partitions import (
    ProtectedBenchmarkStore,
    build_public_benchmark_pilot,
    validate_benchmark_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="protected_benchmark directory")
    parser.add_argument("--development-pack", required=True)
    parser.add_argument("--annotation-pack", required=True)
    parser.add_argument("--context-hours", type=int, default=24)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    registry = build_public_benchmark_pilot(
        root,
        development_evidence_pack=args.development_pack,
        annotation_evidence_pack=args.annotation_pack,
        context_hours=args.context_hours,
    )
    store = ProtectedBenchmarkStore(root)
    registry_path = store.register(registry)
    validation = validate_benchmark_registry(registry)
    summary = {
        "schema": "ai_public_benchmark_pilot_v1",
        "registry_path": str(registry_path),
        "validation": validation,
        "blind_cases_populated": False,
        "truth_boundary": "PUBLIC_AI_WEAK_LABELS_ONLY",
        "human_gold_created": False,
    }
    summary_path = root / "public" / "benchmark_pilot_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
