from typing import Any, List, Dict
from pydantic import BaseModel
from collections import defaultdict

from smc_desk.evaluation.human_challenge import HumanChallengeEvaluator

class AnnotatorSubmission(BaseModel):
    annotator_id: str
    case_id: str
    # Object type -> List of proposed objects
    proposed_objects: Dict[str, List[dict]]

class AdjudicationResult(BaseModel):
    case_id: str
    object_type: str
    agreed_objects: List[dict]
    disputed_objects: List[dict]
    agreement_rate: float


def _normalise_object(raw: dict[str, Any], object_type: str, annotator_id: str) -> dict[str, Any]:
    item = dict(raw)
    item.setdefault("object_type", object_type)
    item.setdefault("primitive", object_type)
    item["_annotator_id"] = annotator_id
    return item


def _cluster_key(case_id: str, object_type: str) -> str:
    return f"{case_id}:{object_type}"


def _public_cluster_object(cluster: list[dict[str, Any]], *, agreed: bool) -> dict[str, Any]:
    anchor = {key: value for key, value in cluster[0].items() if not key.startswith("_")}
    annotators = sorted({str(item["_annotator_id"]) for item in cluster})
    anchor.update(
        {
            "agreement_status": "agreed" if agreed else "disputed",
            "supporting_annotators": annotators,
            "support_count": len(annotators),
            "cluster_size": len(cluster),
        }
    )
    if not agreed:
        anchor["cluster_members"] = [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in cluster
        ]
    return anchor


def compute_inter_annotator_agreement(submissions: List[AnnotatorSubmission]) -> Dict[str, AdjudicationResult]:
    """
    Computes agreement between multiple annotators (e.g. 2 independent SMC experts).
    Identifies exact/partial matches and isolates disagreements for the final adjudicator.
    """
    evaluator = HumanChallengeEvaluator()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    annotators_by_case: dict[str, set[str]] = defaultdict(set)
    for submission in submissions:
        annotators_by_case[submission.case_id].add(submission.annotator_id)
        for object_type, objects in submission.proposed_objects.items():
            for raw in objects:
                grouped[(submission.case_id, object_type)].append(
                    _normalise_object(raw, object_type, submission.annotator_id)
                )

    results: dict[str, AdjudicationResult] = {}
    for (case_id, object_type), objects in grouped.items():
        clusters: list[list[dict[str, Any]]] = []
        for obj in objects:
            placed = False
            for cluster in clusters:
                cluster_annotators = {item["_annotator_id"] for item in cluster}
                if obj["_annotator_id"] in cluster_annotators:
                    continue
                if any(evaluator._is_match(obj, existing) for existing in cluster):
                    cluster.append(obj)
                    placed = True
                    break
            if not placed:
                clusters.append([obj])

        agreed: list[dict[str, Any]] = []
        disputed: list[dict[str, Any]] = []
        for cluster in clusters:
            unique_annotators = {item["_annotator_id"] for item in cluster}
            is_agreed = len(unique_annotators) >= 2
            if is_agreed:
                agreed.append(_public_cluster_object(cluster, agreed=True))
            else:
                disputed.append(_public_cluster_object(cluster, agreed=False))

        agreement_rate = len(agreed) / len(clusters) if clusters else 0.0
        results[_cluster_key(case_id, object_type)] = AdjudicationResult(
            case_id=case_id,
            object_type=object_type,
            agreed_objects=agreed,
            disputed_objects=disputed,
            agreement_rate=agreement_rate,
        )

    return results
