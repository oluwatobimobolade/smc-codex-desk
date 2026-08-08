#!/usr/bin/env python3
"""Write the source-bound manifest for the perception-programme repair."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from smc_desk.data.hashing import file_sha256


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml",
    "specs/MARKET_STRUCTURE_CONSTITUTION_V1.sha256",
    "smc_desk/brain/annotation_semantics.py",
    "smc_desk/brain/structure_lab/annotation_bridge.py",
    "smc_desk/brain/structure_lab/context_retriever.py",
    "smc_desk/brain/structure_lab/runtime.py",
    "smc_desk/brain/structure_lab/tools.py",
    "smc_desk/perception/programme_run.py",
    "smc_desk/perception/programme_schema.py",
    "smc_desk/perception/candidates/atlas.py",
    "smc_desk/perception/candidates/changepoint.py",
    "smc_desk/perception/candidates/directional_change.py",
    "smc_desk/perception/candidates/displacement.py",
    "smc_desk/perception/candidates/fractal.py",
    "smc_desk/perception/candidates/indicators.py",
    "smc_desk/perception/candidates/prominence.py",
    "smc_desk/perception/candidates/schema.py",
    "smc_desk/perception/formal_structure_graph.py",
    "smc_desk/perception/swings.py",
    "smc_desk/structure/active_range.py",
    "smc_desk/structure/doctrine.py",
    "smc_desk/structure/inducement.py",
    "smc_desk/structure/level_interactions.py",
    "smc_desk/structure/poi_ranker.py",
    "smc_desk/structure/protected_point.py",
    "smc_desk/validation/evidence.py",
    "smc_desk/validation/invariants.py",
    "smc_desk/validation/narrative.py",
    "smc_desk/validation/temporal.py",
    "smc_desk/validation/validators.py",
    "tests/test_anchor_preserving_retriever.py",
    "tests/test_br004_006_ai_first_readiness.py",
    "tests/test_candidate_atlas.py",
    "tests/test_deterministic_validators.py",
    "tests/test_level_interactions.py",
    "tests/test_market_structure_constitution.py",
    "tests/test_perception_harness.py",
    "tests/test_perception_programme_run.py",
    "tests/test_protected_point_and_range.py",
    "tests/test_swing_tie_and_dual_pivot.py",
    "tests/test_wp0041b_ai_annotation_render_loop.py",
    "tools/write_perception_programme_repair_manifest.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="foundation_programme/PERCEPTION_READINESS_BRIDGE/PERCEPTION_PROGRAMME_REPAIR_SOURCE_MANIFEST.tsv",
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
        "# Perception programme integrity repair source manifest",
        f"# baseline_head\t{git_head}",
        "# source_state\tdirty_worktree_source_bound_validation",
        "# excludes\tgovernance reports, validation registry, generated runs, and this manifest output",
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
