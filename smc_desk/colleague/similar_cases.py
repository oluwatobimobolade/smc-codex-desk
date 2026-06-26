from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def case_signature(run_dir: Path) -> dict[str, Any]:
    scenario = _load_json(run_dir / "scenarios" / "scenario_tree.json") or {}
    decision = _load_json(run_dir / "scenarios" / "decision.json") or {}
    graph = _load_json(run_dir / "perception" / "mtf_state_graph.json") or {}
    manifest = _load_json(run_dir / "run_manifest.json") or {}
    first = (scenario.get("scenarios") or [{}])[0]
    story = graph.get("market_story") or {}
    blockers = {
        item.get("condition")
        for item in story.get("execution_blockers", [])
        if item.get("condition")
    }
    semantic_counts = story.get("semantic_summary") or {}
    return {
        "run_dir": str(run_dir.resolve()),
        "run_id": manifest.get("run_id") or run_dir.name,
        "symbol": manifest.get("symbol"),
        "decision_action": decision.get("action"),
        "scenario_direction": first.get("direction"),
        "setup_stage": first.get("setup_stage"),
        "execution_consensus": story.get("htf_alignment", {}).get("execution_consensus"),
        "blockers": sorted(blockers),
        "semantic_counts": semantic_counts,
    }


def similarity_score(a: dict[str, Any], b: dict[str, Any]) -> float:
    score = 0.0
    if a.get("symbol") == b.get("symbol"):
        score += 0.15
    for key, weight in (
        ("decision_action", 0.15),
        ("scenario_direction", 0.15),
        ("setup_stage", 0.15),
        ("execution_consensus", 0.15),
    ):
        if a.get(key) and a.get(key) == b.get(key):
            score += weight
    a_blockers = set(a.get("blockers") or [])
    b_blockers = set(b.get("blockers") or [])
    if a_blockers or b_blockers:
        score += 0.20 * (len(a_blockers & b_blockers) / max(1, len(a_blockers | b_blockers)))
    a_sem = set((a.get("semantic_counts") or {}).keys())
    b_sem = set((b.get("semantic_counts") or {}).keys())
    if a_sem or b_sem:
        score += 0.05 * (len(a_sem & b_sem) / max(1, len(a_sem | b_sem)))
    return round(min(score, 1.0), 4)


def retrieve_similar_cases(
    *,
    current_run_dir: Path,
    analysis_runs_root: Path,
    limit: int = 5,
) -> dict[str, Any]:
    current = case_signature(current_run_dir)
    matches: list[dict[str, Any]] = []
    if analysis_runs_root.exists():
        for run_dir in sorted(path for path in analysis_runs_root.iterdir() if path.is_dir()):
            if run_dir.resolve() == current_run_dir.resolve():
                continue
            if not (run_dir / "run_manifest.json").exists():
                continue
            candidate = case_signature(run_dir)
            score = similarity_score(current, candidate)
            if score > 0:
                matches.append({"score": score, "case": candidate})
    matches.sort(key=lambda item: item["score"], reverse=True)
    return {
        "status": "retrieved" if matches else "no_similar_cases_found",
        "method": "deterministic_signature_overlap_v0",
        "current_signature": current,
        "matches": matches[:limit],
        "authority": "research_context_only_not_predictive_probability",
    }
