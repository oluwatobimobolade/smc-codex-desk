"""Fail-closed causal POI authority for the canonical evidence path.

Detectors emit geometric OB/FVG candidates. This module decides which objects
may be called primary, secondary, refinement, or inducement hypotheses. It uses
eligibility gates and lexicographic comparison, not a confidence score that
pretends to prove institutional intent or guarantee a future reaction.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


DIRECTIONS = ("bullish", "bearish")
TIMEFRAMES = ("1d", "4h", "1h", "15m", "5m")
POI_TIMEFRAME_PREFERENCE = ("4h", "1h", "1d", "15m", "5m")
LIFECYCLE_ORDER = {
    "fresh": 4,
    "untouched": 4,
    "touched": 3,
    "partial": 2,
    "partially_mitigated": 2,
}


def build_causal_poi_authority(
    *,
    detector_candidates: Mapping[str, Any],
    formal_structure_graph: Mapping[str, Any],
) -> dict[str, Any]:
    """Build per-timeframe causal episodes and directional POI selections."""
    timeframe_results: dict[str, Any] = {}
    graph_nodes = formal_structure_graph.get("timeframes") or {}
    active_range = formal_structure_graph.get("active_range") or {}
    enforcement_ready = any(
        isinstance(payload, Mapping)
        and any(
            isinstance(item, Mapping) and item.get("available") is True
            for item in (payload.get("poi_lifecycle_contract") or [])
        )
        for payload in detector_candidates.values()
    )
    for timeframe in TIMEFRAMES:
        payload = detector_candidates.get(timeframe)
        node = graph_nodes.get(timeframe)
        if not isinstance(payload, Mapping) or not isinstance(node, Mapping):
            continue
        timeframe_results[timeframe] = _select_timeframe(
            timeframe=timeframe,
            direction=str(node.get("external_bias") or "unknown"),
            payload=payload,
            graph_node=node,
            active_range=active_range,
        )

    scenarios = {
        direction: _build_direction_scenario(
            direction=direction,
            timeframe_results=timeframe_results,
            active_range=active_range,
        )
        for direction in DIRECTIONS
    }
    parent_child = formal_structure_graph.get("parent_child_context") or {}
    aligned = str(parent_child.get("aligned_bias") or "mixed")
    official_direction = aligned if aligned in DIRECTIONS and not parent_child.get("has_conflict") else "mixed"
    official = scenarios.get(official_direction) if official_direction in DIRECTIONS else None
    if official and official.get("status") == "SELECTED":
        status = "SELECTED"
    elif official_direction == "mixed":
        status = "REVIEW_REQUIRED"
    else:
        status = "UNRESOLVED"

    return {
        "schema": "causal_poi_authority_v1",
        "status": status,
        "official_direction": official_direction,
        "official_selection": official,
        "timeframes": timeframe_results,
        "scenarios": scenarios,
        "invariants": {
            "status": "PASS",
            "rules": [
                "candidate_geometry_is_not_primary_authority",
                "causal_origin_gate_rejection_cannot_be_promoted",
                "explicit_break_lineage_required",
                "explicit_departure_trace_required_for_order_block",
                "accepted_external_origin_outranks_nested_range_membership",
                "duplicate_origin_lineages_consolidated_before_selection",
                "opposing_external_break_supersedes_old_origin",
                "fvg_secondary_when_causal_ob_exists",
                "protected_reversal_origin_may_outrank_shallow_continuation",
                "depth_is_tiebreak_not_eligibility",
                "parent_scope_objects_may_refine_but_never_own_primary_authority",
                "inducement_is_hypothesis_only",
            ],
        },
        "authority_contract": {
            "signal_allowed": False,
            "execution": "disabled",
            "ai_may_rank_eligible_candidates": True,
            "ai_may_override_ineligible_candidate": False,
            "abstain_when_causality_unresolved": True,
            "reaction_guaranteed": False,
            "certainty_definition": "certainty_of_rule_classification_not_future_reaction",
            "enforcement_ready": enforcement_ready,
            "enforcement_reason": (
                "canonical_poi_lifecycle_present"
                if enforcement_ready
                else "legacy_or_synthetic_pack_has_no_canonical_poi_lifecycle"
            ),
        },
    }


def _select_timeframe(
    *,
    timeframe: str,
    direction: str,
    payload: Mapping[str, Any],
    graph_node: Mapping[str, Any],
    active_range: Mapping[str, Any],
) -> dict[str, Any]:
    if direction not in DIRECTIONS:
        return _empty_timeframe(timeframe, direction, "UNKNOWN_STRUCTURE_DIRECTION")
    accepted_summary = graph_node.get("latest_external_break")
    if not isinstance(accepted_summary, Mapping):
        return _empty_timeframe(timeframe, direction, "NO_ACCEPTED_EXTERNAL_BREAK")
    accepted_id = str(accepted_summary.get("object_id") or "")
    breaks = _objects(payload.get("structure_breaks"))
    break_index = {str(item.get("object_id") or ""): item for item in breaks}
    accepted = break_index.get(accepted_id)
    if not accepted:
        return _empty_timeframe(timeframe, direction, "ACCEPTED_BREAK_NOT_IN_EVIDENCE", accepted_id=accepted_id)

    raw_index = _raw_poi_index(payload)
    eligible_obs: list[dict[str, Any]] = []
    eligible_fvgs: list[dict[str, Any]] = []
    internal_reactions: list[dict[str, Any]] = []
    parent_scope_candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for lifecycle in _objects(payload.get("pois")):
        if not _parent_scope_eligible(lifecycle):
            continue
        candidate = _evaluate_parent_scope_candidate(
            timeframe=timeframe,
            lifecycle=lifecycle,
            raw_index=raw_index,
            break_index=break_index,
        )
        if candidate is not None:
            parent_scope_candidates.append(candidate)

    for lifecycle in _candidate_lifecycle_records(payload):
        if str(lifecycle.get("direction") or "") != direction:
            continue
        lifecycle = _reconcile_lifecycle_to_formal_direction(lifecycle, direction)
        candidate = _evaluate_candidate(
            timeframe=timeframe,
            direction=direction,
            lifecycle=lifecycle,
            raw_index=raw_index,
            break_index=break_index,
            accepted=accepted,
            active_range=active_range,
        )
        causal_status = candidate["causal_status"]
        if causal_status == "ELIGIBLE_CAUSAL_OB":
            eligible_obs.append(candidate)
        elif causal_status == "ELIGIBLE_CAUSAL_FVG":
            eligible_fvgs.append(candidate)
        elif causal_status == "SECONDARY_INTERNAL_REACTION_CANDIDATE":
            internal_reactions.append(candidate)
        elif causal_status.startswith("REJECTED"):
            rejected.append(candidate)
        else:
            unresolved.append(candidate)

    ranked_obs = sorted(eligible_obs, key=lambda item: _pairwise_key(item, direction), reverse=True)
    ranked_fvgs = sorted(eligible_fvgs, key=lambda item: _pairwise_key(item, direction), reverse=True)
    unresolved_ob_lineage = [item for item in unresolved if item.get("kind") == "order_block"]
    fvg_primary_blockers = [*internal_reactions, *unresolved_ob_lineage]
    if ranked_obs:
        pool = ranked_obs
    elif ranked_fvgs and not fvg_primary_blockers:
        pool = ranked_fvgs
    else:
        pool = []
    if not pool:
        blocked_fvgs = []
        if ranked_fvgs and fvg_primary_blockers:
            blocked_fvgs = [
                {
                    **item,
                    "causal_status": "UNRESOLVED_FVG_PRIMARY_BLOCKED_BY_OB_LINEAGE",
                    "causal_failures": ["order_block_lineage_must_be_resolved_before_standalone_fvg_promotion"],
                }
                for item in ranked_fvgs
            ]
        return {
            **_empty_timeframe(
                timeframe,
                direction,
                "FVG_PRIMARY_BLOCKED_BY_UNRESOLVED_OB_LINEAGE" if blocked_fvgs else "CAUSAL_ORIGIN_UNRESOLVED",
                accepted_id=accepted_id,
            ),
            "unresolved_candidates": [*unresolved, *blocked_fvgs],
            "rejected_candidates": rejected,
            "internal_reaction_candidates": internal_reactions,
            "parent_scope_candidates": parent_scope_candidates,
        }

    primary = dict(pool[0])
    primary["poi_role"] = "primary_causal_poi" if ranked_obs else "standalone_fvg_primary"
    primary["primary_reason"] = (
        "Explicit unbroken break lineage and traced departure-origin ownership."
        if ranked_obs
        else "No eligible causal OB exists; the FVG is explicitly part of the accepted causal impulse."
    )
    secondary: list[dict[str, Any]] = []
    for candidate in [*pool[1:], *(ranked_fvgs if ranked_obs else []), *internal_reactions]:
        item = dict(candidate)
        item["poi_role"] = "secondary_reaction_poi" if item["kind"] == "order_block" else "supporting_fvg"
        item["lost_to_primary_reasons"] = _comparison_reasons(primary, item)
        secondary.append(item)
    return {
        "status": "SELECTED",
        "timeframe": timeframe,
        "direction": direction,
        "accepted_break_id": accepted_id,
        "primary_causal_poi": primary,
        "secondary_reaction_pois": secondary,
        "unresolved_candidates": unresolved,
        "rejected_candidates": rejected,
        "internal_reaction_candidates": internal_reactions,
        "parent_scope_candidates": parent_scope_candidates,
        "pairwise_decisions": [
            {
                "winner": primary["poi_id"],
                "loser": item["poi_id"],
                "reasons": item.get("lost_to_primary_reasons", []),
            }
            for item in secondary
        ],
    }


def _first_lifecycle_event_time(
    lifecycle: Mapping[str, Any],
    event_type: str,
) -> Any:
    for event in lifecycle.get("event_history") or []:
        if not isinstance(event, Mapping):
            continue
        if str(event.get("event_type") or "") == event_type:
            return event.get("timestamp")
    return None


def _evaluate_candidate(
    *,
    timeframe: str,
    direction: str,
    lifecycle: Mapping[str, Any],
    raw_index: Mapping[str, Mapping[str, Any]],
    break_index: Mapping[str, Mapping[str, Any]],
    accepted: Mapping[str, Any],
    active_range: Mapping[str, Any],
) -> dict[str, Any]:
    poi_id = str(lifecycle.get("poi_id") or lifecycle.get("object_id") or "")
    source_id = _source_object_id(poi_id)
    raw = raw_index.get(source_id)
    kind = "fvg" if str(lifecycle.get("created_by") or lifecycle.get("kind") or "").lower() == "fvg" else "order_block"
    base = {
        # Downstream selection uses one identifier contract. ``poi_id`` remains
        # the lifecycle identity and ``source_object_id`` remains the raw
        # detector identity, but the candidate itself is addressed by
        # ``object_id`` everywhere after this authority boundary.
        "object_id": poi_id,
        "poi_id": poi_id,
        "source_object_id": source_id,
        "timeframe": timeframe,
        "direction": direction,
        "kind": kind,
        "price_low": _number(lifecycle.get("price_low")),
        "price_high": _number(lifecycle.get("price_high")),
        "freshness": str(lifecycle.get("freshness") or "unknown"),
        "price_relation": str(lifecycle.get("price_relation") or "unknown"),
        "validity_status": lifecycle.get("validity_status"),
        "scope": lifecycle.get("scope"),
        "event_history": list(lifecycle.get("event_history") or []),
        "first_touch_time": _first_lifecycle_event_time(
            lifecycle,
            "OBJECT_FIRST_TOUCHED",
        ),
    }
    if not raw:
        return {**base, "causal_status": "UNRESOLVED_RAW_OBJECT_MISSING", "causal_failures": ["raw_detector_object_missing"]}

    evidence = raw.get("evidence") or {}
    metadata = raw.get("metadata") or {}
    if kind == "order_block":
        admission = metadata.get("causal_origin_admission")
        admission = admission if isinstance(admission, Mapping) else {}
        if evidence.get("poi_grade") is False or admission.get("admitted") is False:
            reason = str(
                admission.get("reason")
                or evidence.get("admission_status")
                or "causal_origin_gate_rejected"
            )
            return {
                **base,
                "causal_status": "REJECTED_CAUSAL_ORIGIN_GATE",
                "causal_failures": [reason],
                "causal_origin_admission": dict(admission),
            }
    accepted_origin_override = _accepted_external_origin_survives_nested_range_reclassification(
        lifecycle=lifecycle,
        raw=raw,
        accepted=accepted,
        direction=direction,
    )
    if not _lifecycle_eligible(lifecycle) and not accepted_origin_override:
        return {**base, "causal_status": "REJECTED_LIFECYCLE", "causal_failures": ["poi_not_fresh_or_active"]}
    if accepted_origin_override:
        base.update(
            {
                "authority_reconciliation": "accepted_external_origin_survives_newer_nested_range_straddle",
                "authority_scope": "causal_scenario_only",
                "active_entry_authority": False,
                "lifecycle_scope_preserved": lifecycle.get("scope"),
                "lifecycle_validity_status_preserved": lifecycle.get("validity_status"),
            }
        )
    lineage = _select_causal_lineage(
        raw=raw,
        break_index=break_index,
        direction=direction,
        accepted_break_id=str(accepted.get("object_id") or ""),
    )
    linked_break_id = str((lineage or {}).get("linked_break_id") or "")
    base.update({
        "linked_break_id": linked_break_id or None,
        "linked_break_ids": [item["linked_break_id"] for item in _candidate_lineages(raw)],
        "originating_fvg_id": evidence.get("originating_fvg_id"),
        "departure_body_ratio": _number(evidence.get("body_ratio")),
        "source_candle_ids": list(raw.get("source_candle_ids") or []),
        "origin_time": raw.get("pivot_time"),
        "confirmation_time": raw.get("confirmed_at"),
        "causal_link_method": metadata.get("causal_link_method"),
        "origin_geometry": metadata.get("origin_geometry"),
        "origin_cluster_candle_ids": list(metadata.get("origin_cluster_candle_ids") or []),
        "departure_candle_ids": list((lineage or {}).get("departure_candle_ids") or metadata.get("departure_candle_ids") or []),
    })
    if not linked_break_id:
        return {**base, "causal_status": "UNRESOLVED_NO_EXPLICIT_BREAK_LINK", "causal_failures": ["temporal_proximity_is_not_causality"]}
    linked = break_index.get(linked_break_id)
    if not linked:
        return {**base, "causal_status": "UNRESOLVED_LINKED_BREAK_MISSING", "causal_failures": ["linked_break_not_in_evidence"]}
    if str(linked.get("direction") or "") != direction:
        return {**base, "causal_status": "REJECTED_DIRECTION", "causal_failures": ["linked_break_direction_mismatch"]}
    accepted_time = _time(accepted.get("confirmed_at"))
    linked_time = _time(linked.get("confirmed_at"))
    origin_time = _time(raw.get("pivot_time"))
    if accepted_time is None or linked_time is None or linked_time > accepted_time:
        return {**base, "causal_status": "REJECTED_TEMPORAL_ORDER", "causal_failures": ["origin_does_not_precede_accepted_break"]}
    if origin_time is None or origin_time > linked_time:
        return {**base, "causal_status": "REJECTED_TEMPORAL_ORDER", "causal_failures": ["origin_time_missing_or_after_linked_break"]}
    opposing = [
        item for item in break_index.values()
        if _scope(item) == "external"
        and str(item.get("direction") or "") != direction
        and (when := _time(item.get("confirmed_at"))) is not None
        and linked_time < when <= accepted_time
    ]
    if opposing:
        return {
            **base,
            "causal_status": "REJECTED_SUPERSEDED_LINEAGE",
            "causal_failures": ["opposing_external_break_superseded_origin"],
            "superseding_break_ids": [str(item.get("object_id") or "") for item in opposing],
        }
    if kind == "order_block" and metadata.get("causal_link_method") != "explicit_break_departure_trace":
        return {
            **base,
            "causal_status": "UNRESOLVED_GEOMETRIC_OB_ONLY",
            "causal_failures": ["order_block_has_no_explicit_departure_trace"],
        }
    if kind == "fvg" and not (
        metadata.get("causal_link_method") == "break_source_candle_overlap"
        and evidence.get("location_context") == "causal_impulse_overlap"
    ):
        return {
            **base,
            "causal_status": "UNRESOLVED_TEMPORAL_FVG_LINK",
            "causal_failures": ["fvg_time_proximity_is_not_causal_impulse_membership"],
        }

    break_evidence = linked.get("evidence") or {}
    broke_protected = bool(break_evidence.get("broke_protected_swing"))
    valid_choch = bool(break_evidence.get("valid_choch"))
    owns_latest = linked_break_id == str(accepted.get("object_id") or "")
    linked_scope = _scope(linked)
    range_location = _range_location(base, active_range)
    parent_origin_beyond_nested_range = _outside_range_parent_origin_allowed(
        range_location=range_location,
        direction=direction,
        linked_scope=linked_scope,
        owns_latest=owns_latest,
        broke_protected=broke_protected,
        valid_choch=valid_choch,
    )
    if range_location.startswith("outside_") and not parent_origin_beyond_nested_range:
        return {
            **base,
            "range_location": range_location,
            "range_relationship": "outside_without_external_origin_authority",
            "causal_status": "UNRESOLVED_OUTSIDE_ACTIVE_RANGE",
            "causal_failures": ["candidate_outside_certified_active_range_without_parent_origin_exception"],
        }
    lineage_role = (
        "protected_reversal_origin"
        if broke_protected and valid_choch
        else "latest_external_continuation_origin"
        if owns_latest
        else "prior_unbroken_lineage_origin"
    )
    range_relationship = (
        "accepted_external_origin_beyond_newer_nested_range"
        if parent_origin_beyond_nested_range
        else "inside_certified_active_range"
        if not range_location.startswith("outside_")
        else "unknown"
    )
    certificate = _causal_certificate(
        accepted=accepted,
        linked=linked,
        base=base,
        owns_latest=owns_latest,
        no_opposing_external_break=not opposing,
        range_relationship=range_relationship,
        certificate_role="primary_eligibility",
    )
    result = {
        **base,
        "linked_break_time": linked.get("confirmed_at"),
        "linked_break_scope": linked_scope,
        "linked_break_type": str(linked.get("break_type") or ""),
        "linked_break_displacement_strength": _number(break_evidence.get("displacement_strength")),
        "broke_protected_swing": broke_protected,
        "valid_choch": valid_choch,
        "owns_latest_external_break": owns_latest,
        "lineage_role": lineage_role,
        "range_location": range_location,
        "range_relationship": range_relationship,
        "range_location_aligned": (
            parent_origin_beyond_nested_range or _range_location_aligned(range_location, direction)
        ),
        "causal_certificate": certificate,
        "causal_failures": [],
        "causal_status": "ELIGIBLE_CAUSAL_FVG" if kind == "fvg" else "ELIGIBLE_CAUSAL_OB",
    }
    if linked_scope != "external":
        result["causal_status"] = "SECONDARY_INTERNAL_REACTION_CANDIDATE"
        result["poi_role"] = "secondary_reaction_poi"
        result["causal_failures"] = ["internal_break_cannot_own_primary_external_poi"]
    return result


def _evaluate_parent_scope_candidate(
    *,
    timeframe: str,
    lifecycle: Mapping[str, Any],
    raw_index: Mapping[str, Mapping[str, Any]],
    break_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Certify a parent-scope child object for refinement only.

    These objects may refine an already-certified HTF primary POI. They cannot
    become the primary POI for their own timeframe while outside that
    timeframe's protected range.
    """
    direction = str(lifecycle.get("direction") or "")
    if direction not in DIRECTIONS:
        return None
    poi_id = str(lifecycle.get("poi_id") or lifecycle.get("object_id") or "")
    source_id = _source_object_id(poi_id)
    raw = raw_index.get(source_id)
    if not raw:
        return None
    kind = "fvg" if str(lifecycle.get("created_by") or lifecycle.get("kind") or "").lower() == "fvg" else "order_block"
    metadata = raw.get("metadata") or {}
    evidence = raw.get("evidence") or {}
    lineage = _select_causal_lineage(
        raw=raw,
        break_index=break_index,
        direction=direction,
        accepted_break_id=None,
    )
    if not lineage:
        return None
    linked_break_id = str(lineage["linked_break_id"])
    linked = break_index.get(linked_break_id)
    if not linked:
        return None
    origin_time = _time(raw.get("pivot_time"))
    linked_time = _time(linked.get("confirmed_at"))
    if origin_time is None or linked_time is None or origin_time > linked_time:
        return None
    if kind == "order_block" and metadata.get("causal_link_method") != "explicit_break_departure_trace":
        return None
    if kind == "fvg" and not (
        metadata.get("causal_link_method") == "break_source_candle_overlap"
        and evidence.get("location_context") == "causal_impulse_overlap"
    ):
        return None
    base = {
        "poi_id": poi_id,
        "source_object_id": source_id,
        "timeframe": timeframe,
        "direction": direction,
        "kind": kind,
        "price_low": _number(lifecycle.get("price_low")),
        "price_high": _number(lifecycle.get("price_high")),
        "freshness": str(lifecycle.get("freshness") or "unknown"),
        "price_relation": str(lifecycle.get("price_relation") or "unknown"),
        "validity_status": lifecycle.get("validity_status"),
        "scope": lifecycle.get("scope"),
        "linked_break_id": linked_break_id,
        "linked_break_ids": [item["linked_break_id"] for item in _candidate_lineages(raw)],
        "linked_break_scope": _scope(linked),
        "linked_break_type": str(linked.get("break_type") or ""),
        "linked_break_time": linked.get("confirmed_at"),
        "originating_fvg_id": evidence.get("originating_fvg_id"),
        "departure_body_ratio": _number(evidence.get("body_ratio")),
        "source_candle_ids": list(raw.get("source_candle_ids") or []),
        "origin_time": raw.get("pivot_time"),
        "confirmation_time": raw.get("confirmed_at"),
        "origin_cluster_candle_ids": list(metadata.get("origin_cluster_candle_ids") or []),
        "departure_candle_ids": list(lineage.get("departure_candle_ids") or metadata.get("departure_candle_ids") or []),
        "causal_link_method": metadata.get("causal_link_method"),
        "origin_geometry": metadata.get("origin_geometry"),
        "lineage_role": "parent_scope_refinement_origin",
        "range_location": "parent_scope",
        "range_relationship": "child_object_outside_local_range_but_inside_parent_primary",
        "range_location_aligned": True,
        "poi_role": "execution_refinement_candidate",
        "causal_status": "PARENT_SCOPE_REFINEMENT_CANDIDATE",
        "causal_failures": [],
    }
    base["causal_certificate"] = _causal_certificate(
        accepted=None,
        linked=linked,
        base=base,
        owns_latest=False,
        no_opposing_external_break=True,
        range_relationship=str(base["range_relationship"]),
        certificate_role="execution_refinement_only",
    )
    return base


