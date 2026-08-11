"""Machine-readable final-exam contract for an external AI reasoning seat."""
from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


EXAM_STATIONS: tuple[dict[str, Any], ...] = (
    {"station_id": "S01_TIME_HONESTY", "title": "time_honesty", "critical": True},
    {"station_id": "S02_GROUNDING", "title": "grounding", "critical": True},
    {"station_id": "S03_SWEEP_ROLE", "title": "sweep_role", "critical": True},
    {"station_id": "S04_BREAK_GRAMMAR", "title": "break_grammar", "critical": True},
    {"station_id": "S05_PROTECTED_POINT", "title": "protected_point", "critical": True},
    {"station_id": "S06_CONTAINMENT", "title": "containment", "critical": True},
    {"station_id": "S07_COUNTER_STORY", "title": "counter_story", "critical": False},
    {"station_id": "S08_MECHANICAL_MIRROR", "title": "mechanical_mirror", "critical": True},
    {"station_id": "S09_ABSTENTION", "title": "abstention_honesty", "critical": True},
    {"station_id": "S10_ANNOTATION", "title": "annotation_audit", "critical": True},
)
EXAM_STATION_INDEX = {station["station_id"]: station for station in EXAM_STATIONS}
EXAM_STATION_IDS = tuple(EXAM_STATION_INDEX)
ALLOWED_STATUSES = {"PASS", "FAIL", "UNRESOLVED", "NOT_APPLICABLE"}


def make_exam_transcript_template(
    *,
    authority_manifest: Mapping[str, Any] | None = None,
    packet_hash: str = "",
    decision_time: str = "",
) -> dict[str, Any]:
    authority = authority_manifest or {}
    profile = authority.get("ai_seat_profile") or {}
    constitution = authority.get("constitution") or {}
    gauntlet = authority.get("gauntlet") or {}
    return {
        "schema": "ai_seat_exam_transcript_v1",
        "packet_hash": packet_hash,
        "ai_seat_profile_sha256": profile.get("sha256", ""),
        "constitution_sha256": constitution.get("sha256", ""),
        "gauntlet_protocol_sha256": gauntlet.get("protocol_sha256", ""),
        "decision_time": decision_time,
        "stations": [
            {
                "station_id": station["station_id"],
                "status": None,
                "summary": "",
                "evidence_object_ids": [],
                "doctrine_rule_ids": [],
                "first_knowable_times": {},
                "evaluated_by": "ai_seat",
                "resolution_condition": None,
            }
            for station in EXAM_STATIONS
        ],
        "declared_overall_status": None,
        "authority_contract": {
            "self_certification_allowed": False,
            "independent_validation_required": True,
            "signal_allowed": False,
        },
    }


def collect_evidence_ids(value: Any, key: str = "") -> set[str]:
    """Collect identifier values that are actually present in a sealed pack."""
    found: set[str] = set()
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            name = str(child_key)
            if isinstance(child, str) and (name == "id" or name.endswith("_id")):
                found.add(child)
            elif isinstance(child, Sequence) and not isinstance(child, (str, bytes)) and name.endswith("_ids"):
                found.update(str(item) for item in child if isinstance(item, (str, int, float)))
            found.update(collect_evidence_ids(child, name))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            found.update(collect_evidence_ids(child, key))
    return found


