#!/usr/bin/env python3
"""Build human-review packets from Market Colleague live-shadow packages."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.case_library import file_sha256
from smc_desk.perception_legacy import perception_annotation_scaffold


TF_LABELS = {"1d": "1D", "4h": "4H", "1h": "1H", "15m": "15"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_dirs(root: Path) -> list[Path]:
    return sorted(path.parent for path in root.rglob("run_manifest.json"))


def _chart_paths(run_dir: Path, symbol: str) -> dict[str, str]:
    charts: dict[str, str] = {}
    for tf, label in TF_LABELS.items():
        path = run_dir / "charts" / "clean" / f"{symbol}_{tf}_clean.png"
        if path.exists():
            charts[label] = str(path.resolve())
    return charts


def _review_template(case_id: str, reviewer_id: str) -> dict[str, Any]:
    annotations = perception_annotation_scaffold()
    annotations["label_status"] = "draft"
    annotations["reviewer_ids"] = [reviewer_id]
    return {
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "human_review_live_shadow_queue",
        "perception_annotations": annotations,
        "reviewer_decision": {
            "market_read": "unfilled",
            "agrees_with_engine_action": None,
            "should_watch": None,
            "reason": "",
        },
    }


def _adjudication_template(case_id: str, reviewers: list[str]) -> dict[str, Any]:
    annotations = perception_annotation_scaffold()
    annotations["label_status"] = "missing"
    annotations["reviewer_ids"] = reviewers
    return {
        "case_id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "adjudicator_resolution_template",
        "perception_annotations": annotations,
        "adjudicator_justification": "",
        "truth_policy": "Only completed adjudication may become gold. Reviewer drafts and engine context remain non-gold evidence.",
    }


def _prompt(case: dict[str, Any], reviewers: list[str]) -> str:
    lines = [
        f"# Live-Shadow Human Review - {case['case_id']}",
        "",
        "Review the clean charts first. Do not inspect `sealed_engine_context.json` until after both independent reviews are filled.",
        "",
        f"- Symbol: `{case['symbol']}`",
        f"- Decision available at: `{case['decision_available_at']}`",
        f"- Engine action bucket: `{case['engine_action_bucket']}`",
        f"- Reviewer templates: {', '.join(f'`{reviewer}.json`' for reviewer in reviewers)}",
        "",
        "## Clean Charts",
        "",
    ]
    for label in ("1D", "4H", "1H", "15"):
        chart = case["chart_evidence"]["screenshots"].get(label)
        if chart:
            lines.extend([f"### {label}", f"![{case['symbol']} {label}]({chart})", ""])
    lines.extend(
        [
            "## Instructions",
            "",
            "- Mark only visible closed-candle SMC objects.",
            "- If unsure, leave the object out or mark low confidence in notes.",
            "- This review is not a trade signal.",
            "- Gold truth requires two independent reviews plus adjudicator resolution.",
        ]
    )
    return "\n".join(lines) + "\n"


def _sealed_engine_context(run_dir: Path) -> dict[str, Any]:
    files = {}
    for relative in [
        "scenarios/decision.json",
        "scenarios/scenario_tree.json",
        "perception/mtf_state_graph.json",
        "perception/objects.json",
        "external/alignment_report.json",
    ]:
        path = run_dir / relative
        files[relative] = {
            "path": str(path.resolve()),
            "exists": path.exists(),
            "sha256": file_sha256(path) if path.exists() else None,
        }
    return {
        "authority": "sealed_engine_context_not_gold_truth",
        "review_policy": "Use only after independent reviewer drafts are complete.",
        "files": files,
    }


def build_review_queue(
    *,
    analysis_root: Path,
    output_dir: Path,
    actions: list[str] | None = None,
    reviewers: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    actions = [str(action).upper() for action in (actions or ["WATCH", "NO_SETUP"])]
    reviewers = reviewers or ["reviewer_a", "reviewer_b"]
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for run_dir in _run_dirs(analysis_root.expanduser().resolve()):
        manifest = _load_json(run_dir / "run_manifest.json")
        symbol = str(manifest.get("symbol") or run_dir.name)
        decision_path = run_dir / "scenarios" / "decision.json"
        if not decision_path.exists():
            skipped.append({"run_dir": str(run_dir), "reason": "missing_decision"})
            continue
        decision = _load_json(decision_path)
        action = str(decision.get("action") or "").upper()
        if action not in actions:
            skipped.append({"run_dir": str(run_dir), "reason": f"action_{action}_not_requested"})
            continue
        charts = _chart_paths(run_dir, symbol)
        if not charts:
            skipped.append({"run_dir": str(run_dir), "reason": "missing_clean_charts"})
            continue

        case_id = f"{symbol}_{manifest.get('decision_available_at', '').replace(':', '').replace('-', '').replace('T', '_')}_review"
        case_dir = output_dir / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        case = {
            "case_schema_version": "live_shadow_review_v0.1",
            "case_id": case_id,
            "source_run_dir": str(run_dir.resolve()),
            "source_run_manifest": str((run_dir / "run_manifest.json").resolve()),
            "symbol": symbol,
            "decision_candle_open": manifest.get("decision_candle_open"),
            "decision_available_at": manifest.get("decision_available_at"),
            "engine_action_bucket": action,
            "chart_evidence": {"screenshots": charts},
            "truth_policy": "reviewer_drafts_are_not_gold; adjudicated labels only become gold.",
            "engine_weak_labels": "sealed_engine_context.json",
        }
        (case_dir / "case.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
        (case_dir / "review_prompt.md").write_text(_prompt(case, reviewers), encoding="utf-8")
        (case_dir / "sealed_engine_context.json").write_text(json.dumps(_sealed_engine_context(run_dir), indent=2), encoding="utf-8")
        (case_dir / "adjudication_template.json").write_text(json.dumps(_adjudication_template(case_id, reviewers), indent=2), encoding="utf-8")
        for reviewer in reviewers:
            (case_dir / f"{reviewer}.json").write_text(json.dumps(_review_template(case_id, reviewer), indent=2), encoding="utf-8")
        cases.append(
            {
                "case_id": case_id,
                "case_dir": str(case_dir.resolve()),
                "source_run_dir": str(run_dir.resolve()),
                "symbol": symbol,
                "decision_action": action,
                "decision_available_at": manifest.get("decision_available_at"),
            }
        )
        if limit is not None and len(cases) >= limit:
            break

    manifest = {
        "review_queue_version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_root": str(analysis_root.expanduser().resolve()),
        "output_dir": str(output_dir),
        "actions": actions,
        "reviewers": reviewers,
        "case_count": len(cases),
        "cases": cases,
        "skipped": skipped,
        "status": "ready_for_review" if cases else "no_eligible_cases",
        "truth_policy": "No review output is gold until adjudicated.json is completed by an adjudicator.",
        "market_edge_claimed": False,
    }
    (output_dir / "review_queue_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build human review queue from colleague/live-shadow packages.")
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--actions", nargs="+", default=["WATCH", "NO_SETUP"])
    parser.add_argument("--reviewers", nargs="+", default=["reviewer_a", "reviewer_b"])
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_review_queue(
        analysis_root=Path(args.analysis_root),
        output_dir=Path(args.output_dir),
        actions=args.actions,
        reviewers=args.reviewers,
        limit=args.limit,
    )
    print(json.dumps({"status": manifest["status"], "case_count": manifest["case_count"], "output_dir": manifest["output_dir"]}, indent=2))


if __name__ == "__main__":
    main()
