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
* **Structure** — precision and recall over BOS/CHoCH/sweep marks, matched on
  price within tolerance and on direction. Marking a real level the human did
  not is a false positive; missing one they did is a false negative.
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
import json
from pathlib import Path
from typing import Any

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


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tolerance(price: float | None, atr: float | None) -> float:
    if atr and atr > 0:
        return atr * PRICE_TOLERANCE_ATR
    if price:
        return abs(price) * PRICE_TOLERANCE_PCT
    return 1e-9


def _metric(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall and (precision + recall)
        else None
    )
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


def _score_structure(human: dict[str, Any], system: dict[str, Any], atr: float | None) -> dict[str, Any]:
    """Match human structure marks against system 'major' structure by price."""
    human_marks = [
        a for a in (human.get("annotations") or [])
        if isinstance(a, dict) and _f(a.get("price")) is not None and a.get("primitive")
    ]
    confident = [a for a in human_marks if not a.get("is_ambiguous")]
    ambiguous = [a for a in human_marks if a.get("is_ambiguous")]

    system_prices: list[tuple[str, float]] = []
    for timeframe, entry in (system.get("significant_structure") or {}).items():
        for object_id in entry or []:
            price = _price_from_object_id(object_id, system)
            if price is not None:
                system_prices.append((f"{timeframe}:{object_id}", price))

    unmatched_system = list(system_prices)
    tp = 0
    misses: list[dict[str, Any]] = []
    for mark in confident:
        price = _f(mark.get("price"))
        tol = _tolerance(price, atr)
        hit = None
        for candidate in unmatched_system:
            if abs(candidate[1] - price) <= tol:
                hit = candidate
                break
        if hit:
            tp += 1
            unmatched_system.remove(hit)
        else:
            misses.append({"primitive": mark.get("primitive"), "price": price,
                           "notes": mark.get("notes", "")})

    return {
        "metrics": _metric(tp, len(unmatched_system), len(misses)),
        "human_marks": len(confident),
        "human_ambiguous": len(ambiguous),
        "system_marks": len(system_prices),
        "missed_by_system": misses,
        "extra_from_system": [name for name, _ in unmatched_system],
    }


def _price_from_object_id(object_id: str, system: dict[str, Any]) -> float | None:
    """Recover a price for a system object id, when the answer recorded one."""
    prices = system.get("object_prices")
    if isinstance(prices, dict):
        return _f(prices.get(object_id))
    return None


def _score_draw(human: dict[str, Any], system: dict[str, Any], atr: float | None) -> dict[str, Any]:
    h = ((human.get("liquidity") or {}).get("expected_draw") or {})
    s = system.get("draw") or {}
    h_price, s_price = _f(h.get("price")), _f(s.get("target_price"))
    if h_price is None:
        return {"scored": False, "reason": "reviewer named no expected draw"}
    tol = _tolerance(h_price, atr)
    return {
        "scored": True,
        "human_price": h_price, "system_price": s_price,
        "system_kind": s.get("target_kind"),
        "agree": s_price is not None and abs(s_price - h_price) <= tol,
        "direction_agree": str(h.get("direction") or "").lower() == str(s.get("direction") or "").lower(),
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


def score_case(case_dir: Path, markup_filename: str) -> dict[str, Any] | None:
    markup_path = case_dir / markup_filename
    sealed_path = case_dir / "_sealed_system_answer.json"
    if not markup_path.exists() or not sealed_path.exists():
        return None
    human = json.loads(markup_path.read_text())
    system = json.loads(sealed_path.read_text())
    if not str(human.get("htf_bias") or "").strip():
        return {"case_id": case_dir.name, "status": "INCOMPLETE",
                "reason": "htf_bias not filled in"}

    atr = _f((system.get("atr") or {}).get(human.get("context_timeframe"))) if isinstance(
        system.get("atr"), dict
    ) else None

    return {
        "case_id": case_dir.name,
        "status": "SCORED",
        "regime": (json.loads((case_dir / "metadata.json").read_text()) or {}).get("regime_type")
        if (case_dir / "metadata.json").exists() else None,
        "bias": _score_bias(human, system),
        "dealing_range": _score_range(human, system, atr),
        "structure": _score_structure(human, system, atr),
        "draw": _score_draw(human, system, atr),
        "poi": _score_poi(human, system),
        "decision": {
            "human": human.get("would_you_trade_this"),
            "system_state": (system.get("market_state") or {}).get("state"),
        },
        "reviewer_notes": human.get("reviewer_notes", ""),
    }


def main() -> None:
    args = parse_args()
    cohort = Path(args.cohort).expanduser().resolve()
    results: list[dict[str, Any]] = []
    for case_dir in sorted(p for p in cohort.iterdir() if p.is_dir()):
        scored = score_case(case_dir, args.markup_filename)
        if scored:
            results.append(scored)

    scored_cases = [r for r in results if r.get("status") == "SCORED"]
    bias_agree = sum(1 for r in scored_cases if r["bias"]["agree"])
    range_high = sum(1 for r in scored_cases if r["dealing_range"].get("high_agree"))
    range_low = sum(1 for r in scored_cases if r["dealing_range"].get("low_agree"))
    draw_agree = sum(1 for r in scored_cases if r["draw"].get("agree"))
    poi_overlap = sum(1 for r in scored_cases if r["poi"].get("overlap"))

    tp = sum(r["structure"]["metrics"]["true_positives"] for r in scored_cases)
    fp = sum(r["structure"]["metrics"]["false_positives"] for r in scored_cases)
    fn = sum(r["structure"]["metrics"]["false_negatives"] for r in scored_cases)

    report = {
        "schema": "markup_score_report_v1",
        "cohort": str(cohort),
        "cases_found": len(results),
        "cases_scored": len(scored_cases),
        "cases_incomplete": [r["case_id"] for r in results if r.get("status") == "INCOMPLETE"],
        "summary": {
            "bias_agreement": f"{bias_agree}/{len(scored_cases)}" if scored_cases else None,
            "range_high_agreement": f"{range_high}/{len(scored_cases)}" if scored_cases else None,
            "range_low_agreement": f"{range_low}/{len(scored_cases)}" if scored_cases else None,
            "draw_agreement": f"{draw_agree}/{len(scored_cases)}" if scored_cases else None,
            "poi_overlap": f"{poi_overlap}/{len(scored_cases)}" if scored_cases else None,
            "structure": _metric(tp, fp, fn),
        },
        "honest_limits": [
            "One reviewer is not adjudicated truth; it is one expert opinion.",
            "Agreement is not profitability and must never be reported as edge.",
            "Cases marked after seeing the system's answer are contaminated and invalid.",
        ],
        "cases": results,
    }

    out = Path(args.output) if args.output else cohort / "score_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))

    print(f"cases scored : {len(scored_cases)}/{len(results)}")
    if scored_cases:
        print(f"bias agree   : {bias_agree}/{len(scored_cases)}")
        print(f"range high   : {range_high}/{len(scored_cases)}   low: {range_low}/{len(scored_cases)}")
        print(f"draw agree   : {draw_agree}/{len(scored_cases)}")
        print(f"POI overlap  : {poi_overlap}/{len(scored_cases)}")
        print(f"structure    : {report['summary']['structure']}")
    else:
        print("No completed markup found. Fill markup_template.json -> markup.json per case.")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
