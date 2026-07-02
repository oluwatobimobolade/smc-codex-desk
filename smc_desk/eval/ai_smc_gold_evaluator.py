"""Compare AI SMC output to human-adjudicated gold labels."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smc_desk.eval.gold_set_loader import GoldChartCase


def compare_ai_output_to_human_labels(
    *,
    official_decision: Mapping[str, Any],
    gold_case: GoldChartCase,
    price_tolerance_bps: float = 10.0,
) -> dict[str, Any]:
    checks = {
        "state": official_decision.get("official_state") == gold_case.expected_state,
        "direction": official_decision.get("direction") == gold_case.expected_direction,
        "grade": _grade_matches(official_decision, gold_case),
        "poi": _zone_matches(official_decision.get("active_poi") or {}, gold_case.expected_poi, price_tolerance_bps),
        "invalidation": _price_matches(
            ((official_decision.get("invalidation") or {}).get("invalidation_price")),
            (gold_case.expected_invalidation or {}).get("price") if gold_case.expected_invalidation else None,
            price_tolerance_bps,
        ),
        "target": _target_matches(official_decision.get("target_plan") or {}, gold_case.expected_target, price_tolerance_bps),
    }
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    return {
        "schema": "ai_smc_gold_evaluation_v1",
        "case_id": gold_case.case_id,
        "symbol": gold_case.symbol,
        "checks": checks,
        "passed": passed,
        "total": total,
        "score": passed / total if total else 0.0,
        "status": "PASS" if passed == total else "MISMATCH",
    }


def _grade_matches(decision: Mapping[str, Any], case: GoldChartCase) -> bool:
    if case.expected_setup_grade is None:
        return True
    return str(decision.get("setup_grade")) == str(case.expected_setup_grade)


def _zone_matches(actual: Mapping[str, Any], expected: Mapping[str, Any] | None, tolerance_bps: float) -> bool:
    if expected is None:
        return True
    return _price_matches(actual.get("price_low"), expected.get("price_low"), tolerance_bps) and _price_matches(
        actual.get("price_high"), expected.get("price_high"), tolerance_bps
    )


def _target_matches(actual: Mapping[str, Any], expected: Mapping[str, Any] | None, tolerance_bps: float) -> bool:
    if expected is None:
        return True
    targets = actual.get("targets") or []
    expected_price = expected.get("price")
    return any(_price_matches(item.get("price"), expected_price, tolerance_bps) for item in targets if isinstance(item, Mapping))


def _price_matches(actual: Any, expected: Any, tolerance_bps: float) -> bool:
    if expected is None:
        return True
    try:
        actual_f = float(actual)
        expected_f = float(expected)
    except (TypeError, ValueError):
        return False
    tolerance = max(abs(expected_f) * tolerance_bps / 10000.0, 1e-9)
    return abs(actual_f - expected_f) <= tolerance
