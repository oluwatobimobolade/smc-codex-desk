"""Anchor-preserving context retriever (programme §4.6, §28, §15).

The programme explicitly rejects the flat \"keep N most recent per bucket\"
recency cap and mandates that the AI always sees the causally mandatory
anchors, even at the cost of recency. This module is the canonical
retriever.

Always preserve (anchor set, per programme §4.6):
    - active external high and low
    - current protected point
    - current range endpoints
    - origin candidates of accepted breaks
    - active higher-timeframe POIs
    - unswept external liquidity
    - candidates referenced by the blind reader
    - candidates challenged by the critic

Then fill remaining capacity by:
    - causal score
    - timeframe importance
    - active lifecycle
    - visual-window proximity
    - recency

Anything not in context is reachable through the on-demand retrieval tools
in ``tools.py`` (get_candidate, search_candidates, get_parent_chain,
get_break_origin). The retriever is deterministic and the chosen set is
hash-pinned so a role prompt cannot drift silently.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from smc_desk.data.hashing import object_sha256

# Soft budget for the fill set. The anchor set ALWAYS fits regardless of budget.
DEFAULT_FILL_BUDGET = 600

ANCHOR_KINDS = (
    "active_external_high",
    "active_external_low",
    "protected_point",
    "range_endpoint",
    "break_origin",
    "htf_active_poi",
    "unswept_external_liquidity",
    "blind_reader_reference",
    "critic_challenge",
)


@dataclass(frozen=True)
class AnchorHit:
    """One anchor that must be preserved in the retrieved context."""
    candidate_id: str
    anchor_kind: str
    source: str          # which upstream evidence named it
    reason: str


@dataclass(frozen=True)
class ContextRetrievalResult:
    """Full retrieval result. ``anchor_records`` are the full candidate dicts
    for the anchor set; ``fill`` is the ranked fill set. The hash pins the
    whole chosen context so prompt drift is detectable.
    """
    anchors: tuple[AnchorHit, ...]
    anchor_records: tuple[Mapping[str, Any], ...]
    fill: tuple[Mapping[str, Any], ...]
    dropped_from_fill: tuple[str, ...]
    missing_anchor_ids: tuple[str, ...]
    budget: int
    schema: str = "anchor_preserving_context_v1"

    @property
    def sha256(self) -> str:
        return object_sha256(
            {
                "anchors": [asdict(a) for a in self.anchors],
                "anchor_records": list(self.anchor_records),
                "fill": list(self.fill),
                "dropped_from_fill": list(self.dropped_from_fill),
                "missing_anchor_ids": list(self.missing_anchor_ids),
                "budget": self.budget,
            }
        )

    @property
    def context_ids(self) -> set[str]:
        ids = {a.candidate_id for a in self.anchors}
        for rec in self.anchor_records:
            cid = rec.get("object_id")
            if isinstance(cid, str):
                ids.add(cid)
        for rec in self.fill:
            cid = rec.get("object_id")
            if isinstance(cid, str):
                ids.add(cid)
        return ids


def _candidate_pool(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Flatten every candidate in case['candidate_objects'] into a list.

    Robust to the multi-timeframe / multi-bucket structure the detector and
    atlas produce:
        {"15m": {"swings": [...], "fvgs": [...], ...},
         "1h": {"swings": [...], ...}, ...}
    """
    pool: list[Mapping[str, Any]] = []
    co = case.get("candidate_objects") or {}
    if not isinstance(co, Mapping):
        return pool
    for timeframe, buckets in co.items():
        if not isinstance(buckets, Mapping):
            continue
        for bucket, items in buckets.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, Mapping) and item.get("object_id"):
                    pool.append(item)
    return pool


