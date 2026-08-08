#!/usr/bin/env python3
"""Prepare, score, or aggregate blind SMC interrogation adjudications."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smc_desk.evaluation.interrogation_adjudication import (
    aggregate_blind_adjudication_packets,
    prepare_blind_adjudication_packet,
    score_completed_blind_adjudication,
)


def _write_or_print(payload: dict, output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        path = Path(output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(path)
    else:
        print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--case-manifest", required=True)
    prepare.add_argument("--reviewer-a", required=True)
    prepare.add_argument("--reviewer-b", required=True)
    prepare.add_argument("--system-submission", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--trust-registry", required=True)
    prepare.add_argument("--cohort-manifest", required=True)

    score = subparsers.add_parser("score")
    score.add_argument("--packet-manifest", required=True)
    score.add_argument("--output", default=None)
    score.add_argument("--strict", action="store_true")

    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("packet_manifests", nargs="+")
    aggregate.add_argument("--minimum-cases", type=int, default=30)
    aggregate.add_argument("--output", default=None)
    aggregate.add_argument("--strict", action="store_true")

    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_blind_adjudication_packet(
            case_manifest_path=args.case_manifest,
            reviewer_submission_paths=[args.reviewer_a, args.reviewer_b],
            system_submission_path=args.system_submission,
            output_dir=args.output_dir,
            trust_registry_path=args.trust_registry,
            cohort_manifest_path=args.cohort_manifest,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "score":
        result = score_completed_blind_adjudication(args.packet_manifest)
        _write_or_print(result, args.output)
        return 1 if args.strict and result["status"] != "PASS_100" else 0
    result = aggregate_blind_adjudication_packets(args.packet_manifests, minimum_cases=args.minimum_cases)
    _write_or_print(result, args.output)
    return 1 if args.strict and result["status"] != "CERTIFIED_100" else 0


if __name__ == "__main__":
    raise SystemExit(main())
