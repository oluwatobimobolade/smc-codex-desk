"""Score the system against a human markup, object by object.

This produces the error signal the project has never had. Until a human has
marked charts and the system has been scored against them, every perception
threshold — swing significance, break displacement floors, liquidity
importance weights, label separation — is a reasoned default rather than a
measurement.

What is scored, in the order a trader reads a chart:

* **Bias** — did the system reach the same directional read, from the same
  context timeframe?
* **Dealing range** — do the high and low agree within tolerance?
* **Structure** — precision and recall over significant BOS/CHoCH/swing marks,
  matched on price, direction, scope, and timeframe. Sweeps stay in the
  liquidity review until an expert-approved sweep-significance rule exists.
* **Liquidity draw** — did the system name the same target?
* **POI** — does the primary zone overlap the human's?
* **Decision** — trade / watch / no-trade agreement.

Deliberate choices:

* Tolerance is expressed in **ATR**, not ticks or percent, because "the same
  level" means something different on a quiet 15m chart and a volatile 4H one.
* A miss and a false positive are reported separately. A system that marks
  everything scores high recall and is useless; the harm is in the precision.
* Ambiguous human marks are counted separately and never punish the system.

Usage::

    python tools/score_markup_cohort.py --cohort review_queues/markup_cohort_<date>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_desk.evaluation.cohort_integrity import (
    STRUCTURE_PRIMITIVES,
    VALID_DECISIONS,
    assert_cohort_scoreable as _assert_cohort_scoreable,
    float_or_none as _f,
    sha256_file as _sha256_file,
    validate_completed_markup as _validate_completed_markup,
)

# Two marks are "the same level" within this multiple of the timeframe's ATR.
PRICE_TOLERANCE_ATR = 0.5
# Fallback when no ATR is recorded for a case.
PRICE_TOLERANCE_PCT = 0.004


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--markup-filename", default="markup.json",
                        help="Completed reviewer file inside each case directory.")
    parser.add_argument("--output", default="", help="Where to write the report.")
    return parser.parse_args()


def _tolerance(price: float | None, atr: float | None) -> float:
    if atr and atr > 0:
        return atr * PRICE_TOLERANCE_ATR
    if price:
        return abs(price) * PRICE_TOLERANCE_PCT
    return 1e-9


def _metric(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def _score_bias(human: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    h = str(human.get("htf_bias") or "").strip().lower()
    s = str(system.get("htf_bias") or "").strip().lower()
    return {
        "scored": bool(h),
        "human": h or None, "system": s or None,
        "agree": bool(h and s and h == s),
        "human_timeframe": human.get("context_timeframe") or None,
        "system_timeframe": system.get("context_timeframe") or None,
        "timeframe_agree": bool(
            str(human.get("context_timeframe") or "").lower()
            == str(system.get("context_timeframe") or "").lower()
            and human.get("context_timeframe")
        ),
    }


def _score_range(human: dict[str, Any], system: dict[str, Any], atr: float | None) -> dict[str, Any]:
    h = human.get("dealing_range") or {}
    s = system.get("dealing_range") or {}
    h_high, h_low = _f(h.get("high")), _f(h.get("low"))
    s_high, s_low = _f(s.get("high")), _f(s.get("low"))
    if h_high is None or h_low is None:
        return {"scored": False, "reason": "reviewer left the dealing range blank"}
    tol_high = _tolerance(h_high, atr)
    tol_low = _tolerance(h_low, atr)
    return {
        "scored": True,
        "human": {"high": h_high, "low": h_low},
        "system": {"high": s_high, "low": s_low},
        "high_agree": s_high is not None and abs(s_high - h_high) <= tol_high,
        "low_agree": s_low is not None and abs(s_low - h_low) <= tol_low,
        "tolerance": round(max(tol_high, tol_low), 4),
    }


def _atr_for_timeframe(atr: Any, timeframe: Any) -> float | None:
    if isinstance(atr, dict):
        return _f(atr.get(str(timeframe or "").lower()))
    return _f(atr)


def _score_structure(human: dict[str, Any], system: dict[str, Any], atr: Any) -> dict[str, Any]:
    """Maximum one-to-one matching with each mark's own timeframe ATR."""
    human_marks = [
        a for a in (human.get("annotations") or [])
        if (
            isinstance(a, dict)
            and _f(a.get("price")) is not None
            and str(a.get("primitive") or "").strip().lower() in STRUCTURE_PRIMITIVES
        )
    ]
    deferred_sweeps = [
        a for a in (human.get("annotations") or [])
        if isinstance(a, dict) and str(a.get("primitive") or "").strip().lower() == "sweep"
    ]
    confident = [a for a in human_marks if not a.get("is_ambiguous")]
    ambiguous = [a for a in human_marks if a.get("is_ambiguous")]

    metadata = system.get("object_metadata")
    object_metadata = metadata if isinstance(metadata, dict) else {}
    system_marks: list[dict[str, Any]] = []
    for timeframe, entry in (system.get("significant_structure") or {}).items():
        for object_id in entry or []:
            price = _price_from_object_id(object_id, system, timeframe=timeframe)
            if price is not None:
                object_key = f"{timeframe}:{object_id}"
                item_metadata = object_metadata.get(object_key) or object_metadata.get(object_id) or {}
                primitive = str(item_metadata.get("primitive") or "").strip().lower()
                if primitive and primitive not in STRUCTURE_PRIMITIVES:
                    continue
                system_marks.append({
                    "name": f"{timeframe}:{object_id}",
                    "object_id": object_id,
                    "timeframe": timeframe,
                    "price": price,
                    "metadata": item_metadata,
                })

    edges: dict[int, list[int]] = {}
    tolerances: dict[int, float] = {}
    for human_index, mark in enumerate(confident):
        price = _f(mark.get("price"))
        timeframe = str(mark.get("timeframe") or "").lower()
        tolerance = _tolerance(price, _atr_for_timeframe(atr, timeframe))
        tolerances[human_index] = tolerance
        compatible = [
            candidate_index
            for candidate_index, candidate in enumerate(system_marks)
            if abs(candidate["price"] - price) <= tolerance
            and _structure_compatible(mark, candidate)
        ]
        edges[human_index] = sorted(
            compatible,
            key=lambda candidate_index: abs(system_marks[candidate_index]["price"] - price),
        )

    candidate_to_human: dict[int, int] = {}

    def assign(human_index: int, seen: set[int]) -> bool:
        for candidate_index in edges.get(human_index, []):
            if candidate_index in seen:
                continue
            seen.add(candidate_index)
            previous = candidate_to_human.get(candidate_index)
            if previous is None or assign(previous, seen):
                candidate_to_human[candidate_index] = human_index
                return True
        return False

    for human_index in range(len(confident)):
        assign(human_index, set())

    matched_human = set(candidate_to_human.values())
    matched_system = set(candidate_to_human)
    misses = [
        {
            "primitive": mark.get("primitive"),
            "direction": mark.get("direction"),
            "timeframe": mark.get("timeframe"),
            "price": _f(mark.get("price")),
            "tolerance": round(tolerances[index], 4),
            "notes": mark.get("notes", ""),
        }
        for index, mark in enumerate(confident)
        if index not in matched_human
    ]
    unmatched_system = [
        candidate for index, candidate in enumerate(system_marks) if index not in matched_system
    ]
    tp = len(matched_human)

    return {
        "metrics": _metric(tp, len(unmatched_system), len(misses)),
        "human_marks": len(confident),
        "human_ambiguous": len(ambiguous),
        "human_sweeps_deferred_to_liquidity_review": len(deferred_sweeps),
        "system_marks": len(system_marks),
        "missed_by_system": misses,
        "extra_from_system": [candidate["name"] for candidate in unmatched_system],
    }


