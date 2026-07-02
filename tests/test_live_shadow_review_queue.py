from __future__ import annotations

import json
from pathlib import Path

from tools.build_live_shadow_review_queue import build_review_queue


def _write_run(root: Path, *, action: str = "NO_SETUP", with_charts: bool = True) -> Path:
    run_dir = root / "live_shadow" / "symbols" / "BTCUSDT" / "colleague_run"
    (run_dir / "scenarios").mkdir(parents=True)
    (run_dir / "perception").mkdir()
    (run_dir / "external").mkdir()
    if with_charts:
        (run_dir / "charts" / "clean").mkdir(parents=True)
        for tf in ("15m", "1h", "4h", "1d"):
            (run_dir / "charts" / "clean" / f"BTCUSDT_{tf}_clean.png").write_bytes(f"{tf}".encode())
    request_path = run_dir / "request.json"
    request_path.write_text("{}", encoding="utf-8")
    manifest = {
        "symbol": "BTCUSDT",
        "decision_candle_open": "2026-01-01T12:00:00",
        "decision_available_at": "2026-01-01T12:15:00",
        "files": {"request.json": {"path": str(request_path.resolve())}},
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "scenarios" / "decision.json").write_text(json.dumps({"action": action}), encoding="utf-8")
    (run_dir / "scenarios" / "scenario_tree.json").write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    (run_dir / "perception" / "mtf_state_graph.json").write_text(json.dumps({"nodes": []}), encoding="utf-8")
    (run_dir / "perception" / "objects.json").write_text(json.dumps({"timeframes": {}}), encoding="utf-8")
    (run_dir / "external" / "alignment_report.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    return run_dir


def test_build_review_queue_creates_blind_templates_and_sealed_context(tmp_path: Path) -> None:
    _write_run(tmp_path)

    manifest = build_review_queue(
        analysis_root=tmp_path,
        output_dir=tmp_path / "review_queue",
        actions=["NO_SETUP"],
        reviewers=["reviewer_a", "reviewer_b"],
    )

    assert manifest["status"] == "ready_for_review"
    assert manifest["case_count"] == 1
    case_dir = Path(manifest["cases"][0]["case_dir"])
    prompt = (case_dir / "review_prompt.md").read_text(encoding="utf-8")
    reviewer = json.loads((case_dir / "reviewer_a.json").read_text(encoding="utf-8"))
    sealed = json.loads((case_dir / "sealed_engine_context.json").read_text(encoding="utf-8"))
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))

    assert "Do not inspect `sealed_engine_context.json`" in prompt
    assert reviewer["perception_annotations"]["label_status"] == "draft"
    assert sealed["authority"] == "sealed_engine_context_not_gold_truth"
    assert case["truth_policy"].startswith("reviewer_drafts_are_not_gold")