def _recency(candidate: Mapping[str, Any]) -> str:
    for key in ("confirmed_at", "candidate_at", "pivot_time"):
        v = candidate.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _collect_anchors(case: Mapping[str, Any]) -> list[AnchorHit]:
    """Pull every programme-mandated anchor from the certified evidence.

    Sources we look at:
        * graph.active_range       -> active_external_high / active_external_low / range_endpoint
        * graph.protected_point    -> protected_point
        * graph.accepted_breaks    -> break_origin (for every accepted break)
        * graph.active_htf_pois    -> htf_active_poi
        * graph.unswept_external_liquidity  -> unswept_external_liquidity
        * case['blind_reader_reference_ids']  -> blind_reader_reference
        * case['critic_challenges']            -> critic_challenge
    Unknown / missing keys contribute no anchors (we do not invent).
    """
    anchors: list[AnchorHit] = []
    graph = case.get("formal_structure_graph") or {}

    rng = graph.get("active_range") if isinstance(graph.get("active_range"), Mapping) else None
    if rng:
        if rng.get("high_object_id"):
            anchors.append(AnchorHit(
                candidate_id=str(rng["high_object_id"]), anchor_kind="active_external_high",
                source="formal_structure_graph.active_range.high",
                reason="active range upper boundary per programme §4.6"))
        if rng.get("low_object_id"):
            anchors.append(AnchorHit(
                candidate_id=str(rng["low_object_id"]), anchor_kind="active_external_low",
                source="formal_structure_graph.active_range.low",
                reason="active range lower boundary per programme §4.6"))
        if rng.get("range_id"):
            anchors.append(AnchorHit(
                candidate_id=str(rng["range_id"]), anchor_kind="range_endpoint",
                source="formal_structure_graph.active_range",
                reason="active dealing range endpoint per programme §7"))

    pp = graph.get("protected_point")
    if isinstance(pp, Mapping) and pp.get("object_id"):
        anchors.append(AnchorHit(
            candidate_id=str(pp["object_id"]), anchor_kind="protected_point",
            source="formal_structure_graph.protected_point",
            reason="current protected point per programme §5 (causal origin of impulse)"))

    for br in graph.get("accepted_breaks") or []:
        if not isinstance(br, Mapping):
            continue
        if br.get("origin_object_id"):
            anchors.append(AnchorHit(
                candidate_id=str(br["origin_object_id"]), anchor_kind="break_origin",
                source=f"formal_structure_graph.accepted_breaks[{br.get('object_id') or '?'}]",
                reason=f"origin of accepted break direction={br.get('direction')}"))

    for ht in graph.get("active_htf_pois") or []:
        if isinstance(ht, Mapping) and ht.get("poi_id"):
            anchors.append(AnchorHit(
                candidate_id=str(ht["poi_id"]), anchor_kind="htf_active_poi",
                source=f"formal_structure_graph.active_htf_pois[{ht['poi_id']}]",
                reason=f"active higher-timeframe POI at {ht.get('timeframe')}"))

    for lvl in graph.get("unswept_external_liquidity") or []:
        if isinstance(lvl, Mapping) and lvl.get("object_id"):
            anchors.append(AnchorHit(
                candidate_id=str(lvl["object_id"]), anchor_kind="unswept_external_liquidity",
                source="formal_structure_graph.unswept_external_liquidity",
                reason="external liquidity level not yet consumed per programme §2.2"))

    for cid in case.get("blind_reader_reference_ids") or []:
        anchors.append(AnchorHit(
            candidate_id=str(cid), anchor_kind="blind_reader_reference",
            source="case.blind_reader_reference_ids",
            reason="blind visual reader explicitly named this candidate"))
    for cid in case.get("critic_challenges") or []:
        anchors.append(AnchorHit(
            candidate_id=str(cid), anchor_kind="critic_challenge",
            source="case.critic_challenges",
            reason="adversarial critic flagged this candidate for re-evaluation"))

    seen: set[tuple[str, str, str]] = set()
    out: list[AnchorHit] = []
    for a in anchors:
        key = (a.candidate_id, a.anchor_kind, a.source)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _rank_fill_candidates(
    pool: Iterable[Mapping[str, Any]],
    *,
    excluded: set[str],
) -> list[Mapping[str, Any]]:
    """Rank non-anchor candidates by the programme §4.6 fill ordering.

    Causal > timeframe importance > active lifecycle > recency. Ties preserve
    input order (stable sort).
    """
    scored: list[tuple[tuple, int, Mapping[str, Any]]] = []
    for index, c in enumerate(pool):
        cid = c.get("object_id")
        if not isinstance(cid, str) or cid in excluded:
            continue
        causal = 0
        if c.get("displacement_after"):
            causal += 2
        if c.get("fvg_created"):
            causal += 1
        if isinstance(c.get("breaks_caused"), list) and c["breaks_caused"]:
            causal += len(c["breaks_caused"])
        tf = str(c.get("timeframe", ""))
        tf_weight = {"1d": 5, "4h": 4, "1h": 3, "15m": 2}.get(tf, 1)
        life = str(c.get("lifecycle", "CANDIDATE"))
        life_weight = {"STRUCTURAL": 3, "PROTECTED": 3, "CANDIDATE": 1, "STALE": 0, "REJECTED": 0}.get(life, 1)
        recency = _recency(c)  # str (possibly empty); never dict
        scored.append((-causal, -tf_weight, -life_weight, recency, index, c))
    scored.sort()
    return [entry[-1] for entry in scored]


