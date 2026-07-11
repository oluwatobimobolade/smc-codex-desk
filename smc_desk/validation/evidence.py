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


def collect_pool_ids(
    case: Mapping[str, Any],
    graph: Mapping[str, Any] | None,
) -> set[str]:
    """Every admissible evidence_id the interpretation may cite."""
    ids: set[str] = set()
    co = case.get("candidate_objects") or {}
    if isinstance(co, Mapping):
        for tf, buckets in co.items():
            if not isinstance(buckets, Mapping):
                continue
            for bucket, items in buckets.items():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, Mapping) and isinstance(it.get("object_id"), str):
                        ids.add(it["object_id"])
    if isinstance(graph, Mapping):
        for k in ("protected_point", "active_range"):
            node = graph.get(k)
            if isinstance(node, Mapping):
                for v in node.values():
                    if isinstance(v, str):
                        ids.add(v)
        for seq in (graph.get("accepted_breaks") or [],
                    graph.get("active_htf_pois") or [],
                    graph.get("unswept_external_liquidity") or []):
            if isinstance(seq, list):
                for e in seq:
                    if isinstance(e, Mapping):
                        for v in e.values():
                            if isinstance(v, str):
                                ids.add(v)
    return ids


def _walk_evidence_fields(obj: Any, path: str = "") -> list[tuple[str, list[str]]]:
    """Yield (path, [str_ids]) pairs for every evidence-like list under obj."""
    out: list[tuple[str, list[str]]] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            sub = f"{path}.{k}" if path else k
            if k in {"evidence_ids", "breaking_candidate_ids", "swept_levels",
                     "caused_breaks", "breaks_caused"} and isinstance(v, list):
                ids = [x for x in v if isinstance(x, str)]
                out.append((sub, ids))
            elif isinstance(v, (dict, list)):
                out.extend(_walk_evidence_fields(v, sub))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_walk_evidence_fields(v, f"{path}[{i}]"))
    return out


def check_evidence_grounding(
    *,
    interpretation: Mapping[str, Any],
    admissible_ids: set[str],
) -> tuple[Violation, ...]:
    """Return ERROR for evidence_ids not in the admissible set."""
    out: list[Violation] = []
    for field_path, ids in _walk_evidence_fields(interpretation):
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


__all__ = ["check_evidence_grounding", "collect_pool_ids"]