def _build_direction_scenario(
    *, direction: str, timeframe_results: Mapping[str, Any], active_range: Mapping[str, Any],
) -> dict[str, Any]:
    range_tf = str(active_range.get("timeframe") or "") if active_range.get("status") == "RESOLVED" else ""
    preference = tuple(dict.fromkeys((range_tf, *POI_TIMEFRAME_PREFERENCE)))
    selected_tf = next((
        timeframe for timeframe in preference
        if timeframe
        and (timeframe_results.get(timeframe) or {}).get("direction") == direction
        and (timeframe_results.get(timeframe) or {}).get("status") == "SELECTED"
    ), None)
    if selected_tf is None:
        return {
            "status": "UNRESOLVED",
            "direction": direction,
            "controlling_timeframe": None,
            "primary_causal_poi": None,
            "reason": "No timeframe has an eligible causal POI.",
        }
    selected = timeframe_results[selected_tf]
    primary = selected["primary_causal_poi"]
    refinements = _execution_refinements(
        primary=primary,
        controlling_timeframe=selected_tf,
        direction=direction,
        timeframe_results=timeframe_results,
    )
    return {
        "status": "SELECTED",
        "direction": direction,
        "controlling_timeframe": selected_tf,
        "active_range_timeframe": range_tf or None,
        "accepted_break_id": selected.get("accepted_break_id"),
        "primary_causal_poi": primary,
        "secondary_reaction_pois": selected.get("secondary_reaction_pois", []),
        "execution_refinements": refinements,
        "refinement_confluence": _refinement_confluence(primary, refinements),
        "inducement_candidates": _inducement_hypotheses(
            primary=primary,
            direction=direction,
            timeframe_results=timeframe_results,
        ),
        "selection_rule": "eligibility_then_pairwise_causal_lineage",
    }