def validate_exam_transcript(
    transcript: Mapping[str, Any] | None,
    *,
    authority_manifest: Mapping[str, Any],
    evidence_pack: Mapping[str, Any],
    expected_packet_hash: str,
    expected_decision_time: str = "",
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    payload = transcript if isinstance(transcript, Mapping) else {}
    if payload.get("schema") != "ai_seat_exam_transcript_v1":
        _issue(issues, "invalid_exam_schema", "Exam transcript schema is missing or invalid.")

    expected_bindings = {
        "packet_hash": expected_packet_hash,
        "ai_seat_profile_sha256": (authority_manifest.get("ai_seat_profile") or {}).get("sha256"),
        "constitution_sha256": (authority_manifest.get("constitution") or {}).get("sha256"),
        "gauntlet_protocol_sha256": (authority_manifest.get("gauntlet") or {}).get("protocol_sha256"),
    }
    for field, expected in expected_bindings.items():
        if not expected or payload.get(field) != expected:
            _issue(issues, f"exam_binding_mismatch:{field}", f"Exam transcript {field} does not match the sealed packet.")
    if expected_decision_time and payload.get("decision_time") != expected_decision_time:
        _issue(
            issues,
            "exam_binding_mismatch:decision_time",
            "Exam transcript decision_time does not match the sealed packet cutoff.",
        )

    contract = payload.get("authority_contract") or {}
    if contract.get("self_certification_allowed") is not False:
        _issue(issues, "exam_self_certification_forbidden", "The AI seat cannot certify its own transcript.")
    if contract.get("independent_validation_required") is not True:
        _issue(issues, "exam_independent_validation_missing", "Independent validation must remain required.")
    if contract.get("signal_allowed") is not False:
        _issue(issues, "exam_signal_authority_forbidden", "The exam cannot grant signal authority.")

    stations = payload.get("stations")
    if not isinstance(stations, list):
        stations = []
        _issue(issues, "exam_stations_not_list", "Exam stations must be a list.")
    ids = [str(item.get("station_id") or "") for item in stations if isinstance(item, Mapping)]
    duplicates = sorted(station_id for station_id, count in Counter(ids).items() if station_id and count > 1)
    missing = sorted(set(EXAM_STATION_IDS).difference(ids))
    unknown = sorted(set(ids).difference(EXAM_STATION_IDS))
    for station_id in duplicates:
        _issue(issues, f"duplicate_exam_station:{station_id}", "Each exam station must appear exactly once.")
    for station_id in missing:
        _issue(issues, f"missing_exam_station:{station_id}", "Every exam station is mandatory.")
    for station_id in unknown:
        _issue(issues, f"unknown_exam_station:{station_id}", "Unknown exam station IDs are forbidden.")

    known_evidence = collect_evidence_ids(evidence_pack)
    known_evidence.update(
        str(item)
        for item in (authority_manifest.get("metamorphic_evidence") or {}).get("evidence_contract_ids", [])
    )
    station_results: dict[str, Any] = {}
    for item in stations:
        if not isinstance(item, Mapping):
            _issue(issues, "exam_station_not_object", "Each exam station must be an object.")
            continue
        station_id = str(item.get("station_id") or "")
        definition = EXAM_STATION_INDEX.get(station_id)
        if definition is None or station_id in station_results:
            continue
        local: list[str] = []
        status = str(item.get("status") or "")
        if status not in ALLOWED_STATUSES:
            local.append("invalid_status")
        if not str(item.get("summary") or "").strip():
            local.append("missing_summary")
        if item.get("evaluated_by") != "ai_seat":
            local.append("invalid_submitter_identity")
        evidence_ids = item.get("evidence_object_ids")
        if not isinstance(evidence_ids, list):
            local.append("evidence_ids_not_list")
            evidence_ids = []
        unknown_ids = sorted(set(map(str, evidence_ids)).difference(known_evidence)) if known_evidence else []
        if unknown_ids:
            local.append("unknown_evidence_ids:" + ",".join(unknown_ids))
        if status == "PASS" and not evidence_ids:
            local.append("pass_without_evidence")
        if status in {"FAIL", "UNRESOLVED", "NOT_APPLICABLE"} and not str(item.get("resolution_condition") or "").strip():
            local.append("nonpass_missing_resolution_condition")
        if station_id == "S01_TIME_HONESTY" and status == "PASS":
            knowable = item.get("first_knowable_times")
            if not isinstance(knowable, Mapping) or not knowable:
                local.append("time_honesty_missing_first_knowable_times")
        if station_id == "S08_MECHANICAL_MIRROR" and status == "PASS":
            metamorphic = authority_manifest.get("metamorphic_evidence") or {}
            mirror_ids = set(map(str, metamorphic.get("evidence_contract_ids") or []))
            if metamorphic.get("status") != "AVAILABLE" or not mirror_ids:
                local.append("mechanical_mirror_artifact_unavailable")
            elif not mirror_ids.intersection(map(str, evidence_ids)):
                local.append("mechanical_mirror_artifact_not_cited")
        doctrine_ids = item.get("doctrine_rule_ids")
        if not isinstance(doctrine_ids, list):
            local.append("doctrine_rule_ids_not_list")
        station_results[station_id] = {
            "status": status,
            "critical": bool(definition["critical"]),
            "contract_valid": not local,
            "issues": local,
        }
        for code in local:
            _issue(issues, f"{station_id}:{code}", f"Exam station {station_id} failed contract validation.")

    failed = sorted(
        station_id
        for station_id, result in station_results.items()
        if result["status"] in {"FAIL", "UNRESOLVED"} or not result["contract_valid"]
    )
    not_applicable = sorted(
        station_id for station_id, result in station_results.items() if result["status"] == "NOT_APPLICABLE"
    )
    # NOT_APPLICABLE is a correct refusal only when it supplies a resolution
    # condition and the final decision cannot be trade-ready.
    downgrade_required = bool(issues or failed)
    status = "PASS_CONTRACT" if not downgrade_required else "FAIL_CLOSED"
    return {
        "schema": "ai_seat_exam_validation_v1",
        "status": status,
        "downgrade_required": downgrade_required,
        "failed_stations": failed,
        "not_applicable_stations": not_applicable,
        "station_results": station_results,
        "issues": issues,
        "semantic_correctness_certified": False,
        "self_certification_used": False,
        "signal_allowed": False,
    }


def apply_exam_downgrade(decision_payload: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    """Strip promotional fields before parsing an exam-failed decision."""
    payload = copy.deepcopy(dict(decision_payload))
    if not validation.get("downgrade_required"):
        return payload
    failed = list(validation.get("failed_stations") or [])
    issue_codes = [str(item.get("code")) for item in validation.get("issues") or [] if isinstance(item, Mapping)]
    reason = "AI seat exam failed closed: " + ", ".join(failed or issue_codes or ["unknown_exam_failure"])
    payload["official_state"] = "REVIEW_REQUIRED"
    payload["setup_grade"] = "C"
    payload["direction"] = "mixed"
    payload["entry_plan"] = {
        "entry_ready": False,
        "entry_timeframe": "15m",
        "refinement_timeframe": "5m",
        "entry_price": None,
        "entry_zone_low": None,
        "entry_zone_high": None,
        "signal_type": None,
        "required_confirmation": [],
        "evidence_object_ids": [],
        "entry_anchor": None,
        "mapped_entry_price": None,
        "summary": reason,
    }
    payload["stop_loss_plan"] = {
        "stop_price": None,
        "structural_invalidation_price": None,
        "source": None,
        "buffer_notes": None,
        "evidence_object_ids": [],
        "stop_anchor": None,
        "mapped_stop_price": None,
        "summary": reason,
    }
    payload["target_plan"] = {"targets": [], "model_completion_liquidity_id": None, "summary": reason}
    payload["rr_status"] = {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": reason}
    payload["invalidation"] = {
        "invalidation_price": None,
        "condition": reason,
        "source": None,
        "evidence_object_ids": [],
        "invalidation_anchor": None,
        "mapped_invalidation_price": None,
    }
    payload["annotation_plan"] = {
        "chart_template": "review_chart",
        "show_trade_box": False,
        "labels": [],
        "levels": [],
        "reasoning_order": list((payload.get("annotation_plan") or {}).get("reasoning_order") or []),
    }
    # A failed exam cannot retain an AI-authored display exception. The
    # deterministic context atlas may still render its mandatory objects, but
    # that visibility is no longer attributed to the failed AI seat.
    payload["context_exception_requests"] = []
    if payload.get("annotation_plan_v2") is not None:
        payload["annotation_plan_v2"] = {
            "schema": "professional_smc_annotation_plan_v2",
            "style": "professional_smc_sparse",
            "objects": [],
            "notes": [reason],
        }
    self_review = dict(payload.get("self_review") or {})
    remaining = list(self_review.get("remaining_uncertainties") or [])
    remaining.append(reason)
    self_review.update(
        {
            "active_range_check": "failed",
            "poi_check": "failed",
            "annotation_check": "failed",
            "refusal_check": "passed",
            "remaining_uncertainties": remaining,
        }
    )
    self_review.setdefault("corrections_made", [])
    payload["self_review"] = self_review
    payload["final_thesis"] = reason
    return payload


def validate_unresolved_claims(
    *,
    dissent_records: Any,
    doctrine_pending_claims: Any,
    authority_manifest: Mapping[str, Any],
    evidence_pack: Mapping[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    known_evidence = collect_evidence_ids(evidence_pack)
    pending_ids = set(
        map(
            str,
            (authority_manifest.get("constitution") or {}).get("pending_human_adjudication", []),
        )
    )
    dissents = dissent_records if isinstance(dissent_records, list) else []
    pending_claims = doctrine_pending_claims if isinstance(doctrine_pending_claims, list) else []
    if not isinstance(dissent_records, list):
        _issue(issues, "dissent_records_not_list", "dissent_records must be a list.")
    if not isinstance(doctrine_pending_claims, list):
        _issue(issues, "doctrine_pending_claims_not_list", "doctrine_pending_claims must be a list.")

    for index, record in enumerate(dissents):
        prefix = f"dissent:{index}"
        if not isinstance(record, Mapping):
            _issue(issues, f"{prefix}:not_object", "Each dissent record must be an object.")
            continue
        if record.get("schema") != "ai_seat_dissent_v1":
            _issue(issues, f"{prefix}:wrong_schema", "Dissent record schema is invalid.")
        if record.get("status") != "PROPOSED_ALTERNATIVE":
            _issue(issues, f"{prefix}:wrong_status", "Dissent must remain PROPOSED_ALTERNATIVE.")
        for field in ("dissent_id", "claim", "proposed_interpretation", "resolution_condition"):
            if not str(record.get(field) or "").strip():
                _issue(issues, f"{prefix}:missing_{field}", f"Dissent record requires {field}.")
        evidence_ids = record.get("evidence_object_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            _issue(issues, f"{prefix}:ungrounded", "Dissent record requires evidence_object_ids.")
        elif known_evidence:
            unknown = sorted(set(map(str, evidence_ids)).difference(known_evidence))
            if unknown:
                _issue(issues, f"{prefix}:unknown_evidence", "Dissent cites unknown evidence IDs.")

    for index, record in enumerate(pending_claims):
        prefix = f"doctrine_pending:{index}"
        if not isinstance(record, Mapping):
            _issue(issues, f"{prefix}:not_object", "Each doctrine-pending claim must be an object.")
            continue
        for field in ("claim_id", "dependent_conclusion", "resolution_condition"):
            if not str(record.get(field) or "").strip():
                _issue(issues, f"{prefix}:missing_{field}", f"Doctrine-pending claim requires {field}.")
        decision_ids = record.get("doctrine_decision_ids")
        if not isinstance(decision_ids, list) or not decision_ids:
            _issue(issues, f"{prefix}:missing_decision_ids", "Doctrine-pending claim requires decision IDs.")
        else:
            unknown = sorted(set(map(str, decision_ids)).difference(pending_ids))
            if unknown:
                _issue(issues, f"{prefix}:unknown_decision_ids", "Claim cites non-pending doctrine decisions.")
        evidence_ids = record.get("evidence_object_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            _issue(issues, f"{prefix}:ungrounded", "Doctrine-pending claim requires evidence_object_ids.")
        elif known_evidence:
            unknown = sorted(set(map(str, evidence_ids)).difference(known_evidence))
            if unknown:
                _issue(issues, f"{prefix}:unknown_evidence", "Claim cites unknown evidence IDs.")

    unresolved = bool(dissents or pending_claims)
    return {
        "schema": "ai_seat_unresolved_claim_validation_v1",
        "status": "REVIEW_REQUIRED" if issues or unresolved else "PASS",
        "downgrade_required": bool(issues or unresolved),
        "dissent_count": len(dissents),
        "doctrine_pending_claim_count": len(pending_claims),
        "issues": issues,
        "signal_allowed": False,
    }


def _issue(issues: list[dict[str, str]], code: str, message: str) -> None:
    issues.append({"code": code, "message": message})


__all__ = [
    "EXAM_STATIONS",
    "EXAM_STATION_IDS",
    "apply_exam_downgrade",
    "collect_evidence_ids",
    "make_exam_transcript_template",
    "validate_unresolved_claims",
    "validate_exam_transcript",
]