def _structure_compatible(human: dict[str, Any], system_mark: dict[str, Any]) -> bool:
    """Require semantic agreement when the sealed answer recorded metadata."""
    metadata = system_mark.get("metadata")
    if not isinstance(metadata, dict) or not metadata:
        return True

    human_tf = str(human.get("timeframe") or "").strip().lower()
    system_tf = str(metadata.get("timeframe") or system_mark.get("timeframe") or "").lower()
    if human_tf and system_tf and human_tf != system_tf:
        return False

    human_direction = str(human.get("direction") or "").strip().lower()
    system_direction = str(metadata.get("direction") or "").strip().lower()
    if human_direction and system_direction and human_direction != system_direction:
        return False

    human_primitive = str(human.get("primitive") or "").strip().lower()
    system_primitive = str(metadata.get("primitive") or "").strip().lower()
    if human_primitive and system_primitive and human_primitive != system_primitive:
        return False
    human_scope = str(human.get("scope") or "").strip().lower()
    system_scope = str(metadata.get("scope") or "").strip().lower()
    if human_scope and system_scope and human_scope != system_scope:
        return False
    return True


def _price_from_object_id(
    object_id: str, system: dict[str, Any], *, timeframe: str = ""
) -> float | None:
    """Recover a price for a system object id, when the answer recorded one."""
    prices = system.get("object_prices")
    if isinstance(prices, dict):
        return _f(prices.get(f"{timeframe}:{object_id}", prices.get(object_id)))
    return None


