#!/usr/bin/env python3
"""Initialize protected benchmarks and export the AI doctrine research panel."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smc_desk.brain.doctrine_panel import export_doctrine_panel_packets
from smc_desk.research.benchmark_partitions import (
    ProtectedBenchmarkStore,
    build_unpopulated_registry,
    validate_benchmark_registry,
)


DEFAULT_DOCTRINE_SOURCES = [
    "specs/PERCEPTION_ANNOTATION_MANUAL_V1.md",
    "strategies/smc/STRUCTURE_DOCTRINE.md",
    "strategies/smc/CONSENSUS_SMC_RESEARCH.md",
    "strategies/smc/POI_REFINEMENT_DOCTRINE.md",
    "strategies/smc/VISUAL_ACCURACY_SPEC.md",
    "governance/FAILURE_REGISTER.md",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="research_lab/ai_perception_readiness")
    parser.add_argument("--doctrine-sources", nargs="*", default=DEFAULT_DOCTRINE_SOURCES)
    args = parser.parse_args()
    root = Path(args.out).expanduser().resolve()
    benchmark_root = root / "protected_benchmark"
    registry = build_unpopulated_registry(benchmark_root)
    store = ProtectedBenchmarkStore(benchmark_root)
    registry_path = store.register(registry)
    validation = validate_benchmark_registry(registry)
    doctrine = export_doctrine_panel_packets(
        source_paths=[Path(path) for path in args.doctrine_sources],
        output_dir=root / "ai_doctrine_panel",
    )
    summary = {
        "schema": "ai_perception_readiness_initialization_v1",
        "root": str(root),
        "benchmark_registry": str(registry_path),
        "benchmark_validation": validation,
        "doctrine_panel": doctrine,
        "operating_model": "AI_FIRST_HUMAN_CERTIFICATION_LATER",
        "blind_cases_populated": False,
        "human_gold_created": False,
        "readiness_gate_passed": False,
    }
    (root / "readiness_initialization.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
