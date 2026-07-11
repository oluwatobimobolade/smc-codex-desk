#!/usr/bin/env python3
"""Write the source-bound manifest for the BR-004 through BR-006 AI-first slice."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from smc_desk.data.hashing import file_sha256


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "specs/AI_CENTERED_STRUCTURE_REASONING_V1.yaml",
    "smc_desk/brain/doctrine_panel.py",
    "smc_desk/brain/structure_reasoning_roles.py",
    "smc_desk/brain/structure_lab/__init__.py",
    "smc_desk/brain/structure_lab/prompts.py",
    "smc_desk/brain/structure_lab/runtime.py",
    "smc_desk/brain/structure_lab/schemas.py",
    "smc_desk/data/hashing.py",
    "smc_desk/evaluation/ai_consensus.py",
    "smc_desk/research/__init__.py",
    "smc_desk/research/benchmark_partitions.py",
    "tools/build_ai_public_benchmark_pilot.py",
    "tools/finalize_ai_doctrine_panel.py",
    "tools/init_ai_perception_readiness.py",
    "tools/run_ai_structure_lab.py",
    "tools/run_validation_registry.py",
    "tools/write_ai_first_source_manifest.py",
    "tests/test_br004_006_ai_first_readiness.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="foundation_programme/PERCEPTION_READINESS_BRIDGE/BR004_006_SOURCE_MANIFEST.tsv",
    )
    args = parser.parse_args()
    output = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    records: list[tuple[str, str, int]] = []
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        if not path.exists():
            raise FileNotFoundError(path)
        records.append((relative, file_sha256(path), path.stat().st_size))
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    lines = [
        "# BR-004 through BR-006 AI-first source manifest",
        f"# baseline_head\t{git_head}",
        "# source_state\tdirty_worktree_source_bound_validation",
        "# excludes\tgovernance reports, validation registry, generated runs, and this manifest to avoid circular hashing",
        "path\tsha256\tsize_bytes",
        *(f"{relative}\t{digest}\t{size}" for relative, digest, size in records),
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
