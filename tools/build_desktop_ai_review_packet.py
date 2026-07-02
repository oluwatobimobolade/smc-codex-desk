#!/usr/bin/env python3
"""Build no-API desktop AI reviewer packets for local SMC cases.

The packet is designed for Codex/Claude desktop style use: open the prompt,
inspect the clean chart images, and fill the response JSON manually. It does
not call any model API and intentionally excludes engine overlays/weak labels.
"""
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

from smc_desk.perception_legacy import perception_annotation_scaffold


MANUAL_PATH = ROOT / "specs" / "PERCEPTION_ANNOTATION_MANUAL_V1.md"
ONTOLOGY_PATH = ROOT / "specs" / "PERCEPTION_ONTOLOGY_V2.yaml"


def _case_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("case.json") if path.is_file())


def _load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _response_template(case_id: str, reviewer_id: str) -> dict[str, Any]:
    annotations = perception_annotation_scaffold()
    annotations["label_status"] = "draft"
    annotations["reviewer_ids"] = [reviewer_id]
    return {
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "desktop_ai_no_api",
        "perception_annotations": annotations,
        "reviewer_reasoning": "",
    }


def _prompt(case: dict[str, Any], reviewer_id: str, response_path: Path) -> str:
    screenshots = case.get("chart_evidence", {}).get("screenshots", {})
    lines = [
        f"# Desktop AI SMC Review Packet - {case.get('case_id')}",
        "",
        "You are acting as a blind SMC perception reviewer. Use only the clean raw chart images below and the manual/ontology references. Do not use engine overlays, machine analysis, weak labels, or future candles.",
        "",
        "Return only JSON matching the response template. If uncertain, leave the object out or mark low confidence in notes.",
        "",
        f"- Reviewer ID: `{reviewer_id}`",
        f"- Symbol: `{case.get('symbol')}`",
        f"- Decision time: `{case.get('decision_time')}`",
        f"- Response template: `{response_path.resolve()}`",
        f"- Manual: `{MANUAL_PATH}`",
        f"- Ontology: `{ONTOLOGY_PATH}`",
        "",
        "## Clean Charts",
        "",
    ]
    for label in ("1D", "4H", "1H", "15"):
        screenshot = screenshots.get(label)
        if screenshot:
            lines.extend([f"### {label}", f"![{case.get('symbol')} {label}]({screenshot})", ""])
    lines.extend(
        [
            "## Required JSON Contract",
            "",
            "- `perception_annotations.label_status` must remain `draft` for this pass.",
            "- Events require `timestamp` and `price`.",
            "- Zones require `price_low` and `price_high`.",
            "- BOS/CHoCH require `structure_scope` when visible.",
            "- This output is an independent reviewer draft, not adjudicated truth.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_packets(root: Path, output_dir: Path, reviewer_id: str, limit: int | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    packets = []
    for case_path in _case_files(root):
        case = _load_case(case_path)
        case_id = str(case.get("case_id") or case_path.parent.name)
        response_path = output_dir / f"{case_id}.{reviewer_id}.response_template.json"
        prompt_path = output_dir / f"{case_id}.{reviewer_id}.prompt.md"
        response_path.write_text(json.dumps(_response_template(case_id, reviewer_id), indent=2), encoding="utf-8")
        prompt_path.write_text(_prompt(case, reviewer_id, response_path), encoding="utf-8")
        packets.append(
            {
                "case_id": case_id,
                "case_path": str(case_path.resolve()),
                "prompt": str(prompt_path.resolve()),
                "response_template": str(response_path.resolve()),
                "symbol": case.get("symbol"),
                "decision_time": case.get("decision_time"),
            }
        )
        if limit is not None and len(packets) >= limit:
            break
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "reviewer_id": reviewer_id,
        "mode": "desktop_ai_no_api",
        "policy": "Packets include clean charts and schemas only; engine weak labels and machine analysis are excluded.",
        "packet_count": len(packets),
        "packets": packets,
    }
    (output_dir / "desktop_ai_review_packet_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build no-API desktop AI review packets.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reviewer-id", default="desktop_ai_reviewer")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    manifest = build_packets(Path(args.root), Path(args.output_dir), args.reviewer_id, args.limit)
    print(f"Built {manifest['packet_count']} desktop AI review packets at {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
