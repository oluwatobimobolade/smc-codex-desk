import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def file_hash(filepath):
    path = ROOT / filepath
    if not path.exists():
        return None
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def git_output(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT).decode('utf-8').strip()


def get_git_commit():
    try:
        return git_output(['git', 'rev-parse', 'HEAD'])
    except Exception:
        return "Unknown"


def get_git_status_short() -> list[str]:
    try:
        output = git_output(['git', 'status', '--short'])
    except Exception:
        return []
    return [line for line in output.splitlines() if line.strip()]


FROZEN_FILES = {
    "perception_engine_v2": "smc_desk/perception/engine_v2.py",
    "ontology": "smc_desk/perception/ontology.py",
    "renderer": "smc_desk/rendering/chart_renderer.py",
    "vision_schema": "smc_desk/vision/schemas.py",
    "knowledge_registry": "smc_desk/knowledge/source_registry.py",
    "teacher_panel_annotator": "smc_desk/teacher_panel/chart_annotator.py",
    "teacher_panel_aggregator": "smc_desk/teacher_panel/weak_label_aggregator.py",
    "evaluation_comparator": "smc_desk/perception/comparator.py",
    "thresholds": "specs/PERCEPTION_ONTOLOGY_V2.yaml",
}


def build_snapshot() -> dict:
    file_hashes = {name: file_hash(path) for name, path in FROZEN_FILES.items()}
    missing = [path for name, path in FROZEN_FILES.items() if file_hashes[name] is None]
    git_status = get_git_status_short()
    return {
        "git_commit": get_git_commit(),
        "working_tree_dirty": bool(git_status),
        "git_status_short": git_status,
        "missing_files": missing,
        **file_hashes,
    }


def main() -> None:
    snapshot = build_snapshot()
    out_path = ROOT / "blackbox_gauntlet/registry/freeze_snapshot.json"
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=4)
    print(f"Saved freeze snapshot to {out_path}.")
    if snapshot["working_tree_dirty"]:
        print("WARNING: freeze snapshot was generated from a dirty working tree.")
    if snapshot["missing_files"]:
        print(f"WARNING: missing frozen files: {snapshot['missing_files']}")


if __name__ == "__main__":
    main()
