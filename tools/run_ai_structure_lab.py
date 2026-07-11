#!/usr/bin/env python3
"""Run the governed six-role AI structure lab from an evidence pack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smc_desk.brain.structure_lab import CallableRoleProvider, ReplayRoleProvider, run_structure_lab
from smc_desk.rendering.structure_lab_annotation_renderer import render_structure_lab_annotation_pack


def build_case(evidence_pack: dict) -> dict:
    graph = evidence_pack.get("formal_structure_graph") or {}
    charts = {}
    for timeframe, raw in (evidence_pack.get("chart_images") or {}).items():
        item = dict(raw) if isinstance(raw, dict) else {"path": str(raw)}
        item.pop("base64", None)
        charts[timeframe] = item
    return {
        "case_id": f"{evidence_pack.get('symbol', 'UNKNOWN')}_{str(graph.get('decision_time') or 'UNKNOWN').replace(':', '')}",
        "symbol": evidence_pack.get("symbol"),
        "decision_time": graph.get("decision_time"),
        "chart_manifest": charts,
        "candidate_objects": evidence_pack.get("detector_candidates") or {},
        "formal_structure_graph": graph,
        "render_manifest": {"status": "EXISTING_CHARTS_ONLY", "charts": charts},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-pack", required=True)
    parser.add_argument("--responses", required=True, help="Six-role response bundle JSON.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-repair-attempts", type=int, choices=[0, 1], default=1)
    parser.add_argument(
        "--provider-mode",
        choices=["OFFLINE_REPLAY_PROVIDER", "MANUAL_AI_ASSISTED_JSON"],
        default="OFFLINE_REPLAY_PROVIDER",
        help="Replay is deterministic test evidence; manual mode records AI-supplied role JSON without an API call.",
    )
    parser.add_argument("--provider-name", default="manual-ai-structure-review")
    parser.add_argument("--model-name", default="unspecified-ai-model")
    parser.add_argument(
        "--skip-annotation-render",
        action="store_true",
        help="Diagnostic only: omit the professional render bridge. A PASS visual verdict will then require a pre-rendered case manifest.",
    )
    args = parser.parse_args()
    evidence_pack = json.loads(Path(args.evidence_pack).read_text(encoding="utf-8"))
    responses = json.loads(Path(args.responses).read_text(encoding="utf-8"))
    if args.provider_mode == "OFFLINE_REPLAY_PROVIDER":
        provider = ReplayRoleProvider(responses)
    else:
        provider = CallableRoleProvider(
            lambda role, _prompt, _payload, _attempt: responses[role],
            provider_name=args.provider_name,
            model_name=args.model_name,
            provider_mode="MANUAL_AI_ASSISTED_JSON",
        )
    graph = evidence_pack.get("formal_structure_graph") or {}
    parent_child = graph.get("parent_child_context") or {}
    official_state = str(parent_child.get("required_trade_state") or "THESIS_ONLY")

    def annotation_renderer(semantic_plan, _outputs, render_dir):
        return render_structure_lab_annotation_pack(
            evidence_pack=evidence_pack,
            semantic_plan=semantic_plan,
            output_dir=render_dir,
            official_state=official_state,
        )

    manifest = run_structure_lab(
        case=build_case(evidence_pack),
        provider=provider,
        output_dir=args.out,
        max_repair_attempts=args.max_repair_attempts,
        annotation_renderer=None if args.skip_annotation_render else annotation_renderer,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["final_status"] in {"AI_PANEL_COMPLETE", "REVISION_REQUIRED", "REVIEW_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
