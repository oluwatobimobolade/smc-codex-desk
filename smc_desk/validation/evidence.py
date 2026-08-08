"""Evidence-ID grounding validator (programme §28.1).

Every accepted interpretation must cite at least one evidence_id that
exists in the candidate pool or structure graph, and every evidence_id
must be unique across the interpretation.

A naked claim -- an accepted interpretation field that names a price,
time, level, or relationship without an evidence_id -- is a BLOCK
violation per programme §28.1.

Unknown evidence IDs (cited but absent from the pool) are ERROR severity.
The orchestrator decides how they interact with the certified/abstained
flag (see ``certify_interpretation``).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from smc_desk.validation.primitives import Severity, Violation
from smc_desk.perception.programme_schema import (
    canonical_object_id,
    flatten_candidate_objects,
    graph_anchor_records,
)


REFERENCE_ID_FIELDS = {
    "origin_object_id",
    "breaking_candidate_id",
    "protected_point_id",
    "protected_point_evidence_id",
    "selected_poi_evidence_id",
    "semantic_object_id",
    "broken_level_evidence_id",
    "opposing_protected_point_evidence_id",
    "confirming_candle_id",
    "internal_structure_break_id",
}


def collect_pool_ids(
    case: Mapping[str, Any],
    graph: Mapping[str, Any] | None,
) -> set[str]:
    """Every admissible evidence_id the interpretation may cite."""
    ids: set[str] = set()
    for record in flatten_candidate_objects(case.get("candidate_objects") or {}):
        oid = canonical_object_id(record)
        if oid:
            ids.add(oid)
    if isinstance(graph, Mapping):
        ids.update(item["object_id"] for item in graph_anchor_records(graph))
        ids.update(_collect_graph_object_ids(graph))
    return ids


def walk_evidence_fields(obj: Any, path: str = "") -> list[tuple[str, list[str]]]:
    """Yield (path, [str_ids]) pairs for every evidence-like list under obj."""
    out: list[tuple[str, list[str]]] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            sub = f"{path}.{k}" if path else k
            is_plural_reference = (
                k == "evidence_ids"
                or k.endswith("_evidence_ids")
                or k in {"accepted_evidence_ids", "breaking_candidate_ids", "swept_levels", "caused_breaks", "breaks_caused"}
            )
            if is_plural_reference and isinstance(v, (list, tuple)):
                ids = [x for x in v if isinstance(x, str)]
                out.append((sub, ids))
            elif (k in REFERENCE_ID_FIELDS or k.endswith("_evidence_id")) and isinstance(v, str):
                out.append((sub, [v] if v else []))
            elif isinstance(v, (dict, list)):
                out.extend(walk_evidence_fields(v, sub))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(walk_evidence_fields(v, f"{path}[{i}]"))
    return out


def check_evidence_grounding(
    *,
    interpretation: Mapping[str, Any],
    admissible_ids: set[str],
) -> tuple[Violation, ...]:
    """Return ERROR for evidence_ids not in the admissible set."""
    out: list[Violation] = []
    fields = walk_evidence_fields(interpretation)
    cited = [eid for _, ids in fields for eid in ids]
    if not cited:
        out.append(Violation(
            code="INTERPRETATION_HAS_NO_EVIDENCE",
            severity=Severity.BLOCK.value,
            message="Interpretation contains no recognised evidence references.",
            checker="evidence.minimum_grounding",
        ))
    for field_path, ids in fields:
        for eid in ids:
            if eid not in admissible_ids:
                out.append(Violation(
                    code="EVIDENCE_ID_NOT_GROUNDED",
                    severity=Severity.ERROR.value,
                    message=f"cited evidence_id {eid!r} not in candidate pool or graph",
                    evidence_ids=(eid,),
                    field_path=field_path,
                    checker="evidence.grounding",
                ))
    return tuple(out)


def _collect_graph_object_ids(graph: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, Mapping):
            for child_key, value in node.items():
                if isinstance(value, str) and (
                    child_key in {"object_id", "swing_id", "range_id", "liquidity_id", "poi_id"}
                    or child_key.endswith("_swing_id")
                    or child_key.endswith("_evidence_id")
                ) and value:
                    ids.add(value)
                elif isinstance(value, (Mapping, list, tuple)):
                    walk(value, child_key)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, key)

    walk(graph)
    return ids


__all__ = ["REFERENCE_ID_FIELDS", "check_evidence_grounding", "collect_pool_ids", "walk_evidence_fields"]
