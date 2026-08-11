"""Fail-closed authority for material, non-controlling chart context.

Active POI selection and chart completeness answer different questions.  A
zone can correctly lose *entry* authority after an opposing external break and
still remain material supply/demand that a professional trader would retain on
the chart.  This module keeps those concepts separate:

* causal_poi_authority remains the only active-entry selector;
* only detector objects tied to V3-accepted structure may enter this atlas;
* an AI exception can change display visibility to ``context_only`` and
  nothing else;
* every material object is named so renderers can prove that it was drawn or
  explicitly account for its omission.

The output is descriptive and observe-only.  It never supplies entries, stops,
targets, bias overrides, paper authority, or live authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


TIMEFRAME_ORDER = ("1d", "4h", "1h", "15m", "5m")
TIMEFRAME_RANK = {timeframe: index for index, timeframe in enumerate(TIMEFRAME_ORDER)}
ACTIVE_MITIGATION = {"", "fresh", "untouched", "partial", "partially_mitigated"}


def build_annotation_context_authority(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bounded context atlas and its mandatory coverage contract."""
    graph = evidence_pack.get("formal_causal_episode_graph") or {}
    graph_timeframes = graph.get("timeframes") if isinstance(graph, Mapping) else {}
    detector = evidence_pack.get("detector_candidates") or {}
    candidates, by_id = _candidate_indexes(detector)
    accepted_by_tf, _accepted_ids = _accepted_episode_indexes(graph_timeframes)

    requirements: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    seen_requirement_ids: set[str] = set()

    for timeframe in TIMEFRAME_ORDER:
        # When a higher-timeframe material cluster already supplied a causal
        # refinement on this chart, do not add a second unrelated historical
        # cluster merely because it also passed detection. The refinement is
        # the cleaner trader-facing explanation of the parent zone.
        if any(
            str(item.get("timeframe") or "") == timeframe
            and str(item.get("display_role") or "") == "context_refinement"
            for item in requirements
        ):
            continue
        node = graph_timeframes.get(timeframe) if isinstance(graph_timeframes, Mapping) else None
        if not isinstance(node, Mapping):
            continue
        latest = node.get("latest_external_episode")
        if not isinstance(latest, Mapping):
            continue
        latest_id = str(latest.get("structure_event_id") or "")
        latest_direction = str(latest.get("direction") or "").lower()
        external_episodes = [
            episode
            for episode in (node.get("episodes") or [])
            if isinstance(episode, Mapping)
            and str(episode.get("scope") or "") == "external"
            and str(episode.get("structure_event_id") or "") != latest_id
            and str(episode.get("direction") or "").lower() in {"bullish", "bearish"}
        ]
        external_episodes.sort(key=lambda item: _time(item.get("confirmation_time")) or datetime.min.replace(tzinfo=timezone.utc))

        # One latest material opposing cluster per native timeframe keeps the
        # chart sparse while preventing a real supply/demand episode from being
        # erased merely because a later external event became controlling.
        selected_episode: Mapping[str, Any] | None = None
        selected_ob: Mapping[str, Any] | None = None
        selected_fvg: Mapping[str, Any] | None = None
        for episode in reversed(external_episodes):
            direction = str(episode.get("direction") or "").lower()
            if latest_direction in {"bullish", "bearish"} and direction == latest_direction:
                continue
            break_id = str(episode.get("structure_event_id") or "")
            linked = [
                item
                for item in candidates.get(timeframe, [])
                if _linked_break_id(item) == break_id
                and str(item.get("direction") or "").lower() == direction
            ]
            order_blocks = [item for item in linked if _context_eligible_ob(item)]
            fvgs = [item for item in linked if _context_eligible_fvg(item)]
            if not order_blocks and not fvgs:
                continue
            selected_episode = episode
            selected_ob = max(order_blocks, key=_poi_selection_key, default=None)
            selected_fvg = max(
                [item for item in fvgs if selected_ob is None or _zones_overlap(item, selected_ob)],
                key=_poi_selection_key,
                default=None,
            )
            if selected_fvg is None:
                selected_fvg = max(fvgs, key=_poi_selection_key, default=None)
            break

        if selected_episode is None:
            continue

        break_id = str(selected_episode.get("structure_event_id") or "")
        direction = str(selected_episode.get("direction") or "").lower()
        cluster_id = f"context_cluster:{timeframe}:{break_id}"
        cluster_requirement_ids: list[str] = []

        break_candidate = by_id.get(break_id)
        if break_candidate is not None:
            requirement = _requirement(
                candidate=break_candidate,
                display_role="superseded_context_structure",
                control_status="superseded_by_later_opposing_external_episode",
                source_break_id=break_id,
                parent_cluster_id=cluster_id,
                reason="V3-accepted external break that created the still-material contextual zone.",
                priority=1,
            )
            _append_requirement(requirements, requirement, seen_requirement_ids)
            cluster_requirement_ids.append(requirement["requirement_id"])

        for candidate, role, reason, priority in (
            (
                selected_ob,
                "superseded_context_poi",
                "Causal OB owns an accepted historical external break but cannot control entry after the later opposing external episode.",
                1,
            ),
            (
                selected_fvg,
                "superseded_context_imbalance",
                "Causal-impulse FVG supports the accepted historical break and remains chart context only.",
                2,
            ),
        ):
            if candidate is None:
                continue
            requirement = _requirement(
                candidate=candidate,
                display_role=role,
                control_status="superseded_by_later_opposing_external_episode",
                source_break_id=break_id,
                parent_cluster_id=cluster_id,
                reason=reason,
                priority=priority,
            )
            _append_requirement(requirements, requirement, seen_requirement_ids)
            cluster_requirement_ids.append(requirement["requirement_id"])

        parent_zone = selected_ob or selected_fvg
        refinement = _select_causal_refinement(
            parent_timeframe=timeframe,
            parent_zone=parent_zone,
            parent_episode=selected_episode,
            direction=direction,
            candidates=candidates,
            accepted_by_tf=accepted_by_tf,
        )
        if refinement is not None:
            refinement_candidate, refinement_break = refinement
            requirement = _requirement(
                candidate=refinement_candidate,
                display_role="context_refinement",
                control_status="subordinate_refinement_of_superseded_parent",
                source_break_id=str(refinement_break.get("structure_event_id") or ""),
                parent_cluster_id=cluster_id,
                reason="Lower-timeframe admitted departure origin refines the parent contextual zone without inheriting entry authority.",
                priority=1,
            )
            _append_requirement(requirements, requirement, seen_requirement_ids)
            cluster_requirement_ids.append(requirement["requirement_id"])
            refinement_break_candidate = by_id.get(str(refinement_break.get("structure_event_id") or ""))
            if refinement_break_candidate is not None:
                refinement_structure = _requirement(
                    candidate=refinement_break_candidate,
                    display_role="context_refinement_structure",
                    control_status="subordinate_refinement_of_superseded_parent",
                    source_break_id=str(refinement_break.get("structure_event_id") or ""),
                    parent_cluster_id=cluster_id,
                    reason="Accepted lower-timeframe break proving the selected contextual refinement.",
                    priority=2,
                )
                _append_requirement(requirements, refinement_structure, seen_requirement_ids)
                cluster_requirement_ids.append(refinement_structure["requirement_id"])

            omissions.extend(
                _geometric_refinement_omissions(
                    selected=refinement_candidate,
                    parent_zone=parent_zone,
                    parent_episode=selected_episode,
                    direction=direction,
                    timeframe=str(refinement_candidate.get("timeframe") or ""),
                    candidates=candidates,
                    cluster_id=cluster_id,
                )
            )

        clusters.append(
            {
                "cluster_id": cluster_id,
                "timeframe": timeframe,
                "direction": direction,
                "source_break_id": break_id,
                "superseding_break_id": latest_id,
                "superseding_direction": latest_direction,
                "requirement_ids": cluster_requirement_ids,
                "active_entry_authority": False,
                "display_role": "material_historical_context",
            }
        )

    selected_by_timeframe: dict[str, list[str]] = {}
    for requirement in requirements:
        selected_by_timeframe.setdefault(str(requirement["timeframe"]), []).append(str(requirement["object_id"]))

    earliest_required: dict[str, str] = {}
    for requirement in requirements:
        timeframe = str(requirement["timeframe"])
        value = str(requirement.get("required_start_time") or "")
        if not value:
            continue
        current = earliest_required.get(timeframe)
        if current is None or (_time(value) or datetime.max.replace(tzinfo=timezone.utc)) < (_time(current) or datetime.max.replace(tzinfo=timezone.utc)):
            earliest_required[timeframe] = value

    return {
        "schema": "annotation_context_authority_v1",
        "status": "MATERIAL_CONTEXT_FOUND" if requirements else "NO_MATERIAL_SUPERSEDED_CONTEXT",
        "clusters": clusters,
        "requirements": requirements,
        "selected_evidence_ids": selected_by_timeframe,
        "omission_ledger": omissions,
        "window_requirements": {
            "earliest_required_time_by_timeframe": earliest_required,
            "maximum_context_rows_per_timeframe": 720,
            "pre_anchor_padding_bars": 8,
        },
        "contextual_exception_policy": {
            "allowed_transition": "entry_rejected_to_context_only_display",
            "requires_prequalified_requirement_id": True,
            "requires_v3_accepted_source_break": True,
            "requires_exact_sealed_geometry": True,
            "ai_may_request_visibility": True,
            "ai_may_create_or_move_zone": False,
            "ai_may_change_bias": False,
            "ai_may_grant_active_entry_authority": False,
            "ai_may_add_entry_stop_target_or_trade_box": False,
        },
        "authority_contract": {
            "observe_only": True,
            "active_poi_selector": False,
            "active_entry_authority": False,
            "bias_override_authority": False,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }


def validate_context_exception_requests(
    requests: Sequence[Mapping[str, Any]] | None,
    context_authority: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate AI requests against the deterministic, sealed context atlas."""
    authority = context_authority if isinstance(context_authority, Mapping) else {}
    requirement_index = {
        str(item.get("requirement_id") or ""): item
        for item in authority.get("requirements", []) or []
        if isinstance(item, Mapping) and item.get("requirement_id")
    }
    issues: list[dict[str, str]] = []
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in requests or []:
        if not isinstance(raw, Mapping):
            issues.append({"code": "context_exception_request_not_object", "message": "Each context exception request must be an object."})
            continue
        request_id = str(raw.get("request_id") or "")
        requirement_id = str(raw.get("requirement_id") or "")
        requirement = requirement_index.get(requirement_id)
        if not request_id or request_id in seen:
            issues.append({"code": "context_exception_request_id_invalid", "message": "Context exception request IDs must be non-empty and unique."})
            continue
        seen.add(request_id)
        if requirement is None:
            issues.append({"code": "context_exception_not_prequalified", "message": f"{request_id} does not cite a prequalified context requirement."})
            continue
        expected_ids = [str(requirement.get("object_id") or "")]
        actual_ids = [str(value) for value in raw.get("evidence_object_ids", []) or []]
        if actual_ids != expected_ids:
            issues.append({"code": "context_exception_evidence_mismatch", "message": f"{request_id} does not cite the exact sealed evidence object."})
            continue
        if raw.get("requested_display_role") != "context_only":
            issues.append({"code": "context_exception_role_forbidden", "message": f"{request_id} may request context_only display and nothing else."})
            continue
        if raw.get("acknowledges_no_entry_authority") is not True or raw.get("acknowledges_no_bias_override") is not True:
            issues.append({"code": "context_exception_authority_acknowledgement_missing", "message": f"{request_id} must preserve entry and bias authority boundaries."})
            continue
        if not str(raw.get("rationale") or "").strip():
            issues.append({"code": "context_exception_rationale_missing", "message": f"{request_id} requires a concise evidence-based rationale."})
            continue
        accepted.append(
            {
                "request_id": request_id,
                "requirement_id": requirement_id,
                "object_id": expected_ids[0],
                "status": "AI_CONTEXT_DISPLAY_EXCEPTION_ACCEPTED",
                "display_role": "context_only",
                "active_entry_authority": False,
                "bias_override_authority": False,
            }
        )
    return {
        "schema": "annotation_context_exception_validation_v1",
        "status": "PASS" if not issues else "REVIEW_REQUIRED",
        "accepted_requests": accepted,
        "issues": issues,
        "authority_contract": {
            "display_visibility_only": True,
            "active_entry_authority": False,
            "bias_override_authority": False,
        },
    }


def _candidate_indexes(detector: Any) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, Mapping[str, Any]]]:
    by_timeframe: dict[str, list[Mapping[str, Any]]] = {}
    by_id: dict[str, Mapping[str, Any]] = {}
    if not isinstance(detector, Mapping):
        return by_timeframe, by_id
    for timeframe, payload in detector.items():
        if not isinstance(payload, Mapping):
            continue
        bucket: list[Mapping[str, Any]] = []
        for values in payload.values():
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, Mapping):
                    continue
                object_id = str(item.get("object_id") or item.get("id") or "")
                if not object_id:
                    continue
                by_id.setdefault(object_id, item)
                if item not in bucket:
                    bucket.append(item)
        by_timeframe[str(timeframe)] = bucket
    return by_timeframe, by_id


def _accepted_episode_indexes(graph_timeframes: Any) -> tuple[dict[str, dict[str, Mapping[str, Any]]], set[str]]:
    by_timeframe: dict[str, dict[str, Mapping[str, Any]]] = {}
    accepted_ids: set[str] = set()
    if not isinstance(graph_timeframes, Mapping):
        return by_timeframe, accepted_ids
    for timeframe, node in graph_timeframes.items():
        if not isinstance(node, Mapping):
            continue
        items: dict[str, Mapping[str, Any]] = {}
        for episode in node.get("episodes", []) or []:
            if not isinstance(episode, Mapping):
                continue
            object_id = str(episode.get("structure_event_id") or "")
            if object_id:
                items[object_id] = episode
                accepted_ids.add(object_id)
        by_timeframe[str(timeframe)] = items
    return by_timeframe, accepted_ids


def _select_causal_refinement(
    *,
    parent_timeframe: str,
    parent_zone: Mapping[str, Any] | None,
    parent_episode: Mapping[str, Any],
    direction: str,
    candidates: Mapping[str, list[Mapping[str, Any]]],
    accepted_by_tf: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    if parent_zone is None or parent_timeframe not in TIMEFRAME_RANK:
        return None
    parent_rank = TIMEFRAME_RANK[parent_timeframe]
    origin = _time(parent_zone.get("pivot_time") or parent_zone.get("candidate_at"))
    confirmation = _time(parent_episode.get("confirmation_time"))
    for timeframe in TIMEFRAME_ORDER[parent_rank + 1 :]:
        eligible: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        accepted = accepted_by_tf.get(timeframe, {})
        for item in candidates.get(timeframe, []):
            if not _context_eligible_ob(item):
                continue
            if str(item.get("direction") or "").lower() != direction or not _zones_overlap(item, parent_zone):
                continue
            item_time = _time(item.get("pivot_time") or item.get("candidate_at"))
            if origin is not None and item_time is not None and item_time < origin:
                continue
            if confirmation is not None and item_time is not None and item_time > confirmation:
                continue
            linked_break = accepted.get(_linked_break_id(item))
            if linked_break is None:
                continue
            eligible.append((item, linked_break))
        if eligible:
            return max(eligible, key=lambda pair: _refinement_selection_key(pair[0], parent_zone))
    return None


def _geometric_refinement_omissions(
    *,
    selected: Mapping[str, Any],
    parent_zone: Mapping[str, Any] | None,
    parent_episode: Mapping[str, Any],
    direction: str,
    timeframe: str,
    candidates: Mapping[str, list[Mapping[str, Any]]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    if parent_zone is None:
        return []
    origin = _time(parent_zone.get("pivot_time") or parent_zone.get("candidate_at"))
    confirmation = _time(parent_episode.get("confirmation_time"))
    omissions: list[dict[str, Any]] = []
    selected_id = str(selected.get("object_id") or "")
    selected_break = _linked_break_id(selected)
    for item in candidates.get(timeframe, []):
        object_id = str(item.get("object_id") or "")
        metadata = item.get("metadata") or {}
        if (
            not object_id
            or object_id == selected_id
            or str(item.get("object_type") or "") != "order_block"
            or str(item.get("direction") or "").lower() != direction
            or _linked_break_id(item) != selected_break
            or not _zones_overlap(item, parent_zone)
            or metadata.get("candidate_authority") != "geometric_visibility_only_no_promotion"
        ):
            continue
        item_time = _time(item.get("pivot_time") or item.get("candidate_at"))
        if origin is not None and item_time is not None and item_time < origin:
            continue
        if confirmation is not None and item_time is not None and item_time > confirmation:
            continue
        omissions.append(
            {
                "object_id": object_id,
                "timeframe": timeframe,
                "parent_cluster_id": cluster_id,
                "status": "OMITTED_WITH_REASON",
                "reason_code": "geometric_visibility_only_not_causal_origin",
                "reason": "A narrower admitted departure origin owns the break; this older geometric base remains in the audit ledger only.",
                "selected_causal_refinement_id": selected_id,
                "active_entry_authority": False,
            }
        )
    return omissions


def _requirement(
    *,
    candidate: Mapping[str, Any],
    display_role: str,
    control_status: str,
    source_break_id: str,
    parent_cluster_id: str,
    reason: str,
    priority: int,
) -> dict[str, Any]:
    object_id = str(candidate.get("object_id") or candidate.get("id") or "")
    timeframe = str(candidate.get("timeframe") or "unknown")
    evidence_type = str(candidate.get("object_type") or "")
    return {
        "requirement_id": f"context_requirement:{timeframe}:{object_id}",
        "object_id": object_id,
        "timeframe": timeframe,
        "evidence_type": evidence_type,
        "display_role": display_role,
        "control_status": control_status,
        "source_break_id": source_break_id,
        "parent_cluster_id": parent_cluster_id,
        "required_render": True,
        "render_priority": priority,
        "required_start_time": candidate.get("pivot_time") or candidate.get("candidate_at"),
        "required_end_time": candidate.get("confirmed_at") or candidate.get("candidate_at") or candidate.get("pivot_time"),
        "price_low": candidate.get("price_low"),
        "price_high": candidate.get("price_high"),
        "reason": reason,
        "ai_context_exception_eligible": True,
        "active_entry_authority": False,
        "bias_override_authority": False,
        "trade_box_allowed": False,
    }


def _append_requirement(
    requirements: list[dict[str, Any]], requirement: dict[str, Any], seen: set[str]
) -> None:
    requirement_id = str(requirement.get("requirement_id") or "")
    if not requirement_id or requirement_id in seen:
        return
    seen.add(requirement_id)
    requirements.append(requirement)


def _linked_break_id(item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    return str(
        metadata.get("linked_break_id")
        or evidence.get("structure_break_id")
        or evidence.get("origin_break_id")
        or ""
    )


def _context_eligible_ob(item: Mapping[str, Any]) -> bool:
    if str(item.get("object_type") or "") != "order_block" or not _active_lifecycle(item):
        return False
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    admission = metadata.get("causal_origin_admission") if isinstance(metadata.get("causal_origin_admission"), Mapping) else {}
    return bool(
        evidence.get("poi_grade") is True
        and evidence.get("caused_structure_break") is True
        and (admission.get("admitted") is True or evidence.get("admission_status") == "departure_produced_displacement_into_accepted_break")
        and metadata.get("causal_link_method") == "explicit_break_departure_trace"
        and _linked_break_id(item)
    )


def _context_eligible_fvg(item: Mapping[str, Any]) -> bool:
    if str(item.get("object_type") or "") != "fvg" or not _active_lifecycle(item):
        return False
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    return bool(
        evidence.get("poi_grade") is True
        and evidence.get("location_context") == "causal_impulse_overlap"
        and metadata.get("causal_link_method") == "break_source_candle_overlap"
        and _linked_break_id(item)
    )


def _active_lifecycle(item: Mapping[str, Any]) -> bool:
    confirmation = str(item.get("confirmation_status") or "").lower()
    activity = str(item.get("activity_status") or "").lower()
    mitigation = str(item.get("mitigation_status") or "").lower()
    terminal_reason = str(item.get("terminal_reason") or "none").lower()
    return bool(
        confirmation == "confirmed"
        and activity != "terminal"
        and mitigation in ACTIVE_MITIGATION
        and terminal_reason in {"", "none"}
    )


def _poi_selection_key(item: Mapping[str, Any]) -> tuple[float, float, float]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    admission = metadata.get("causal_origin_admission") if isinstance(metadata.get("causal_origin_admission"), Mapping) else {}
    freshness = 1.0 if str(item.get("mitigation_status") or "").lower() in {"fresh", "untouched"} else 0.5
    score = _number(admission.get("score")) or _number(item.get("evidence_strength")) or 0.0
    body = _number(evidence.get("body_ratio")) or 0.0
    return freshness, score, body


def _refinement_selection_key(item: Mapping[str, Any], parent: Mapping[str, Any]) -> tuple[float, float, float, float]:
    low, high = _zone(item)
    parent_low, parent_high = _zone(parent)
    contained = float(low is not None and high is not None and parent_low is not None and parent_high is not None and parent_low <= low <= high <= parent_high)
    width = (high - low) if low is not None and high is not None else float("inf")
    freshness, score, body = _poi_selection_key(item)
    return contained, freshness, score + body, -width


def _zones_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_low, left_high = _zone(left)
    right_low, right_high = _zone(right)
    if None in {left_low, left_high, right_low, right_high}:
        return False
    return max(left_low, right_low) <= min(left_high, right_high)


def _zone(item: Mapping[str, Any]) -> tuple[float | None, float | None]:
    low = _number(item.get("price_low"))
    high = _number(item.get("price_high"))
    if low is not None and high is not None and low > high:
        low, high = high, low
    return low, high


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _time(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = [
    "build_annotation_context_authority",
    "validate_context_exception_requests",
]
