"""Immutable shadow decisions and selective-prediction outcome metrics."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smc_desk.data.hashing import canonical_json, object_sha256


class ShadowDecisionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["DECISION"] = "DECISION"
    case_id: str
    symbol: str
    decision_time: datetime
    horizon: str
    decision: Literal["ACCEPT", "REFUSE", "DATA_FAILED"]
    uncertainty_score: float | None = Field(default=None, ge=0.0, le=1.0)
    shadow_prediction: Literal["BULLISH", "BEARISH", "NEUTRAL"] | None = None
    refusal_reasons: list[str] = Field(default_factory=list)
    source_hashes: dict[str, str] = Field(default_factory=dict)

    @field_validator("decision_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("decision_time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_decision_contract(self) -> "ShadowDecisionEvent":
        if self.decision == "REFUSE" and not self.refusal_reasons:
            raise ValueError("REFUSE requires at least one reason")
        if self.decision != "DATA_FAILED" and self.uncertainty_score is None:
            raise ValueError("eligible decision requires uncertainty_score")
        return self


class OutcomeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["OUTCOME"] = "OUTCOME"
    case_id: str
    resolved_at: datetime
    state: Literal["RESOLVED", "UNRESOLVED", "DATA_FAILED"]
    shadow_prediction_correct: bool | None = None
    favorable_opportunity: bool | None = None
    outcome_return_bps: float | None = None
    outcome_definition: str
    source_hashes: dict[str, str] = Field(default_factory=dict)

    @field_validator("resolved_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("resolved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_resolution(self) -> "OutcomeEvent":
        if self.state == "RESOLVED" and self.favorable_opportunity is None:
            raise ValueError("resolved outcome requires favorable_opportunity")
        return self


def append_selective_ledger_event(
    path: str | Path,
    event: ShadowDecisionEvent | OutcomeEvent | Mapping[str, Any],
) -> dict[str, Any]:
    """Append one hash-chained event while refusing duplicate event ownership."""
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    model = _validate_event(event)
    payload = model.model_dump(mode="json")
    with ledger_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        existing = _decode_and_verify(handle.readlines())
        identity = (payload["event_type"], payload["case_id"])
        if any((item["event_type"], item["case_id"]) == identity for item in existing):
            raise ValueError(f"Duplicate selective ledger event: {identity[0]}:{identity[1]}")
        previous = existing[-1]["entry_sha256"] if existing else "0" * 64
        entry = {
            "schema": "selective_outcome_ledger_event_v1",
            **payload,
            "previous_entry_sha256": previous,
        }
        entry["entry_sha256"] = object_sha256(entry)
        handle.seek(0, 2)
        handle.write(canonical_json(entry) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return entry


def read_selective_ledger(path: str | Path) -> list[dict[str, Any]]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return []
    with ledger_path.open("r", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        events = _decode_and_verify(handle.readlines())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return events


def build_selective_outcome_report(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate abstention utility without tuning label definitions for P&L."""
    event_list = [dict(event) for event in events]
    decisions = {str(item["case_id"]): item for item in event_list if item.get("event_type") == "DECISION"}
    outcomes = {str(item["case_id"]): item for item in event_list if item.get("event_type") == "OUTCOME"}
    cases = [
        {"decision": decision, "outcome": outcomes.get(case_id)}
        for case_id, decision in sorted(decisions.items())
    ]
    total = len(cases)
    data_failed = sum(
        case["decision"].get("decision") == "DATA_FAILED"
        or (case["outcome"] or {}).get("state") == "DATA_FAILED"
        for case in cases
    )
    eligible = [case for case in cases if case["decision"].get("decision") != "DATA_FAILED"]
    accepted = [case for case in eligible if case["decision"].get("decision") == "ACCEPT"]
    refused = [case for case in eligible if case["decision"].get("decision") == "REFUSE"]
    resolved = [case for case in eligible if (case["outcome"] or {}).get("state") == "RESOLVED"]
    accepted_resolved = [case for case in accepted if (case["outcome"] or {}).get("state") == "RESOLVED"]
    refused_resolved = [case for case in refused if (case["outcome"] or {}).get("state") == "RESOLVED"]

    accepted_scored = [case for case in accepted_resolved if (case["outcome"] or {}).get("shadow_prediction_correct") is not None]
    selective_errors = sum(not bool(case["outcome"]["shadow_prediction_correct"]) for case in accepted_scored)
    refused_favorable = sum(bool(case["outcome"].get("favorable_opportunity")) for case in refused_resolved)
    all_favorable = sum(bool(case["outcome"].get("favorable_opportunity")) for case in resolved)
    reasons = Counter(
        reason
        for case in refused
        for reason in case["decision"].get("refusal_reasons", [])
    )
    curve = _risk_coverage_curve(resolved)
    report = {
        "schema": "selective_outcome_report_v1",
        "case_counts": {
            "total": total,
            "eligible": len(eligible),
            "accepted": len(accepted),
            "refused": len(refused),
            "resolved": len(resolved),
            "data_failed": data_failed,
        },
        "metrics": {
            "coverage": _ratio(len(accepted), len(eligible)),
            "selective_error": _ratio(selective_errors, len(accepted_scored)),
            "false_omission_rate": _ratio(refused_favorable, len(refused_resolved)),
            "missed_favorable_outcome_rate": _ratio(refused_favorable, all_favorable),
            "data_failure_rate": _ratio(data_failed, total),
            "area_under_risk_coverage_curve": _aurc(curve),
        },
        "risk_coverage_curve": curve,
        "refusal_reason_distribution": dict(sorted(reasons.items())),
        "unresolved_case_ids": sorted(
            case_id for case_id in decisions
            if case_id not in outcomes or outcomes[case_id].get("state") == "UNRESOLVED"
        ),
        "authority_contract": {
            "definition_threshold_tuning_from_profitability": False,
            "economic_replication_claimed": False,
            "forecast_calibration_claimed": False,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }
    report["report_sha256"] = object_sha256(report)
    return report


def _risk_coverage_curve(resolved_cases: list[dict[str, Any]]) -> list[dict[str, float | int]]:
    scored = [
        case for case in resolved_cases
        if case["decision"].get("uncertainty_score") is not None
        and case["decision"].get("shadow_prediction") is not None
        and case["outcome"].get("shadow_prediction_correct") is not None
    ]
    if not scored:
        return []
    ordered = sorted(scored, key=lambda case: (float(case["decision"]["uncertainty_score"]), case["decision"]["case_id"]))
    points: list[dict[str, float | int]] = []
    errors = 0
    for index, case in enumerate(ordered, start=1):
        errors += int(not bool(case["outcome"]["shadow_prediction_correct"]))
        points.append({
            "uncertainty_threshold": round(float(case["decision"]["uncertainty_score"]), 8),
            "accepted_cases": index,
            "coverage": round(index / len(ordered), 8),
            "selective_risk": round(errors / index, 8),
        })
    return points


def _aurc(curve: list[Mapping[str, Any]]) -> float | None:
    if not curve:
        return None
    area = 0.0
    previous_coverage = 0.0
    previous_risk = float(curve[0]["selective_risk"])
    for point in curve:
        coverage = float(point["coverage"])
        risk = float(point["selective_risk"])
        area += (coverage - previous_coverage) * (previous_risk + risk) / 2.0
        previous_coverage = coverage
        previous_risk = risk
    return round(area, 8)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 8)