def retrieve_for_case(
    case: Mapping[str, Any],
    *,
    fill_budget: int = DEFAULT_FILL_BUDGET,
    pool: Sequence[Mapping[str, Any]] | None = None,
) -> ContextRetrievalResult:
    """Return the anchor-preserved context for one role prompt."""
    anchors = _collect_anchors(case)
    anchor_ids = {a.candidate_id for a in anchors}

    candidate_pool = list(pool) if pool is not None else _candidate_pool(case)

    by_id: dict[str, Mapping[str, Any]] = {}
    for c in candidate_pool:
        cid = c.get("object_id")
        if isinstance(cid, str):
            by_id[cid] = c

    # The anchor set ALWAYS fits in context (programme §4.6). Missing anchors
    # are reported explicitly -- they are not silently dropped.
    anchor_records: list[Mapping[str, Any]] = []
    missing_anchor_ids: list[str] = []
    for a in anchors:
        rec = by_id.get(a.candidate_id)
        if rec is None:
            missing_anchor_ids.append(a.candidate_id)
            anchor_records.append(
                {"object_id": a.candidate_id, "_anchor_kind": a.anchor_kind, "_available": False}
            )
        else:
            enriched = dict(rec)
            enriched["_anchor_kind"] = a.anchor_kind
            enriched["_anchor_reason"] = a.reason
            enriched["_anchor_source"] = a.source
            enriched["_available"] = True
            anchor_records.append(enriched)

    ranked_all = _rank_fill_candidates(candidate_pool, excluded=anchor_ids)
    fill = ranked_all[:fill_budget]
    dropped = [str(c.get("object_id", "?")) for c in ranked_all[fill_budget:] if isinstance(c.get("object_id"), str)]

    return ContextRetrievalResult(
        anchors=tuple(anchors),
        anchor_records=tuple(anchor_records),
        fill=tuple(fill),
        dropped_from_fill=tuple(dropped),
        missing_anchor_ids=tuple(missing_anchor_ids),
        budget=fill_budget,
    )


def to_compact_payload(result: ContextRetrievalResult, *, include_fill: bool = True) -> dict[str, Any]:
    """Serialise a retrieval result into the role-payload candidate_objects shape."""
    return {
        "schema": result.schema,
        "anchors": [asdict(a) for a in result.anchors],
        "candidates": list(result.anchor_records),
        "fill": list(result.fill) if include_fill else [],
        "dropped_from_fill": list(result.dropped_from_fill),
        "missing_anchor_ids": list(result.missing_anchor_ids),
        "budget": result.budget,
        "sha256": result.sha256,
    }


__all__ = [
    "ANCHOR_KINDS",
    "DEFAULT_FILL_BUDGET",
    "AnchorHit",
    "ContextRetrievalResult",
    "retrieve_for_case",
    "to_compact_payload",
]