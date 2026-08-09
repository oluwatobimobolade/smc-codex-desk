"""Turn an analyst's blind case picks into a sealed, scoreable definition set.

This is the only supported route to `selection_status: ANALYST_REVIEWED`. The
previous set reached the evaluation pipeline as sequential date-block
placeholders described as "balanced across four regimes", a claim nobody had
verified against a chart. `definition_set_status_v2` exists to make that
impossible, and this tool is what satisfies it honestly.

It refuses to invent the analyst's judgement. Specifically it will not run
without an explicit `--analyst-id`, a written rationale, and a per-case regime
call supplied by the person who looked at the charts. Those three fields are
the whole point: they record *who* decided, *why* these cases, and *what they
saw* — none of which a program can supply on their behalf.

Selections file (JSON), produced by hand after reviewing the survey::

    {
      "rationale": "Chose 13 cases spanning June: four clean trends, three
                    ranges, three transitions, three genuinely ambiguous.
                    Skipped the low-volume weekend windows.",
      "cases": [
        {"candidate_id": "cand_03", "case_id": "trend_01", "regime": "trend",
         "note": "clean HTF advance, shallow pullbacks"},
        {"candidate_id": "cand_09", "case_id": "ambiguous_01", "regime": "ambiguous",
         "note": "I could argue either direction here"}
      ]
    }

Usage::

    python tools/seal_definition_set.py \\
        --survey review_queues/candidate_survey_<date> \\
        --selections my_picks.json \\
        --analyst-id founder \\
        --output data/gold_sets/development_set_<date>
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_desk.evaluation.cohort_integrity import (
    case_ids_sha256,
    definition_case_set_sha256,
    reviewed_definition_issues,
)

MIN_CASES = 8
RECOMMENDED_MIN = 12
RECOMMENDED_MAX = 15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey", required=True, help="Folder produced by survey_candidate_cases.py")
    parser.add_argument("--selections", required=True, help="Your picks, as JSON.")
    parser.add_argument("--analyst-id", required=True, help="Who made this selection.")
    parser.add_argument("--output", required=True, help="New definition-set directory.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument(
        "--allow-small", action="store_true",
        help=f"Permit fewer than {RECOMMENDED_MIN} cases (minimum {MIN_CASES}).",
    )
    return parser.parse_args()


def _fail(message: str) -> None:
    raise SystemExit(f"Refusing to seal: {message}")


def main() -> None:
    args = parse_args()
    survey_root = Path(args.survey).expanduser().resolve()
    manifest_path = survey_root / "survey_manifest.json"
    if not manifest_path.exists():
        _fail(f"no survey_manifest.json in {survey_root}")
    survey = json.loads(manifest_path.read_text())
    by_candidate = {
        row["candidate_id"]: row
        for row in survey.get("candidates", [])
        if row.get("status") == "RENDERED"
    }

    selections = json.loads(Path(args.selections).expanduser().resolve().read_text())
    rationale = selections.get("rationale")
    if not (isinstance(rationale, str) and rationale.strip()) and not (
        isinstance(rationale, list) and any(str(x).strip() for x in rationale)
    ):
        _fail("selections file has no rationale. Why these cases, in your words?")

    cases = selections.get("cases")
    if not isinstance(cases, list) or not cases:
        _fail("selections file lists no cases")
    if len(cases) < MIN_CASES and not args.allow_small:
        _fail(
            f"only {len(cases)} cases selected; {RECOMMENDED_MIN}-{RECOMMENDED_MAX} is the "
            f"working range and {MIN_CASES} the floor. Pass --allow-small to override."
        )
    if len(cases) > RECOMMENDED_MAX:
        print(f"note: {len(cases)} cases selected; {RECOMMENDED_MAX} is the suggested ceiling "
              "for a single markup pass.")

    seen_case_ids: set[str] = set()
    resolved: list[dict[str, Any]] = []
    for entry in cases:
        if not isinstance(entry, dict):
            _fail(f"case entry is not an object: {entry!r}")
        candidate_id = str(entry.get("candidate_id") or "").strip()
        case_id = str(entry.get("case_id") or "").strip()
        regime = str(entry.get("regime") or "").strip()
        if candidate_id not in by_candidate:
            _fail(f"{candidate_id!r} is not a rendered candidate in this survey")
        if not case_id:
            _fail(f"{candidate_id} has no case_id")
        if case_id in seen_case_ids:
            _fail(f"duplicate case_id {case_id!r}")
        if not regime:
            _fail(
                f"{case_id} has no regime. Your regime call is required -- the old set's "
                "labels were date-block placeholders and that is what this replaces."
            )
        seen_case_ids.add(case_id)
        resolved.append({
            "case_id": case_id,
            "candidate_id": candidate_id,
            "regime": regime,
            "note": str(entry.get("note") or "").strip(),
            "decision_time": by_candidate[candidate_id]["decision_time"],
        })

    out_root = Path(args.output).expanduser().resolve()
    if out_root.exists() and any(out_root.iterdir()):
        _fail(f"output already exists and is not empty: {out_root}")
    out_root.mkdir(parents=True, exist_ok=True)

    for case in resolved:
        case_dir = out_root / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "metadata.json").write_text(json.dumps({
            "instrument": args.symbol,
            "timeframe": args.timeframe,
            "decision_time": case["decision_time"],
            "regime_type": case["regime"],
            "analyst_note": case["note"],
            "selected_from": {
                "survey": str(survey_root),
                "candidate_id": case["candidate_id"],
            },
        }, indent=2))

    case_ids = sorted(case["case_id"] for case in resolved)
    status = {
        "schema": "definition_set_status_v2",
        "selection_status": "ANALYST_REVIEWED",
        "analyst_id": args.analyst_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "selection_rationale": rationale,
        "created_by": "tools/seal_definition_set.py",
        "selected_from_survey": str(survey_root),
        "blind_selection": (
            "Cases were chosen from clean charts carrying no system output, "
            "detector objects, or pre-assigned regime labels."
        ),
        "scoreable": True,
        "case_count": len(case_ids),
        "case_ids_sha256": case_ids_sha256(case_ids),
        "case_set_sha256": definition_case_set_sha256(out_root, case_ids),
    }

    issues = reviewed_definition_issues(status, case_ids, status["case_set_sha256"])
    if issues:
        _fail("the sealed status failed its own contract: " + "; ".join(issues))

    (out_root / "definition_set_status.json").write_text(json.dumps(status, indent=2))

    regimes: dict[str, int] = {}
    for case in resolved:
        regimes[case["regime"]] = regimes.get(case["regime"], 0) + 1

    print(f"sealed {len(case_ids)} analyst-reviewed cases in {out_root}")
    print(f"analyst    : {args.analyst_id}")
    print(f"regimes    : {regimes}   (your calls, not placeholders)")
    print("\nNext:")
    print(f"  python tools/build_markup_cohort.py --gold-set {out_root} \\")
    print(f"      --source <ohlcv csv> --output review_queues/<cohort_name>")


if __name__ == "__main__":
    main()
