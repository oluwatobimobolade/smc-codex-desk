"""A/B designs for the structure-lab candidate payload (programme §15).

Four designs expose the programme's comparison set:

* ``full``     -- every candidate in the pool (no compaction). The worst-case
                  ceiling against which the others are measured.
* ``flat``     -- the existing 80-most-recent-per-bucket cap (the programme's
                  rejected stop-gap; kept as a comparison point).
* ``anchor``   -- the anchor-preserving retriever WITHOUT on-demand tools.
* ``anchor_tools`` -- anchor retriever WITH the tools surface (§4.6 default).

Each returns ``{"candidate_objects": ..., "ab_design": ..., "stats": ...}`` so
the role runtime can swap designs and the A/B report (step 15) can compare
sizes, fill ratios, and missing-anchor counts deterministically.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from smc_desk.brain.structure_lab import context_retriever
from smc_desk.brain.structure_lab.prompts import compact_candidate_objects

ALL_DESIGNS = ("full", "flat", "anchor", "anchor_tools")


def build_candidate_payload(
    case: Mapping[str, Any],
    *,
    design: str = "anchor_tools",
    flat_per_bucket_limit: int = 80,
    anchor_fill_budget: int = 600,
) -> dict[str, Any]:
    """Return the candidate_objects payload under the requested design."""
    if design not in ALL_DESIGNS:
        raise ValueError(f"Unknown ab design: {design!r}. Available: {ALL_DESIGNS}")

    if design == "full":
        co = case.get("candidate_objects") or {}
        return {"candidate_objects": co, "ab_design": design, "stats": {
            "design": design,
            "candidates_kept": _candidate_count(co),
            "estimated_bytes": _approx_size(co),
            "anchors_required": 0,
            "anchors_preserved": 0,
            "missing_anchor_ids": [],
            "fill_count": _candidate_count(co),
            "dropped_from_fill_count": 0,
            "fill_budget": None,
            "context_sha256": None,
        }}

    if design == "flat":
        co = case.get("candidate_objects") or {}
        compacted, summary = compact_candidate_objects(co, per_bucket_limit=flat_per_bucket_limit)
        stats = dict(summary.get("totals", {}))
        stats.update({
            "design": design,
            "estimated_bytes": _approx_size(compacted),
            "anchors_required": 0,
            "anchors_preserved": 0,
            "missing_anchor_ids": [],
            "fill_count": stats.get("candidates_after", 0),
            "dropped_from_fill_count": max(stats.get("candidates_before", 0) - stats.get("candidates_after", 0), 0),
            "fill_budget": flat_per_bucket_limit,
            "context_sha256": None,
        })
        return {"candidate_objects": compacted, "ab_design": design, "stats": stats,
                "compaction_summary": summary}

    # anchor / anchor_tools share retrieval; the difference is the tool schema
    # advertised to the model (added by attach_tools_to_payload below).
    result = context_retriever.retrieve_for_case(case, fill_budget=anchor_fill_budget)
    payload = context_retriever.to_compact_payload(result)
    stats = {
        "design": design,
        "anchors_required": len(result.anchors),
        "anchors_preserved": sum(1 for r in result.anchor_records if r.get("_available") is not False),
        "missing_anchor_ids": list(result.missing_anchor_ids),
        "fill_count": len(result.fill),
        "dropped_from_fill_count": len(result.dropped_from_fill),
        "fill_budget": result.budget,
        "context_sha256": result.sha256,
        "estimated_bytes": _approx_size(payload["candidates"]) + _approx_size(payload["fill"]),
    }
    if design == "anchor_tools":
        payload = attach_tools_to_payload(payload)
    return {"candidate_objects": payload, "ab_design": design, "stats": stats}


def attach_tools_to_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Add the retrieval tool schema the harness advertises (design=anchor_tools)."""
    if payload.get("tools_attached"):
        return payload
    from smc_desk.brain.structure_lab.tools import TOOL_DEFINITIONS
    payload["tools"] = list(TOOL_DEFINITIONS)
    payload["tools_attached"] = True
    return payload


def _approx_size(obj: Any) -> int:
    try:
        return len(json.dumps(obj, default=str, sort_keys=True))
    except (TypeError, ValueError):
        return 0


def _candidate_count(co: Any) -> int:
    n = 0
    if not isinstance(co, Mapping):
        return 0
    for tf, buckets in co.items():
        if not isinstance(buckets, Mapping):
            continue
        for bucket, items in buckets.items():
            if isinstance(items, list):
                n += len(items)
    return n


__all__ = [
    "ALL_DESIGNS",
    "build_candidate_payload",
    "attach_tools_to_payload",
]