def _validate_event(event: ShadowDecisionEvent | OutcomeEvent | Mapping[str, Any]) -> ShadowDecisionEvent | OutcomeEvent:
    if isinstance(event, (ShadowDecisionEvent, OutcomeEvent)):
        return event
    payload = {
        key: value for key, value in event.items()
        if key not in {"schema", "previous_entry_sha256", "entry_sha256"}
    }
    event_type = str(payload.get("event_type") or "")
    if event_type == "DECISION":
        return ShadowDecisionEvent.model_validate(payload)
    if event_type == "OUTCOME":
        return OutcomeEvent.model_validate(payload)
    raise ValueError(f"Unsupported selective ledger event type: {event_type or 'missing'}")


def _decode_and_verify(lines: Iterable[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous = "0" * 64
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        entry = json.loads(line)
        claimed = entry.pop("entry_sha256", None)
        if entry.get("previous_entry_sha256") != previous or claimed != object_sha256(entry):
            raise ValueError(f"Selective outcome ledger hash-chain failure at line {line_number}")
        entry["entry_sha256"] = claimed
        _validate_event(entry)
        events.append(entry)
        previous = claimed
    return events


__all__ = [
    "OutcomeEvent",
    "ShadowDecisionEvent",
    "append_selective_ledger_event",
    "build_selective_outcome_report",
    "read_selective_ledger",
]


# -- turning completed runs into measurable refusals --------------------------
#
# The ledger was built but never written to, so `missed_favorable_outcome_rate`
# had no data and a run of REVIEW_REQUIRED verdicts was indistinguishable from
# a broken system quietly saying nothing. A refusal only becomes falsifiable if
# the read it *would* have taken is recorded at decision time -- otherwise there
# is nothing to score the market against later.

REFUSAL_STATES = {"REVIEW_REQUIRED", "THESIS_ONLY", "WATCH_ONLY"}
ACCEPT_STATES = {"TRADE_PLAN_READY"}

_BIAS_TO_PREDICTION = {"bullish": "BULLISH", "bearish": "BEARISH"}


def _reconciliation_uncertainty(invariants: Mapping[str, Any]) -> float | None:
    """Fraction of controlling checks the stricter replay rejected.

    A measured quantity, not a confidence score: 0.0 means both engines agreed
    everywhere, 1.0 means they agreed nowhere. It is the only uncertainty the
    system can currently state without inventing one.
    """
    checks = invariants.get("checks")
    if not isinstance(checks, (list, tuple)) or not checks:
        return None
    failed = sum(1 for check in checks if isinstance(check, Mapping) and not check.get("passed"))
    return round(failed / len(checks), 6)


def build_shadow_decision_from_run(
    *,
    case_id: str,
    symbol: str,
    decision_time: datetime,
    horizon: str,
    official_state: str,
    hard_issue_codes: Iterable[str] = (),
    narrative_context: Mapping[str, Any] | None = None,
    invariants: Mapping[str, Any] | None = None,
    source_hashes: Mapping[str, str] | None = None,
    data_failed: bool = False,
) -> ShadowDecisionEvent:
    """Record what the system decided, and what it would have said if asked.

    ``shadow_prediction`` is carried on refusals deliberately. Without it a
    refusal can never be scored, and "the system was right to stay out" stays
    an assertion forever.
    """
    reasons = [str(code) for code in hard_issue_codes if str(code)]
    if data_failed:
        decision = "DATA_FAILED"
    elif str(official_state) in ACCEPT_STATES:
        decision = "ACCEPT"
    else:
        decision = "REFUSE"
        if not reasons:
            reasons = [f"official_state_{str(official_state).lower() or 'unknown'}"]

    narrative = narrative_context if isinstance(narrative_context, Mapping) else {}
    prediction: str | None = None
    if narrative.get("is_coherent") is True:
        prediction = _BIAS_TO_PREDICTION.get(str(narrative.get("context_bias") or "").lower(), "NEUTRAL")
    elif decision != "DATA_FAILED":
        prediction = "NEUTRAL"

    uncertainty = None
    if decision != "DATA_FAILED":
        uncertainty = _reconciliation_uncertainty(invariants or {})
        if uncertainty is None:
            # No reconciliation evidence at all is maximum uncertainty, not zero.
            uncertainty = 1.0

    return ShadowDecisionEvent(
        case_id=case_id,
        symbol=symbol,
        decision_time=decision_time,
        horizon=horizon,
        decision=decision,  # type: ignore[arg-type]
        uncertainty_score=uncertainty,
        shadow_prediction=prediction,  # type: ignore[arg-type]
        refusal_reasons=reasons if decision == "REFUSE" else [],
        source_hashes=dict(source_hashes or {}),
    )
