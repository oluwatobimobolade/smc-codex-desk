"""AI-first consensus and later human-certification boundary."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from smc_desk.data.hashing import object_sha256


CONSENSUS_FIELDS = (
    "classification",
    "parent_external_state",
    "child_internal_state",
    "controlling_timeframe",
    "selected_poi_evidence_id",
)


def build_ai_structure_consensus(reviews: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Combine independent AI views without pretending they are human gold."""
    if len(reviews) < 2:
        raise ValueError("AI consensus requires at least two separately recorded reviews.")
    reviewer_ids = [str(review.get("reviewer_id") or "") for review in reviews]
    if any(not reviewer_id for reviewer_id in reviewer_ids) or len(set(reviewer_ids)) != len(reviewer_ids):
        raise ValueError("AI reviewer IDs must be non-empty and unique.")

    identities = {
        (
            str(review.get("provider_name") or "unknown"),
            str(review.get("model_name") or "unknown"),
        )
        for review in reviews
    }
    episodes = [dict(review.get("causal_episode") or {}) for review in reviews]
    consensus: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    for field in CONSENSUS_FIELDS:
        values = [episode.get(field) for episode in episodes]
        counts = Counter(_stable_value(value) for value in values)
        winner, support = counts.most_common(1)[0]
        decoded = next(value for value in values if _stable_value(value) == winner)
        if support == len(values):
            consensus[field] = decoded
        else:
            consensus[field] = None
            disagreements.append(
                {
                    "field": field,
                    "values": {reviewer_ids[index]: values[index] for index in range(len(values))},
                    "majority_value": decoded if support > len(values) / 2 else None,
                    "support": support,
                }
            )

    confidences = [float(episode.get("confidence", 0.0)) for episode in episodes]
    payload = {
        "schema": "ai_structure_consensus_v1",
        "reviewer_ids": reviewer_ids,
        "provider_model_identities": [list(identity) for identity in sorted(identities)],
        "independence_quality": "MULTI_PROVIDER" if len(identities) > 1 else "SAME_PROVIDER_SEPARATE_ROLE_RUNS",
        "consensus": consensus,
        "disagreements": disagreements,
        "mean_reported_confidence": round(sum(confidences) / len(confidences), 6),
        "consensus_status": "AGREEMENT" if not disagreements else "DISAGREEMENT_REQUIRES_REVIEW",
        "truth_class": "AI_WEAK_CONSENSUS",
        "gold_eligible": False,
        "human_certification_required_for_gold": True,
        "signal_allowed": False,
    }
    payload["consensus_sha256"] = object_sha256(payload)
    return payload


def build_human_certification_template(consensus: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    """Create a later spot-check form; never auto-fill human judgments."""
    return {
        "schema": "human_structure_certification_v1",
        "case_id": case_id,
        "ai_consensus_sha256": consensus.get("consensus_sha256"),
        "reviewer_a": {"human_id": None, "decision": None, "reasoning": None, "completed_at": None},
        "reviewer_b": {"human_id": None, "decision": None, "reasoning": None, "completed_at": None},
        "adjudicator": {"human_id": None, "resolution": None, "reasoning": None, "completed_at": None},
        "status": "AWAITING_HUMAN_CERTIFICATION",
        "gold_eligible": False,
        "truth_policy": "AI consensus may prioritize review but cannot self-certify as human gold.",
    }


def _stable_value(value: Any) -> str:
    return object_sha256(value)