def _score_draw(human: dict[str, Any], system: dict[str, Any], atr: float | None) -> dict[str, Any]:
    h = ((human.get("liquidity") or {}).get("expected_draw") or {})
    s = system.get("draw") or {}
    h_price, s_price = _f(h.get("price")), _f(s.get("target_price"))
    if h_price is None:
        return {"scored": False, "reason": "reviewer named no expected draw"}
    tol = _tolerance(h_price, atr)
    direction_agree = (
        bool(str(h.get("direction") or "").strip())
        and str(h.get("direction") or "").lower() == str(s.get("direction") or "").lower()
    )
    return {
        "scored": True,
        "human_price": h_price, "system_price": s_price,
        "system_kind": s.get("target_kind"),
        "agree": s_price is not None and abs(s_price - h_price) <= tol and direction_agree,
        "direction_agree": direction_agree,
        "tolerance": round(tol, 4),
    }


def _score_poi(human: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    h = human.get("primary_poi") or {}
    h_low, h_high = _f(h.get("price_low")), _f(h.get("price_high"))
    poi = (system.get("market_state") or {}).get("poi") or {}
    s_low, s_high = _f(poi.get("primary_low")), _f(poi.get("primary_high"))
    if h_low is None or h_high is None:
        return {"scored": False, "reason": "reviewer named no primary POI"}
    if s_low is None or s_high is None:
        return {"scored": True, "overlap": False, "system_had_poi": False,
                "human": [h_low, h_high], "system": None}
    lo = max(min(h_low, h_high), min(s_low, s_high))
    hi = min(max(h_low, h_high), max(s_low, s_high))
    return {
        "scored": True, "system_had_poi": True,
        "human": [h_low, h_high], "system": [s_low, s_high],
        "overlap": hi >= lo,
        "overlap_fraction": round(
            max(0.0, hi - lo) / max(abs(h_high - h_low), 1e-9), 4
        ),
    }


def _score_decision(human: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    human_decision = str(human.get("would_you_trade_this") or "").strip().lower()
    decision = system.get("decision") if isinstance(system.get("decision"), dict) else {}
    system_decision = str(decision.get("classification") or "").strip().lower()
    return {
        "scored": human_decision in VALID_DECISIONS and system_decision in VALID_DECISIONS,
        "human": human_decision or None,
        "system": system_decision or None,
        "agree": bool(
            human_decision in VALID_DECISIONS
            and system_decision in VALID_DECISIONS
            and human_decision == system_decision
        ),
        "system_state": (system.get("market_state") or {}).get("state"),
        "authority": decision.get("authority"),
    }


def _score_case_with_manifest(
    case_dir: Path,
    markup_filename: str,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    case_dir = case_dir.expanduser().resolve()
    case_row = next(
        (
            row for row in (manifest.get("cases") or [])
            if isinstance(row, dict) and row.get("case_id") == case_dir.name
        ),
        None,
    )
    if not case_row or case_row.get("status") != "READY":
        raise ValueError(f"Case is not READY in the sealed cohort manifest: {case_dir.name}")
    markup_path = case_dir / markup_filename
    sealed_path = case_dir / "_sealed_system_answer.json"
    if not markup_path.exists() or not sealed_path.exists():
        return None
    human = json.loads(markup_path.read_text(encoding="utf-8"))
    system = json.loads(sealed_path.read_text(encoding="utf-8"))
    metadata_path = case_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    completion_issues = _validate_completed_markup(
        human,
        case_id=case_dir.name,
        reviewer_id=str(manifest.get("reviewer_id") or ""),
        metadata=metadata,
    )
    if completion_issues:
        return {
            "case_id": case_dir.name,
            "status": "INCOMPLETE",
            "reason": "; ".join(completion_issues),
            "completion_issues": completion_issues,
        }

    atr_by_timeframe = system.get("atr") if isinstance(system.get("atr"), dict) else {}
    context_timeframe = str(human.get("context_timeframe") or "").lower()
    range_timeframe = str((human.get("dealing_range") or {}).get("timeframe") or context_timeframe).lower()
    draw_timeframe = str(
        ((human.get("liquidity") or {}).get("expected_draw") or {}).get("timeframe")
        or context_timeframe
    ).lower()

    return {
        "case_id": case_dir.name,
        "case_seal_sha256": case_row.get("case_seal_sha256"),
        "markup_sha256": _sha256_file(markup_path),
        "status": "SCORED",
        "regime": metadata.get("regime_type"),
        "bias": _score_bias(human, system),
        "dealing_range": _score_range(
            human, system, _atr_for_timeframe(atr_by_timeframe, range_timeframe)
        ),
        "structure": _score_structure(human, system, atr_by_timeframe),
        "draw": _score_draw(
            human, system, _atr_for_timeframe(atr_by_timeframe, draw_timeframe)
        ),
        "poi": _score_poi(human, system),
        "decision": _score_decision(human, system),
        "reviewer_notes": human.get("reviewer_notes", ""),
    }


def score_case(case_dir: Path, markup_filename: str) -> dict[str, Any] | None:
    """Public fail-closed case scorer; cohort integrity is always verified first."""
    case_dir = case_dir.expanduser().resolve()
    manifest = _assert_cohort_scoreable(case_dir.parent)
    return _score_case_with_manifest(case_dir, markup_filename, manifest)


def _agreement_summary(
    scored_cases: list[dict[str, Any]], dimension: str, field: str
) -> dict[str, Any]:
    eligible = [
        result for result in scored_cases
        if isinstance(result.get(dimension), dict) and result[dimension].get("scored") is True
    ]
    agreed = sum(1 for result in eligible if result[dimension].get(field) is True)
    return {
        "agreed": agreed,
        "scored": len(eligible),
        "rate": round(agreed / len(eligible), 4) if eligible else None,
    }


def _build_report(
    cohort: Path,
    results: list[dict[str, Any]],
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scored_cases = [r for r in results if r.get("status") == "SCORED"]
    tp = sum(r["structure"]["metrics"]["true_positives"] for r in scored_cases)
    fp = sum(r["structure"]["metrics"]["false_positives"] for r in scored_cases)
    fn = sum(r["structure"]["metrics"]["false_negatives"] for r in scored_cases)
    expected_cases = int((manifest or {}).get("case_count") or len(results))

    report = {
        "schema": "markup_score_report_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": str(cohort),
        "cohort_content_sha256": (manifest or {}).get("cohort_content_sha256"),
        "report_status": (
            "COMPLETE" if expected_cases > 0 and len(scored_cases) == expected_cases
            else "PARTIAL_INCOMPLETE"
        ),
        "cases_found": len(results),
        "cases_scored": len(scored_cases),
        "cases_incomplete": [r["case_id"] for r in results if r.get("status") == "INCOMPLETE"],
        "summary": {
            "bias_agreement": _agreement_summary(scored_cases, "bias", "agree"),
            "bias_timeframe_agreement": _agreement_summary(
                scored_cases, "bias", "timeframe_agree"
            ),
            "range_high_agreement": _agreement_summary(
                scored_cases, "dealing_range", "high_agree"
            ),
            "range_low_agreement": _agreement_summary(
                scored_cases, "dealing_range", "low_agree"
            ),
            "draw_agreement": _agreement_summary(scored_cases, "draw", "agree"),
            "poi_overlap": _agreement_summary(scored_cases, "poi", "overlap"),
            "decision_agreement": _agreement_summary(scored_cases, "decision", "agree"),
            "structure": _metric(tp, fp, fn),
        },
        "honest_limits": [
            "One reviewer is not adjudicated truth; it is one expert opinion.",
            "Agreement is not profitability and must never be reported as edge.",
            "Cases marked after seeing the system's answer are contaminated and invalid.",
            "Sweep-event precision is not reported until an expert-approved significance rule exists.",
        ],
        "cases": results,
    }
    canonical = (
        json.dumps(report, sort_keys=True, default=str, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    report["report_content_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def main() -> None:
    args = parse_args()
    cohort = Path(args.cohort).expanduser().resolve()
    try:
        manifest = _assert_cohort_scoreable(cohort)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    results: list[dict[str, Any]] = []
    for case_row in manifest.get("cases") or []:
        case_dir = cohort / str(case_row["case_id"])
        scored = _score_case_with_manifest(
            case_dir,
            args.markup_filename,
            manifest,
        )
        if scored:
            results.append(scored)
        else:
            results.append({
                "case_id": case_dir.name,
                "status": "INCOMPLETE",
                "reason": f"{args.markup_filename} is missing",
            })

    report = _build_report(cohort, results, manifest)
    scored_cases = [result for result in results if result.get("status") == "SCORED"]

    default_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = (
        Path(args.output)
        if args.output
        else cohort / "score_reports" / f"score_report_{default_stamp}.json"
    )
    out = out.expanduser().resolve()
    if out.exists():
        raise SystemExit(f"Refusing to overwrite an existing score report: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=out.parent, prefix=f".{out.name}.", delete=False
    ) as handle:
        handle.write(json.dumps(report, indent=2, default=str) + "\n")
        temporary = Path(handle.name)
    try:
        temporary.rename(out)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    print(f"cases scored : {len(scored_cases)}/{len(results)}")
    if scored_cases:
        print(f"bias agree   : {report['summary']['bias_agreement']}")
        print(f"range high   : {report['summary']['range_high_agreement']}")
        print(f"range low    : {report['summary']['range_low_agreement']}")
        print(f"draw agree   : {report['summary']['draw_agreement']}")
        print(f"POI overlap  : {report['summary']['poi_overlap']}")
        print(f"decision     : {report['summary']['decision_agreement']}")
        print(f"structure    : {report['summary']['structure']}")
    else:
        print("No completed markup found. Fill markup_template.json -> markup.json per case.")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
