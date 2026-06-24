import hashlib
import json
import subprocess
import glob
from pathlib import Path

def file_hash(filepath):
    if not Path(filepath).exists():
        return None
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def get_git_commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()
    except Exception:
        return "Unknown"

snapshot = {
    "git_commit": get_git_commit(),
    "perception_engine_v2": file_hash("smc_desk/perception/engine_v2.py"),
    "ontology": file_hash("smc_desk/perception/ontology.py"),
    "renderer": file_hash("smc_desk/rendering/renderer_v2.py"),
    "vision_schema": file_hash("smc_desk/rendering/schema.py"),
    "knowledge_registry": file_hash("smc_desk/knowledge/source_registry.py"),
    "teacher_panel_annotator": file_hash("smc_desk/teacher_panel/chart_annotator.py"),
    "teacher_panel_aggregator": file_hash("smc_desk/teacher_panel/weak_label_aggregator.py"),
    "evaluation_comparator": file_hash("smc_desk/perception/comparator.py"),
    "thresholds": "Default Phase 5 Config"
}

out_path = "blackbox_gauntlet/registry/freeze_snapshot.json"
with open(out_path, "w") as f:
    json.dump(snapshot, f, indent=4)
print(f"Saved freeze snapshot to {out_path}.")
