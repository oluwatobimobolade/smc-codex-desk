"""Formal causal SMC episode graph V2.

V1 is intentionally retained as the current deterministic guard. V2 adds the
missing temporal story: accepted structure event, broken swing, displacement,
origin POI, inducement/sweep, protected origin, range, and liquidity draw.

V2 is observe-only and downgrade-only. It may expose a contradiction between
the V1 controlling label and the stricter V3 shadow replay, but it cannot
promote a market state or authorize execution.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


TIMEFRAME_ORDER = ("1d", "12h", "4h", "1h", "15m", "5m")


def build_formal_causal_episode_graph(
    *,
    symbol: str,
    decision_time: str,
    detector_candidates: Mapping[str, Any],
    structure_shadow: Mapping[str, Any],
    formal_structure_graph_v1: Mapping[str, Any],
    causal_poi_authority: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    timeframe_episodes: dict[str, Any] = {}
    accepted_ids: set[str] = set()

    shadow_timeframes = structure_shadow.get("timeframes") or {}
    for timeframe in TIMEFRAME_ORDER:
        shadow_tf = shadow_timeframes.get(timeframe) if isinstance(shadow_timeframes, Mapping) else None
        payload = detector_candidates.get(timeframe)
        if not isinstance(shadow_tf, Mapping) or not isinstance(payload, Mapping):
            continue
        events = [
            dict(event)
            for event in shadow_tf.get("events", []) or []
            if isinstance(event, Mapping) and event.get("accepted_for_shadow_story")
        ]
        events.sort(key=_event_time)
        accepted_ids.update(str(event.get("source_break_object_id")) for event in events if event.get("source_break_object_id"))
        candidate_index = _candidate_index(payload)
        episodes = [
            _build_episode(
                timeframe=timeframe,
                event=event,
                candidate_index=candidate_index,
                payload=payload,
                causal_poi_authority=causal_poi_authority,
                nodes=nodes,
                edges=edges,
            )
            for event in events
        ]
        latest_external = _latest_episode(episodes, "external")
        latest_internal = _latest_episode(episodes, "internal")
        child_after_external = [
            episode
            for episode in episodes
            if latest_external is not None
            and episode.get("scope") == "internal"
            and _timestamp(episode.get("confirmation_time")) >= _timestamp(latest_external.get("confirmation_time"))
        ]
        timeframe_episodes[timeframe] = {
            "timeframe": timeframe,
            "episodes": episodes,
            "latest_external_episode": latest_external,
            "latest_internal_episode": latest_internal,
            "internal_events_after_external": child_after_external,
            "shadow_counts": dict(shadow_tf.get("counts") or {}),
        }

    current_story = _current_story(
        timeframes=timeframe_episodes,
        formal_structure_graph_v1=formal_structure_graph_v1,
        causal_poi_authority=causal_poi_authority,
        nodes=nodes,
        edges=edges,
    )
    invariants = _invariants(
        timeframes=timeframe_episodes,
        formal_structure_graph_v1=formal_structure_graph_v1,
        causal_poi_authority=causal_poi_authority,
        accepted_ids=accepted_ids,
    )
    return {
        "schema": "formal_causal_episode_graph_v2",
        "symbol": symbol,
        "decision_time": decision_time,
        "source_graph_schema": formal_structure_graph_v1.get("schema"),
        "structure_shadow_schema": structure_shadow.get("schema"),
        "timeframes": timeframe_episodes,
        "nodes": list(nodes.values()),
        "edges": edges,
        "current_story": current_story,
        "parent_child_context": formal_structure_graph_v1.get("parent_child_context") or {},
        "active_range": formal_structure_graph_v1.get("active_range") or {},
        "invariants": invariants,
        "authority_contract": {
            "observe_only": True,
            "can_challenge_v1": True,
            "enforcement_ready": bool(invariants.get("enforcement_ready")),
            "can_promote_trade_state": False,
            "signal_allowed": False,
            "entry_authorized": False,
            "stop_loss_authorized": False,
            "take_profit_authorized": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }


def episode_graph_requires_review(graph: Mapping[str, Any]) -> bool:
    return str((graph.get("invariants") or {}).get("status")) != "PASS"


def episode_graph_failure_codes(graph: Mapping[str, Any]) -> list[str]:
    return list((graph.get("invariants") or {}).get("violations") or [])


def _build_episode(
    *,
    timeframe: str,
    event: Mapping[str, Any],
    candidate_index: Mapping[str, Mapping[str, Any]],
    payload: Mapping[str, Any],
    causal_poi_authority: Mapping[str, Any],
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    break_id = str(event.get("source_break_object_id") or "")
    event_node_id = f"structure_event:{break_id}"
    event_node = {
        "node_id": event_node_id,
        "node_type": "structure_event",
        "object_id": break_id,
        "timeframe": timeframe,
        "scope": event.get("scope"),
        "direction": event.get("direction"),
        "event_type": event.get("event_type"),
        "lifecycle_state": event.get("lifecycle_state"),
        "interaction_time": event.get("interaction_time"),
        "body_close_time": event.get("body_close_time"),
        "confirmation_time": event.get("confirmation_time"),
        "broken_level_price": event.get("broken_level_price"),
        "source": "StructureEngineV3Shadow",
    }
    nodes[event_node_id] = event_node

    swing_id = str(event.get("broken_swing_id") or "")
    if swing_id:
        swing = candidate_index.get(swing_id) or {}
        swing_node_id = f"swing:{swing_id}"
        nodes[swing_node_id] = {
            "node_id": swing_node_id,
            "node_type": "swing",
            "object_id": swing_id,
            "timeframe": timeframe,
            "scope": ((swing.get("evidence") or {}).get("scale_name") if isinstance(swing.get("evidence"), Mapping) else None),
            "pivot_time": swing.get("pivot_time"),
            "confirmed_at": swing.get("confirmed_at"),
            "price_high": _float(swing.get("price_high")),
            "price_low": _float(swing.get("price_low")),
        }
        _edge(edges, event_node_id, "breaks", swing_node_id, break_id)

    displacement_node_id = f"displacement:{break_id}"
    nodes[displacement_node_id] = {
        "node_id": displacement_node_id,
        "node_type": "displacement_evidence",
        "object_id": break_id,
        "timeframe": timeframe,
        "direction": event.get("direction"),
        "score": event.get("displacement_score"),
        "penetration_atr": event.get("normalized_penetration_atr"),
        "penetration_bps": event.get("close_beyond_structure_bps"),
        "body_to_range_ratio": event.get("body_to_range_ratio"),
    }
    _edge(edges, displacement_node_id, "confirms", event_node_id, break_id)

    linked_pois = _pois_for_break(causal_poi_authority, break_id)
    enriched_pois = [
        {**poi, "structural_role": _poi_structural_role(poi, event)}
        for poi in linked_pois
    ]
    for poi in enriched_pois:
        poi_id = str(poi.get("poi_id") or poi.get("source_object_id") or "")
        if not poi_id:
            continue
        poi_node_id = f"poi:{poi_id}"
        nodes[poi_node_id] = {
            "node_id": poi_node_id,
            "node_type": "poi",
            "object_id": poi_id,
            "source_object_id": poi.get("source_object_id"),
            "timeframe": poi.get("timeframe"),
            "direction": poi.get("direction"),
            "kind": poi.get("kind"),
            "poi_role": poi.get("poi_role"),
            "structural_role": poi.get("structural_role"),
            "causal_status": poi.get("causal_status"),
            "freshness": poi.get("freshness"),
            "price_low": _float(poi.get("price_low")),
            "price_high": _float(poi.get("price_high")),
            "origin_time": poi.get("origin_time"),
            "confirmation_time": poi.get("confirmation_time"),
        }
        _edge(edges, poi_node_id, "originates", event_node_id, break_id)

    linked_inducements = _linked_objects(payload.get("inducements"), "related_break_id", break_id)
    for inducement in linked_inducements:
        inducement_id = str(inducement.get("object_id") or "")
        if not inducement_id:
            continue
        evidence = inducement.get("evidence") if isinstance(inducement.get("evidence"), Mapping) else {}
        node_id = f"inducement:{inducement_id}"
        nodes[node_id] = {
            "node_id": node_id,
            "node_type": "inducement_hypothesis",
            "object_id": inducement_id,
            "timeframe": timeframe,
            "direction": inducement.get("direction"),
            "price": _float(inducement.get("price_low")),
            "pivot_time": inducement.get("pivot_time"),
            "liquidity_side": evidence.get("liquidity_side"),
            "inducement_taken": bool(evidence.get("inducement_taken")),
            "lifecycle": "taken" if evidence.get("inducement_taken") else "resting",
            "truth_status": "hypothesis_only",
        }
        _edge(edges, node_id, "conditions", event_node_id, break_id)
        sweep_id = str(evidence.get("sweep_id") or "")
        if sweep_id:
            _edge(edges, f"sweep:{sweep_id}", "resolves", node_id, inducement_id)

    linked_sweeps = _sweeps_before_event(payload.get("sweeps"), event)
    for sweep in linked_sweeps:
        sweep_id = str(sweep.get("object_id") or "")
        if not sweep_id:
            continue
        evidence = sweep.get("evidence") if isinstance(sweep.get("evidence"), Mapping) else {}
        node_id = f"sweep:{sweep_id}"
        nodes.setdefault(
            node_id,
            {
                "node_id": node_id,
                "node_type": "liquidity_sweep",
                "object_id": sweep_id,
                "timeframe": timeframe,
                "direction": sweep.get("direction"),
                "pivot_time": sweep.get("pivot_time"),
                "confirmed_at": sweep.get("confirmed_at"),
                "swept_level_id": evidence.get("swept_level_id"),
                "swept_price": _float(evidence.get("swept_price")),
                "reclaim_confirmed": bool(evidence.get("reclaim_confirmed")),
            },
        )
        _edge(edges, node_id, "precedes", event_node_id, break_id)

    primary_poi = next((poi for poi in enriched_pois if poi.get("poi_role") == "primary_causal_poi"), None)
    protected_origin = _protected_origin_from_poi(primary_poi, event)
    if protected_origin:
        protected_id = protected_origin["node_id"]
        nodes[protected_id] = protected_origin
        _edge(edges, protected_id, "protects", event_node_id, break_id)

    return {
        "episode_id": f"episode:{break_id}",
        "timeframe": timeframe,
        "scope": event.get("scope"),
        "direction": event.get("direction"),
        "event_type": event.get("event_type"),
        "structure_event_id": break_id,
        "broken_swing_id": swing_id or None,
        "confirmation_time": event.get("confirmation_time") or event.get("body_close_time"),
        "displacement_score": event.get("displacement_score"),
        "protected_origin": protected_origin,
        "primary_poi": dict(primary_poi) if isinstance(primary_poi, Mapping) else None,
        "secondary_pois": [dict(poi) for poi in enriched_pois if poi is not primary_poi],
        "inducement_ids": [item.get("object_id") for item in linked_inducements],
        "sweep_ids": [item.get("object_id") for item in linked_sweeps],
        "story_sentence": _episode_sentence(event, primary_poi, protected_origin),
    }


def _current_story(
    *,
    timeframes: Mapping[str, Any],
    formal_structure_graph_v1: Mapping[str, Any],
    causal_poi_authority: Mapping[str, Any],
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    active_range = formal_structure_graph_v1.get("active_range") or {}
    active_range_timeframe = str(active_range.get("timeframe") or "") if isinstance(active_range, Mapping) else ""
    controlling_tf = None
    controlling_episode = None
    preferred_timeframes = list(
        dict.fromkeys(
            [active_range_timeframe, "4h", "1h", "1d", "12h", "15m", "5m"]
        )
    )
    for timeframe in preferred_timeframes:
        if not timeframe:
            continue
        node = timeframes.get(timeframe)
        episode = node.get("latest_external_episode") if isinstance(node, Mapping) else None
        if isinstance(episode, Mapping):
            controlling_tf = timeframe
            controlling_episode = episode
            break
    parent_child = formal_structure_graph_v1.get("parent_child_context") or {}
    if controlling_episode is None:
        return {
            "status": "INCOMPLETE",
            "controlling_timeframe": None,
            "controlling_episode": None,
            "route_map": None,
            "summary": "No accepted external structure episode survived the V3 shadow lifecycle.",
        }
    direction = str(controlling_episode.get("direction") or "unknown")
    scenario = (causal_poi_authority.get("scenarios") or {}).get(direction)
    scenario = scenario if isinstance(scenario, Mapping) else {}
    route_map = {
        "direction": direction,
        "primary_poi": scenario.get("primary_causal_poi"),
        "secondary_pois": list(scenario.get("secondary_reaction_pois") or []),
        "execution_refinements": list(scenario.get("execution_refinements") or []),
        "inducement_candidates": list(scenario.get("inducement_candidates") or []),
        "active_range": active_range,
        "liquidity_objective": (
            active_range.get("high") if direction == "bullish" else active_range.get("low")
        ),
        "confirmation_requirement": "Lower-timeframe sweep/rejection plus accepted displacement; POI touch alone is not entry authority.",
        "invalidation": (controlling_episode.get("protected_origin") or {}).get("price"),
    }
    status = "MIXED_CONTEXT" if parent_child.get("has_conflict") else "COHERENT_SHADOW_STORY"
    return {
        "status": status,
        "controlling_timeframe": controlling_tf,
        "controlling_episode": controlling_episode,
        "route_map": route_map,
        "summary": (
            f"{controlling_tf} {direction} {controlling_episode.get('event_type')} controls the shadow story. "
            f"Parent-child status is {parent_child.get('status', 'unknown')}; POI status is {scenario.get('status', 'UNRESOLVED')}."
        ),
    }


def _invariants(
    *,
    timeframes: Mapping[str, Any],
    formal_structure_graph_v1: Mapping[str, Any],
    causal_poi_authority: Mapping[str, Any],
    accepted_ids: set[str],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    v1_nodes = formal_structure_graph_v1.get("timeframes") or {}
    for timeframe, node in v1_nodes.items() if isinstance(v1_nodes, Mapping) else []:
        latest = node.get("latest_external_break") if isinstance(node, Mapping) else None
        object_id = str(latest.get("object_id") or "") if isinstance(latest, Mapping) else ""
        if not object_id:
            continue
        checks.append(
            {
                "code": f"{timeframe}_v1_controlling_external_break_survives_v3",
                "passed": object_id in accepted_ids,
                "severity": "review",
                "object_id": object_id,
                "detail": (
                    "The V1 controlling external break passed the stricter V3 lifecycle."
                    if object_id in accepted_ids
                    else "The V1 controlling external break did not pass V3 penetration, displacement, and acceptance checks."
                ),
            }
        )
    for direction, scenario in (causal_poi_authority.get("scenarios") or {}).items():
        if not isinstance(scenario, Mapping):
            continue
        primary = scenario.get("primary_causal_poi")
        if not isinstance(primary, Mapping):
            continue
        linked_break_id = str(primary.get("linked_break_id") or scenario.get("accepted_break_id") or "")
        checks.append(
            {
                "code": f"{direction}_primary_poi_links_v3_accepted_break",
                "passed": linked_break_id in accepted_ids,
                "severity": "review",
                "object_id": str(primary.get("poi_id") or ""),
                "detail": (
                    "Primary POI owns a V3-accepted structure event."
                    if linked_break_id in accepted_ids
                    else "Primary POI lineage ends at a break challenged by V3."
                ),
            }
        )
    if not checks:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "enforcement_ready": False,
            "checks": [],
            "violations": [],
            "certainty_definition": "deterministic_story_consistency_not_future_price_prediction",
        }
    violations = [check["code"] for check in checks if not check["passed"]]
    return {
        "status": "PASS" if not violations else "REVIEW_REQUIRED",
        "enforcement_ready": True,
        "checks": checks,
        "violations": violations,
        "certainty_definition": "deterministic_story_consistency_not_future_price_prediction",
    }


def _candidate_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for group in ("swings", "structure_breaks", "order_blocks", "fvgs", "poi_grade_fvgs", "sweeps", "inducements", "liquidity_levels"):
        for item in payload.get(group, []) or []:
            if isinstance(item, Mapping) and item.get("object_id"):
                index[str(item["object_id"])] = item
    return index


def _pois_for_break(authority: Mapping[str, Any], break_id: str) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for scenario in (authority.get("scenarios") or {}).values():
        if not isinstance(scenario, Mapping):
            continue
        collections: list[Any] = [scenario.get("primary_causal_poi")]
        collections.extend(scenario.get("secondary_reaction_pois") or [])
        collections.extend(scenario.get("execution_refinements") or [])
        for raw in collections:
            if not isinstance(raw, Mapping):
                continue
            linked = {str(raw.get("linked_break_id") or ""), *(str(value) for value in raw.get("linked_break_ids") or [])}
            if break_id not in linked:
                continue
            key = str(raw.get("poi_id") or raw.get("source_object_id") or "")
            if key:
                found.setdefault(key, dict(raw))
    return list(found.values())


def _linked_objects(raw_items: Any, evidence_key: str, object_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in raw_items or []:
        if not isinstance(raw, Mapping):
            continue
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), Mapping) else {}
        if str(evidence.get(evidence_key) or "") == object_id:
            result.append(dict(raw))
    return result


def _sweeps_before_event(raw_items: Any, event: Mapping[str, Any]) -> list[dict[str, Any]]:
    event_time = _timestamp(event.get("confirmation_time") or event.get("body_close_time"))
    direction = str(event.get("direction") or "")
    candidates = []
    for raw in raw_items or []:
        if not isinstance(raw, Mapping) or str(raw.get("direction") or "") != direction:
            continue
        lifecycle = raw.get("sweep_lifecycle") if isinstance(raw.get("sweep_lifecycle"), Mapping) else None
        if lifecycle is not None and lifecycle.get("structural_sweep_confirmed") is not True:
            continue
        confirmed = raw.get("confirmed_at") or raw.get("candidate_at")
        if confirmed is None:
            continue
        timestamp = _timestamp(confirmed)
        if timestamp <= event_time and event_time - timestamp <= pd.Timedelta(days=7):
            candidates.append(dict(raw))
    return sorted(candidates, key=lambda item: _timestamp(item.get("confirmed_at") or item.get("candidate_at")))[-2:]


def _protected_origin_from_poi(
    poi: Mapping[str, Any] | None, event: Mapping[str, Any]
) -> dict[str, Any] | None:
    if not isinstance(poi, Mapping) or str(poi.get("kind") or "") != "order_block":
        return None
    direction = str(event.get("direction") or "")
    price = _float(poi.get("price_low" if direction == "bullish" else "price_high"))
    if price is None:
        return None
    poi_id = str(poi.get("poi_id") or poi.get("source_object_id") or "")
    return {
        "node_id": f"protected_origin:{poi_id}",
        "node_type": "protected_origin",
        "object_id": poi_id,
        "timeframe": poi.get("timeframe"),
        "direction": direction,
        "price": price,
        "source": "causal_primary_order_block_extreme",
        "status": "CANDIDATE_PROTECTED_ORIGIN",
        "reaction_guaranteed": False,
    }


def _poi_structural_role(poi: Mapping[str, Any], event: Mapping[str, Any]) -> str:
    role = str(poi.get("poi_role") or "")
    kind = str(poi.get("kind") or "")
    event_type = str(event.get("event_type") or "")
    if role == "execution_refinement_candidate":
        return "execution_refinement"
    if kind == "fvg":
        return "standalone_primary_fvg" if role == "primary_causal_poi" else "secondary_fvg"
    if role == "primary_causal_poi":
        if "MSS" in event_type:
            return "protected_reversal_origin_ob"
        if event_type == "INITIAL_DIRECTION_BREAK":
            return "direction_establishing_origin_ob"
        return "continuation_origin_ob"
    if str(poi.get("linked_break_scope") or "") == "internal":
        return "secondary_internal_reaction_ob"
    return "secondary_external_ob"


def _episode_sentence(
    event: Mapping[str, Any], poi: Mapping[str, Any] | None, protected: Mapping[str, Any] | None
) -> str:
    sentence = (
        f"{event.get('scope')} {event.get('event_type')} {event.get('direction')} broke "
        f"{event.get('broken_swing_id')} at {event.get('broken_level_price')} and passed the V3 displacement lifecycle."
    )
    if isinstance(poi, Mapping):
        sentence += (
            f" Its {poi.get('poi_role')} is the {poi.get('timeframe')} {poi.get('kind')} "
            f"{poi.get('price_low')}-{poi.get('price_high')}."
        )
    if isinstance(protected, Mapping):
        sentence += f" The candidate protected origin is {protected.get('price')}."
    return sentence


def _latest_episode(episodes: Sequence[Mapping[str, Any]], scope: str) -> dict[str, Any] | None:
    candidates = [episode for episode in episodes if episode.get("scope") == scope]
    return dict(max(candidates, key=lambda item: _timestamp(item.get("confirmation_time")))) if candidates else None


def _event_time(event: Mapping[str, Any]) -> pd.Timestamp:
    return _timestamp(event.get("confirmation_time") or event.get("body_close_time") or event.get("interaction_time"))


def _edge(edges: list[dict[str, Any]], source: str, relation: str, target: str, evidence_id: str) -> None:
    edge = {"source": source, "relation": relation, "target": target, "evidence_object_id": evidence_id}
    if edge not in edges:
        edges.append(edge)


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


__all__ = [
    "build_formal_causal_episode_graph",
    "episode_graph_failure_codes",
    "episode_graph_requires_review",
]
