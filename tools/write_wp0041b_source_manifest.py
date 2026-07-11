#!/usr/bin/env python3
"""Write the source-and-input manifest for the WP-0041B annotation loop."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from smc_desk.data.hashing import file_sha256


ROOT = Path(__file__).resolve().parents[1]
SOURCE_AND_INPUT_PATHS = (
    "smc_desk/brain/annotation_evidence.py",
    "smc_desk/brain/structure_lab/__init__.py",
    "smc_desk/brain/structure_lab/annotation_bridge.py",
    "smc_desk/brain/structure_lab/runtime.py",
    "smc_desk/brain/structure_lab/schemas.py",
    "smc_desk/rendering/structure_lab_annotation_renderer.py",
    "tools/run_ai_structure_lab.py",
    "tools/write_wp0041b_source_manifest.py",
    "tests/test_wp0041b_ai_annotation_render_loop.py",
    "tests/test_br004_006_ai_first_readiness.py",
    "research_lab/ai_perception_readiness/structure_lab_replays/BTCUSDT_20260709/responses.json",
    "analysis_runs/WP0041_PROFESSIONAL_ANNOTATION_SMOKE/LIVE_FULL_SYSTEM_AI_SMC_V3_20260709_190455/BTCUSDT/10_smc_evidence_pack/evidence_pack.json",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="foundation_programme/PERCEPTION_READINESS_BRIDGE/WP0041B_SOURCE_MANIFEST.tsv",
    )
    args = parser.parse_args()
    output = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    records: list[tuple[str, str, int]] = []
    for relative in SOURCE_AND_INPUT_PATHS:
        path = ROOT / relative
        if not path.exists():
            raise FileNotFoundError(path)
        records.append((relative, file_sha256(path), path.stat().st_size))

    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    lines = [
        "# WP-0041B professional AI annotation render-loop manifest",
        f"# baseline_head\t{git_head}",
        "# source_state\tdirty_worktree_source_and_input_bound_validation",
        "# excludes\tgovernance reports, validation registry, generated render outputs, and this manifest output",
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
