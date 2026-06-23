#!/usr/bin/env python3
"""Create blind, object-level perception review packets from existing cases."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.case_audit import audit_case, find_case_files
from smc_desk.perception import perception_annotation_scaffold


def candidate_for_blind_review(audit: dict[str, Any]) -> bool:
    return bool(
        audit.get("source_csv_exists")
        and audit.get("source_csv_hash_matches") is True
        and audit.get("chart_exchange_matches_ohlcv") is True
        and audit.get("screenshot_count")
        and not audit.get("missing_screenshots")
    )


def write_review_packet(case: dict[str, Any], audit: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    case_id = str(case.get("case_id") or Path(audit["case_path"]).parent.name)
    case_token = hashlib.sha256(str(audit["case_path"]).encode("utf-8")).hexdigest()[:10]
    review_id = f"{case_id}__{case_token}"
    chart_evidence = case.get("chart_evidence") or {}
    screenshots = chart_evidence.get("screenshots") or {}
    labels_path = output_dir / f"{review_id}.perception_labels.json"
    review_path = output_dir / f"{review_id}.blind_review.md"
    label_payload = {
        "case_id": case_id,
        "case_path": audit["case_path"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "perception_annotations": perception_annotation_scaffold(),
    }
    labels_path.write_text(json.dumps(label_payload, indent=2), encoding="utf-8")
    lines = [
        f"# Blind SMC Perception Review - {case_id}",
        "",
        "Label the source chart before opening the engine report or overlay. Use the paired JSON file for object-level labels.",
        "",
        f"- Symbol: {case.get('symbol')}",
        f"- Decision time: {case.get('decision_time')}",
        f"- Label file: `{labels_path}`",
        "",
        "## Label Rules",
        "- Events (BOS, CHoCH, sweep, inducement): timestamp and price are required.",
        "- Zones (FVG, OB, supply, demand, equal highs/lows): price_low and price_high are required.",
        "- Use `internal`, `swing`, or `external` scope for BOS/CHoCH.",
        "- Set `label_status=adjudicated` only after two reviewers and an adjudicator agree.",
        "",
        "## Source Charts",
        "",
    ]
    for timeframe in ("1D", "4H", "1H", "15"):
        screenshot = screenshots.get(timeframe)
        if screenshot:
            lines.extend([f"### {timeframe}", f"![{case.get('symbol')} {timeframe}]({screenshot})", ""])
    review_path.write_text("\n".join(lines), encoding="utf-8")
    return {"labels": labels_path, "review": review_path, "review_id": Path(review_id)}


def prepare_review_queue(root: Path, output_dir: Path, limit: int | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for case_path in find_case_files(root):
        audit = audit_case(case_path)
        if not candidate_for_blind_review(audit):
            skipped.append({"case_path": str(case_path), "reason": ",".join(audit["warnings"])})
            continue
        case = json.loads(case_path.read_text(encoding="utf-8"))
        paths = write_review_packet(case, audit, output_dir)
        prepared.append(
            {
                "case_id": str(case.get("case_id")),
                "case_path": str(case_path),
                "review_id": str(paths["review_id"]),
                "labels": str(paths["labels"]),
                "review": str(paths["review"]),
            }
        )
        if limit is not None and len(prepared) >= limit:
            break
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "prepared": prepared,
        "skipped": skipped,
        "note": "Review the source chart before opening any machine report. Imported labels must be adjudicated before gold evaluation.",
    }
    (output_dir / "review_queue.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare blind perception-review packets from source-aligned cases.")
    parser.add_argument("--root", default="case_library")
    parser.add_argument("--output-dir", default="backtests/perception/review_queue")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    manifest = prepare_review_queue(Path(args.root), Path(args.output_dir), limit=args.limit)
    print(f"Prepared {len(manifest['prepared'])} blind review packets")
    print(f"Skipped {len(manifest['skipped'])} cases")
    print(f"Queue: {Path(args.output_dir) / 'review_queue.json'}")


if __name__ == "__main__":
    main()