def _execution_refinements(
    *, primary: Mapping[str, Any], controlling_timeframe: str, direction: str, timeframe_results: Mapping[str, Any],
) -> list[dict[str, Any]]:
    owner_index = list(TIMEFRAMES).index(controlling_timeframe)
    refinements: list[dict[str, Any]] = []
    for timeframe in TIMEFRAMES[owner_index + 1:]:
        result = timeframe_results.get(timeframe) or {}
        objects = []
        if result.get("direction") == direction:
            if isinstance(result.get("primary_causal_poi"), Mapping):
                objects.append(result["primary_causal_poi"])
            objects.extend(result.get("secondary_reaction_pois") or [])
            objects.extend(result.get("internal_reaction_candidates") or [])
        objects.extend(result.get("parent_scope_candidates") or [])
        for candidate in objects:
            if (
                candidate.get("direction") == direction
                and _overlap(primary, candidate)
                and _within_parent_causal_episode(primary, candidate)
            ):
                item = dict(candidate)
                item["poi_role"] = "execution_refinement"
                item["parent_primary_poi_id"] = primary.get("poi_id")
                item["overlap_low"] = max(
                    _number(primary.get("price_low")) or float("-inf"),
                    _number(candidate.get("price_low")) or float("-inf"),
                )
                item["overlap_high"] = min(
                    _number(primary.get("price_high")) or float("inf"),
                    _number(candidate.get("price_high")) or float("inf"),
                )
                refinements.append(item)
    unique: dict[str, dict[str, Any]] = {}
    for item in refinements:
        unique.setdefault(str(item.get("poi_id") or item.get("source_object_id") or ""), item)
    ranked = list(unique.values())
    ranked.sort(
        key=lambda item: (
            item.get("kind") != "order_block",
            -_lifecycle_rank(item),
            -_timeframe_depth(str(item.get("timeframe") or "")),
            _zone_width(item),
            str(item.get("poi_id") or ""),
        )
    )
    return ranked


