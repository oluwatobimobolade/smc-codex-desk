"""Canonical POI candidate contract shared by selection and market state.

The detector, POI lifecycle, and causal authority legitimately carry different
amounts of evidence.  They must not, however, use different names for the same
facts once a candidate reaches ranking.  This adapter is the single boundary:
it preserves the original payload while exposing stable identifiers and
selection facts without inventing missing evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA = "canonical_poi_candidate_v1"

PRIMARY_CAUSAL_STATUSES = {
    "ELIGIBLE_CAUSAL_OB",
    "ELIGIBLE_CAUSAL_FVG",
}
SECONDARY_CAUSAL_STATUSES = {
    "SECONDARY_INTERNAL_REACTION_CANDIDATE",
    "PARENT_SCOPE_REFINEMENT_CANDIDATE",
}
SPENT_STATES = {
    "consumed",
    "expired",
    "full",
    "fully_mitigated",
    "invalidated",
    "spent",
    "superseded",
    "terminal",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonicalize_poi_candidate(
    poi: Mapping[str, Any],
    *,
    fallback_direction: str | None = None,
) -> dict[str, Any]:
    """Return one stable POI shape without discarding source-specific fields.

    ``object_id`` is the candidate identity used by every downstream consumer.
    For causal-authority objects this is the timeframe-qualified ``poi_id``;
    ``source_object_id`` remains the underlying detector object.
    """
    evidence = _mapping(poi.get("evidence"))
    metadata = _mapping(poi.get("metadata"))
    admission = _mapping(metadata.get("causal_origin_admission"))
    certificate = _mapping(poi.get("causal_certificate"))

    object_id = str(poi.get("object_id") or poi.get("poi_id") or "")
    source_object_id = str(poi.get("source_object_id") or object_id)
    causal_status = str(poi.get("causal_status") or "")

    explicitly_rejected = (
        evidence.get("poi_grade") is False
        or admission.get("admitted") is False
        or causal_status.startswith("REJECTED")
    )
    if causal_status:
        caused_structure_break = (
            causal_status in PRIMARY_CAUSAL_STATUSES | SECONDARY_CAUSAL_STATUSES
            and certificate.get("status", "PASS") == "PASS"
            and not explicitly_rejected
        )
    else:
        caused_structure_break = (
            bool(evidence.get("caused_structure_break"))
            and evidence.get("poi_grade") is not False
            and not explicitly_rejected
        )

    structure_scope = str(
        poi.get("linked_break_scope")
        or metadata.get("linked_break_scope")
        or evidence.get("structure_scope")
        or "internal"
    ).lower()
    displacement_strength = _number(
        poi.get("linked_break_displacement_strength")
        or evidence.get("displacement_atr")
        or evidence.get("displacement_strength")
        or _mapping(metadata.get("displacement")).get("score")
    )

    freshness = _canonical_freshness(poi)
    direction = str(poi.get("direction") or fallback_direction or "unknown").lower()
    canonical = dict(poi)
    canonical.update(
        {
            "schema": SCHEMA,
            "object_id": object_id,
            "poi_id": str(poi.get("poi_id") or object_id),
            "source_object_id": source_object_id,
            "direction": direction,
            "causal_status": causal_status or None,
            "causal_eligible": causal_status in PRIMARY_CAUSAL_STATUSES and not explicitly_rejected,
            "caused_structure_break": caused_structure_break,
            "structure_scope": structure_scope,
            "displacement_strength": displacement_strength,
            "freshness": freshness,
            "is_spent": freshness in SPENT_STATES,
            "admission_status": (
                "rejected"
                if explicitly_rejected
                else "admitted"
                if evidence.get("poi_grade") is True or admission.get("admitted") is True
                else "not_explicitly_graded"
            ),
        }
    )
    return canonical


def _canonical_freshness(poi: Mapping[str, Any]) -> str:
    explicit = str(poi.get("freshness") or "").lower()
    if explicit:
        return explicit
    activity = str(poi.get("activity_status") or "").lower()
    terminal = str(poi.get("terminal_reason") or "").lower()
    mitigation = str(poi.get("mitigation_status") or "").lower()
    if terminal not in {"", "none"}:
        return terminal
    if activity == "terminal":
        return terminal if terminal not in {"", "none"} else "terminal"
    if mitigation == "full":
        return "fully_mitigated"
    if mitigation == "partial":
        return "partial"
    return "fresh"


__all__ = [
    "PRIMARY_CAUSAL_STATUSES",
    "SCHEMA",
    "SECONDARY_CAUSAL_STATUSES",
    "SPENT_STATES",
    "canonicalize_poi_candidate",
]