def _refinement_confluence(
    primary: Mapping[str, Any], refinements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the strict overlap of the best OB refinement on each child TF."""
    by_timeframe: dict[str, Mapping[str, Any]] = {}
    for item in refinements:
        if item.get("kind") != "order_block":
            continue
        timeframe = str(item.get("timeframe") or "")
        by_timeframe.setdefault(timeframe, item)
    if not by_timeframe:
        return None
    components = [primary, *by_timeframe.values()]
    lows = [_number(item.get("price_low")) for item in components]
    highs = [_number(item.get("price_high")) for item in components]
    if any(value is None for value in [*lows, *highs]):
        return None
    low = max(value for value in lows if value is not None)
    high = min(value for value in highs if value is not None)
    if low > high:
        return None
    return {
        "schema": "causal_poi_refinement_confluence_v1",
        "status": "CERTIFIED_GEOMETRIC_OVERLAP",
        "price_low": low,
        "price_high": high,
        "primary_poi_id": primary.get("poi_id"),
        "component_poi_ids": [str(item.get("poi_id") or "") for item in by_timeframe.values()],
        "timeframes": list(by_timeframe),
        "reaction_guaranteed": False,
        "note": "Exact overlap of causally traced child OB refinements; execution still requires a new lower-timeframe trigger.",
    }


def _inducement_hypotheses(
    *, primary: Mapping[str, Any], direction: str, timeframe_results: Mapping[str, Any],
) -> list[dict[str, Any]]:
    primary_mid = _mid(primary)
    if primary_mid is None:
        return []
    out: list[dict[str, Any]] = []
    for result in timeframe_results.values():
        objects = []
        if isinstance(result.get("primary_causal_poi"), Mapping):
            objects.append(result["primary_causal_poi"])
        objects.extend(result.get("secondary_reaction_pois") or [])
        for candidate in objects:
            if candidate.get("poi_id") == primary.get("poi_id") or _overlap(primary, candidate):
                continue
            midpoint = _mid(candidate)
            if midpoint is None:
                continue
            shallower = midpoint < primary_mid if direction == "bearish" else midpoint > primary_mid
            if shallower:
                item = dict(candidate)
                item["poi_role"] = "shallow_inducement_candidate"
                item["hypothesis_status"] = "UNCONFIRMED"
                item["deeper_primary_poi_id"] = primary.get("poi_id")
                out.append(item)
    return out


def _pairwise_key(candidate: Mapping[str, Any], direction: str) -> tuple[Any, ...]:
    lineage_role = {
        "protected_reversal_origin": 3,
        "latest_external_continuation_origin": 2,
        "prior_unbroken_lineage_origin": 1,
    }.get(str(candidate.get("lineage_role")), 0)
    scope = 2 if candidate.get("linked_break_scope") == "external" else 1
    range_alignment = 1 if candidate.get("range_location_aligned") else 0
    displacement = _number(candidate.get("linked_break_displacement_strength")) or 0.0
    lifecycle = _lifecycle_rank(candidate)
    body = _number(candidate.get("departure_body_ratio")) or 0.0
    fvg_support = 1 if candidate.get("originating_fvg_id") else 0
    linked_time = _time(candidate.get("linked_break_time")) or datetime.min
    midpoint = _mid(candidate) or 0.0
    depth = midpoint if direction == "bearish" else -midpoint
    return lineage_role, scope, range_alignment, displacement, lifecycle, body, fvg_support, linked_time, depth, str(candidate.get("poi_id"))


def _comparison_reasons(winner: Mapping[str, Any], loser: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if winner.get("lineage_role") != loser.get("lineage_role"):
        reasons.append("winner_has_stronger_causal_lineage_role")
    if winner.get("linked_break_scope") != loser.get("linked_break_scope"):
        reasons.append("winner_has_stronger_structure_scope")
    if winner.get("range_location_aligned") != loser.get("range_location_aligned"):
        reasons.append("winner_has_better_active_range_location")
    if _lifecycle_rank(winner) != _lifecycle_rank(loser):
        reasons.append("winner_has_better_lifecycle")
    if winner.get("kind") == "order_block" and loser.get("kind") == "fvg":
        reasons.append("fvg_is_supporting_unless_no_causal_ob_exists")
    if not reasons:
        reasons.append("depth_used_only_after_causal_structure_and_lifecycle_tie")
    return reasons


def _raw_poi_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for group in ("order_blocks", "fvgs", "poi_grade_fvgs"):
        for item in _objects(payload.get(group)):
            object_id = str(item.get("object_id") or "")
            if object_id:
                out[object_id] = _merge_raw_poi_records(out.get(object_id), item)
    return out


def _merge_raw_poi_records(
    existing: Mapping[str, Any] | None, incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge duplicate geometry while retaining every explicit break lineage."""
    if not isinstance(existing, Mapping):
        result = dict(incoming)
        metadata = dict(result.get("metadata") or {})
        metadata["causal_lineages"] = _candidate_lineages(result)
        result["metadata"] = metadata
        return result
    result = dict(existing)
    metadata = dict(result.get("metadata") or {})
    lineages = _dedupe_lineages([*_candidate_lineages(existing), *_candidate_lineages(incoming)])
    metadata["causal_lineages"] = lineages
    result["metadata"] = metadata
    result["source_candle_ids"] = list(dict.fromkeys([
        *list(existing.get("source_candle_ids") or []),
        *list(incoming.get("source_candle_ids") or []),
    ]))
    return result


def _candidate_lineages(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = raw.get("evidence") or {}
    metadata = raw.get("metadata") or {}
    lineages = [dict(item) for item in (metadata.get("causal_lineages") or []) if isinstance(item, Mapping)]
    fallback_id = str(
        evidence.get("structure_break_id")
        or evidence.get("origin_break_id")
        or metadata.get("linked_break_id")
        or ""
    )
    if fallback_id:
        lineages.append({
            "linked_break_id": fallback_id,
            "departure_candle_ids": list(metadata.get("departure_candle_ids") or []),
        })
    return _dedupe_lineages(lineages)


def _dedupe_lineages(lineages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for raw in lineages:
        break_id = str(raw.get("linked_break_id") or "")
        if not break_id:
            continue
        item = dict(raw)
        item["linked_break_id"] = break_id
        if break_id in unique:
            unique[break_id]["departure_candle_ids"] = list(dict.fromkeys([
                *list(unique[break_id].get("departure_candle_ids") or []),
                *list(item.get("departure_candle_ids") or []),
            ]))
        else:
            unique[break_id] = item
    return list(unique.values())


def _select_causal_lineage(
    *,
    raw: Mapping[str, Any],
    break_index: Mapping[str, Mapping[str, Any]],
    direction: str,
    accepted_break_id: str | None,
) -> dict[str, Any] | None:
    candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for lineage in _candidate_lineages(raw):
        break_id = str(lineage.get("linked_break_id") or "")
        linked = break_index.get(break_id)
        if not isinstance(linked, Mapping) or str(linked.get("direction") or "") != direction:
            continue
        evidence = linked.get("evidence") or {}
        scope = _scope(linked)
        confirmed = _time(linked.get("confirmed_at")) or datetime.min
        priority = (
            1 if accepted_break_id and break_id == accepted_break_id else 0,
            1 if bool(evidence.get("broke_protected_swing")) and bool(evidence.get("valid_choch")) else 0,
            1 if scope == "external" else 0,
            1 if str(linked.get("break_type") or "") == "CHOCH" else 0,
            confirmed,
            break_id,
        )
        candidates.append((priority, {**lineage, "linked_break_id": break_id}))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _source_object_id(poi_id: str) -> str:
    for marker in (":order_block:", ":fvg:"):
        if marker in poi_id:
            return poi_id.split(marker, 1)[1]
    return poi_id


def _lifecycle_eligible(candidate: Mapping[str, Any]) -> bool:
    freshness = str(candidate.get("freshness") or "").lower()
    relation = str(candidate.get("price_relation") or "").lower()
    return (
        candidate.get("validity_status") == "VALID_ACTIVE_SETUP_POI"
        and candidate.get("scope") == "active_setup"
        and freshness not in {"invalidated", "full", "consumed", "terminal"}
        and not relation.startswith("invalidated")
    )


def _accepted_external_origin_survives_nested_range_reclassification(
    *,
    lifecycle: Mapping[str, Any],
    raw: Mapping[str, Any],
    accepted: Mapping[str, Any],
    direction: str,
) -> bool:
    """Retain an exact external-break origin as scenario authority only.

    The lifecycle classifier answers whether a POI is usable inside the
    *current* protected range.  A later nested range can therefore classify
    the historical origin of an already accepted external break as straddling
    that newer boundary.  That must deny active-entry authority, but it must
    not erase the causal origin from the structural story.

    The exception is intentionally narrow: an unspent admitted OB must own the
    exact accepted external break through an explicit departure trace.  Mere
    geometric overlap, an older lineage, or a spent zone remains rejected.
    """
    freshness = str(lifecycle.get("freshness") or "").lower()
    relation = str(lifecycle.get("price_relation") or "").lower()
    if (
        lifecycle.get("validity_status") != "REVIEW_REQUIRED_STRADDLES_PROTECTED_LEVEL"
        or lifecycle.get("scope") != "rejected"
        or freshness in {"invalidated", "full", "consumed", "terminal"}
        or relation.startswith("invalidated")
    ):
        return False
    evidence = raw.get("evidence") or {}
    metadata = raw.get("metadata") or {}
    admission = metadata.get("causal_origin_admission")
    admission = admission if isinstance(admission, Mapping) else {}
    accepted_id = str(accepted.get("object_id") or "")
    linked_id = str(metadata.get("linked_break_id") or evidence.get("structure_break_id") or "")
    return bool(
        accepted_id
        and linked_id == accepted_id
        and str(raw.get("direction") or "") == direction
        and str(accepted.get("direction") or "") == direction
        and _scope(accepted) == "external"
        and metadata.get("causal_link_method") == "explicit_break_departure_trace"
        and admission.get("admitted") is True
        and evidence.get("poi_grade") is True
    )


def _candidate_lifecycle_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one lifecycle record per POI, including graph-opposing watch objects.

    Older packs exposed only ``active_pois``. Canonical packs also expose all
    mapped ``pois``. Prefer the active record when both exist, but retain an
    object rejected solely by the provisional hierarchy direction so the later
    formal graph can adjudicate it instead of losing it permanently.
    """
    records: dict[str, dict[str, Any]] = {}
    for group in (payload.get("pois"), payload.get("active_pois")):
        for item in _objects(group):
            poi_id = str(item.get("poi_id") or item.get("object_id") or "")
            if poi_id:
                records[poi_id] = item
    return list(records.values())


def _reconcile_lifecycle_to_formal_direction(
    candidate: Mapping[str, Any], formal_direction: str,
) -> dict[str, Any]:
    """Let the formal graph supersede only a stale direction-mismatch rejection."""
    item = dict(candidate)
    if (
        str(item.get("direction") or "") == formal_direction
        and item.get("validity_status") == "INVALID_DIRECTION_MISMATCH"
        and item.get("scope") == "rejected"
    ):
        item["legacy_validity_status"] = item.get("validity_status")
        item["legacy_scope"] = item.get("scope")
        item["validity_status"] = "VALID_ACTIVE_SETUP_POI"
        item["scope"] = "active_setup"
        item["authority_reconciliation"] = "formal_graph_direction_supersedes_provisional_hierarchy_bias"
        item["rejection_reason"] = None
    return item


def _parent_scope_eligible(candidate: Mapping[str, Any]) -> bool:
    freshness = str(candidate.get("freshness") or "").lower()
    relation = str(candidate.get("price_relation") or "").lower()
    return (
        candidate.get("validity_status") == "PARENT_SCOPE_POI"
        and candidate.get("scope") == "parent_scope"
        and freshness not in {"invalidated", "full", "consumed", "terminal"}
        and not relation.startswith("invalidated")
    )


def _lifecycle_rank(candidate: Mapping[str, Any]) -> int:
    return LIFECYCLE_ORDER.get(str(candidate.get("freshness") or "").lower(), 1)


def _scope(item: Mapping[str, Any]) -> str:
    evidence = item.get("evidence") or {}
    return str(item.get("structure_scope") or evidence.get("structure_scope") or ("internal" if evidence.get("is_internal") else "external"))


def _objects(raw: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (raw or []) if isinstance(item, Mapping)]


def _time(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _number(raw: Any) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _mid(candidate: Mapping[str, Any]) -> float | None:
    low = _number(candidate.get("price_low"))
    high = _number(candidate.get("price_high"))
    return None if low is None or high is None else (low + high) / 2.0


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    ll, lh = _number(left.get("price_low")), _number(left.get("price_high"))
    rl, rh = _number(right.get("price_low")), _number(right.get("price_high"))
    if None in {ll, lh, rl, rh}:
        return False
    return max(ll, rl) <= min(lh, rh)  # type: ignore[arg-type]


def _range_location(candidate: Mapping[str, Any], active_range: Mapping[str, Any]) -> str:
    midpoint = _mid(candidate)
    low = _number(active_range.get("low"))
    high = _number(active_range.get("high"))
    equilibrium = _number(active_range.get("equilibrium"))
    if active_range.get("status") != "RESOLVED" or None in {midpoint, low, high, equilibrium}:
        return "unknown"
    assert midpoint is not None and low is not None and high is not None and equilibrium is not None
    if midpoint < low:
        return "outside_below"
    if midpoint > high:
        return "outside_above"
    tolerance = max((high - low) * 0.02, 1e-12)
    if abs(midpoint - equilibrium) <= tolerance:
        return "equilibrium"
    return "discount" if midpoint < equilibrium else "premium"


def _range_location_aligned(location: str, direction: str) -> bool:
    return (direction == "bullish" and location == "discount") or (direction == "bearish" and location == "premium")


def _outside_range_parent_origin_allowed(
    *,
    range_location: str,
    direction: str,
    linked_scope: str,
    owns_latest: bool,
    broke_protected: bool,
    valid_choch: bool,
) -> bool:
    directional_parent_side = (
        direction == "bullish" and range_location == "outside_below"
    ) or (
        direction == "bearish" and range_location == "outside_above"
    )
    strong_external_lineage = linked_scope == "external" and (
        owns_latest or (broke_protected and valid_choch)
    )
    return directional_parent_side and strong_external_lineage


def _causal_certificate(
    *,
    accepted: Mapping[str, Any] | None,
    linked: Mapping[str, Any],
    base: Mapping[str, Any],
    owns_latest: bool,
    no_opposing_external_break: bool,
    range_relationship: str,
    certificate_role: str,
) -> dict[str, Any]:
    origin_ids = list(base.get("origin_cluster_candle_ids") or [])
    departure_ids = list(base.get("departure_candle_ids") or [])
    linked_scope = _scope(linked)
    checks = [
        {"code": "explicit_break_link", "passed": bool(base.get("linked_break_id"))},
        {
            "code": "origin_cluster_present",
            "passed": bool(origin_ids) or (base.get("kind") == "fvg" and bool(base.get("source_candle_ids"))),
        },
        {"code": "departure_trace_present", "passed": bool(departure_ids) or base.get("kind") == "fvg"},
        {"code": "linked_direction_matches", "passed": str(linked.get("direction") or "") == base.get("direction")},
        {
            "code": "origin_precedes_linked_break",
            "passed": (
                _time(base.get("origin_time")) is not None
                and _time(linked.get("confirmed_at")) is not None
                and _time(base.get("origin_time")) <= _time(linked.get("confirmed_at"))
            ),
        },
        {"code": "no_opposing_external_supersession", "passed": no_opposing_external_break},
        {
            "code": "primary_requires_external_scope",
            "passed": linked_scope == "external" if certificate_role == "primary_eligibility" else True,
        },
    ]
    return {
        "schema": "causal_poi_certificate_v1",
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "certificate_role": certificate_role,
        "accepted_external_break_id": None if accepted is None else accepted.get("object_id"),
        "selected_linked_break_id": base.get("linked_break_id"),
        "linked_break_scope": linked_scope,
        "owns_accepted_external_break": owns_latest,
        "origin_cluster_candle_ids": origin_ids,
        "departure_candle_ids": departure_ids,
        "range_relationship": range_relationship,
        "checks": checks,
        "reaction_guaranteed": False,
        "certainty_definition": "deterministic_classification_and_lineage_not_future_reaction",
    }


def _timeframe_depth(timeframe: str) -> int:
    try:
        return TIMEFRAMES.index(timeframe)
    except ValueError:
        return -1


def _zone_width(candidate: Mapping[str, Any]) -> float:
    low = _number(candidate.get("price_low"))
    high = _number(candidate.get("price_high"))
    return float("inf") if low is None or high is None else max(0.0, high - low)


def _within_parent_causal_episode(
    primary: Mapping[str, Any], candidate: Mapping[str, Any],
) -> bool:
    """Require child refinement origin inside the parent origin-to-break episode."""
    parent_origin = _time(primary.get("origin_time"))
    parent_break = _time(primary.get("linked_break_time"))
    child_origin = _time(candidate.get("origin_time"))
    if parent_origin is None or parent_break is None or child_origin is None:
        return False
    return parent_origin <= child_origin <= parent_break


def _empty_timeframe(timeframe: str, direction: str, reason: str, *, accepted_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "UNRESOLVED",
        "timeframe": timeframe,
        "direction": direction,
        "accepted_break_id": accepted_id,
        "primary_causal_poi": None,
        "secondary_reaction_pois": [],
        "unresolved_candidates": [],
        "rejected_candidates": [],
        "internal_reaction_candidates": [],
        "parent_scope_candidates": [],
        "reason": reason,
    }


__all__ = ["build_causal_poi_authority"]
