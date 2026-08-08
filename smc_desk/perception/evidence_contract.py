"""Framework-grade evidence contracts for every exported perception object."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


OBJECT_GROUPS = (
    "swings",
    "structure_breaks",
    "fvgs",
    "poi_grade_fvgs",
    "liquidity_levels",
    "sweeps",
    "order_blocks",
    "inducements",
    "active_pois",
    "pois",
)


def build_object_evidence_contracts(
    *,
    detector_candidates: Mapping[str, Any],
    decision_time: str,
    doctrine_hash: str,
    formal_structure_graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contracts: dict[str, dict[str, Any]] = {}
    object_id_index: dict[str, list[str]] = {}
    duplicate_contract_ids: list[str] = []
    for timeframe, payload in detector_candidates.items():
        if not isinstance(payload, Mapping):
            continue
        for group in OBJECT_GROUPS:
            for raw in payload.get(group, []) or []:
                if not isinstance(raw, Mapping):
                    continue
                contract = _contract(str(timeframe), group, raw, decision_time, doctrine_hash)
                object_id = contract["object_id"]
                contract_id = f"{timeframe}:{group}:{object_id}"
                contract["contract_id"] = contract_id
                if contract_id in contracts:
                    duplicate_contract_ids.append(contract_id)
                    continue
                contracts[contract_id] = contract
                object_id_index.setdefault(object_id, []).append(contract_id)
    active_range = (formal_structure_graph or {}).get("active_range")
    if isinstance(active_range, Mapping) and active_range.get("range_id"):
        range_id = str(active_range["range_id"])
        contract_id = f"active_range:{range_id}"
        range_contract = _range_contract(active_range, decision_time, doctrine_hash)
        range_contract["contract_id"] = contract_id
        contracts[contract_id] = range_contract
        object_id_index.setdefault(range_id, []).append(contract_id)
    incomplete = [object_id for object_id, item in contracts.items() if item["contract_status"] != "COMPLETE"]
    return {
        "schema": "smc_object_evidence_contract_registry_v1",
        "decision_time": decision_time,
        "doctrine_hash": doctrine_hash,
        "contracts": contracts,
        "contract_count": len(contracts),
        "complete_contract_count": len(contracts) - len(incomplete),
        "incomplete_contract_ids": incomplete,
        "object_id_index": object_id_index,
        "ambiguous_object_ids": sorted(object_id for object_id, ids in object_id_index.items() if len(ids) > 1),
        "duplicate_contract_ids": sorted(set(duplicate_contract_ids)),
        "confidence_policy": {
            "probabilistic_confidence_allowed": False,
            "reason": "No adjudicated calibration cohort exists.",
            "legacy_numeric_values_are": "evidence_strength_not_probability",
        },
        "authority_contract": {
            "enforcement_ready": True,
            "evidence_only": True,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }


def _range_contract(raw: Mapping[str, Any], decision_time: str, doctrine_hash: str) -> dict[str, Any]:
    range_id = str(raw.get("range_id"))
    return {
        "schema": "smc_object_evidence_contract_v1",
        "object_id": range_id,
        "object": "active_range",
        "classification": "structurally_activated_dealing_range",
        "status": str(raw.get("status") or "confirmed").lower(),
        "timeframe": str(raw.get("timeframe") or "unknown"),
        "start_anchor": {"time": None, "candle_id": None},
        "end_or_confirmation_anchor": {"time": decision_time, "candle_id": f"decision:{decision_time}"},
        "price_coordinates": {"price": None, "price_low": _number(raw.get("low")), "price_high": _number(raw.get("high"))},
        "candle_ids": [f"decision:{decision_time}"],
        "first_knowable_candle": decision_time,
        "decision_time": decision_time,
        "observed_evidence": {"direction": _value(raw.get("direction")), "source": raw.get("source")},
        "structural_interpretation": "Active range exported by formal structure authority; not a visible-window extreme.",
        "causal_predecessor_ids": [str(value) for value in raw.get("source_pivot_ids") or []],
        "causal_consequence_ids": [],
        "competing_interpretations": ["nested internal range", "superseded historical range"],
        "invalidation_condition": "Superseded or invalidated by a later confirmed structural range event.",
        "doctrine_dependent_assumptions": ["range anchors require confirmed structural pivots"],
        "doctrine_hash": doctrine_hash,
        "evidence_strength": None,
        "evidence_strength_semantics": "not_scored",
        "confidence": None,
        "confidence_status": "UNAVAILABLE_UNCALIBRATED",
        "abstain": False,
        "missing_fields": [],
        "contract_status": "COMPLETE",
    }


def contract_ids_for_object(
    registry: Mapping[str, Any],
    object_id: str,
    *,
    timeframe: str | None = None,
) -> list[str]:
    index = registry.get("object_id_index") if isinstance(registry, Mapping) else None
    contracts = registry.get("contracts") if isinstance(registry, Mapping) else None
    if not isinstance(index, Mapping) or not isinstance(contracts, Mapping):
        return []
    ids = [str(value) for value in index.get(str(object_id), [])]
    if timeframe is not None:
        ids = [
            contract_id
            for contract_id in ids
            if str((contracts.get(contract_id) or {}).get("timeframe")) == str(timeframe)
        ]
    return ids


def _contract(
    timeframe: str, group: str, raw: Mapping[str, Any], decision_time: str, doctrine_hash: str,
) -> dict[str, Any]:
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), Mapping) else {}
    object_id = str(raw.get("object_id") or raw.get("id") or raw.get("poi_id") or "")
    start_time = _first(raw, "pivot_time", "origin_time", "candidate_at", "start_time") or _event_time(raw, "OBJECT_CREATED")
    confirmation_time = (
        _first(raw, "confirmed_at", "confirmation_time", "candidate_at", "end_time")
        or _event_time(raw, "OBJECT_CONFIRMED")
        or start_time
    )
    first_knowable = confirmation_time or start_time
    price = _number(raw.get("price"))
    price_low = _number(raw.get("price_low"))
    price_high = _number(raw.get("price_high"))
    if price is None:
        price = _number(evidence.get("broken_price") or evidence.get("swept_price"))
    predecessor_ids, consequence_ids = _causal_ids(evidence)
    missing: list[str] = []
    if not object_id:
        missing.append("object_id")
    if not timeframe:
        missing.append("timeframe")
    if first_knowable is None:
        missing.append("first_knowable_candle")
    if price is None and price_low is None and price_high is None:
        missing.append("price_coordinates")
    abstain = bool(missing)
    candle_ids = [
        f"{timeframe}:{value}"
        for value in dict.fromkeys(value for value in (start_time, confirmation_time) if value is not None)
    ]
    return {
        "schema": "smc_object_evidence_contract_v1",
        "object_id": object_id,
        "object": group,
        "classification": _classification(group, raw),
        "status": _status(raw),
        "timeframe": timeframe,
        "start_anchor": {"time": start_time, "candle_id": candle_ids[0] if candle_ids else None},
        "end_or_confirmation_anchor": {"time": confirmation_time, "candle_id": candle_ids[-1] if candle_ids else None},
        "price_coordinates": {"price": price, "price_low": price_low, "price_high": price_high},
        "candle_ids": candle_ids,
        "first_knowable_candle": first_knowable,
        "decision_time": decision_time,
        "observed_evidence": {
            "direction": _value(raw.get("direction")),
            "raw_object_type": _value(raw.get("object_type")),
            "structure_scope": _value(raw.get("structure_scope") or evidence.get("structure_scope")),
            "wick_only_probe": bool(raw.get("is_wick_only_probe") or evidence.get("is_unconfirmed_probe")),
            "source_evidence": dict(evidence),
            "sweep_lifecycle": dict(raw.get("sweep_lifecycle") or {}) if isinstance(raw.get("sweep_lifecycle"), Mapping) else None,
        },
        "structural_interpretation": _interpretation(group, raw),
        "causal_predecessor_ids": predecessor_ids,
        "causal_consequence_ids": consequence_ids,
        "competing_interpretations": _competing_interpretations(group),
        "invalidation_condition": _invalidation(group),
        "doctrine_dependent_assumptions": _doctrine_assumptions(group),
        "doctrine_hash": doctrine_hash,
        "evidence_strength": _number(raw.get("evidence_strength") or raw.get("legacy_heuristic_score")),
        "evidence_strength_semantics": "heuristic_not_probability",
        "confidence": None,
        "confidence_status": "UNAVAILABLE_UNCALIBRATED",
        "abstain": abstain,
        "missing_fields": missing,
        "contract_status": "INCOMPLETE_ABSTAIN" if abstain else "COMPLETE",
    }


def _classification(group: str, raw: Mapping[str, Any]) -> str:
    return str(raw.get("break_type") or raw.get("object_type") or raw.get("kind") or group.rstrip("s")).lower()


def _status(raw: Mapping[str, Any]) -> str:
    return str(_value(raw.get("confirmation_status")) or raw.get("truth_status") or _value(raw.get("activity_status")) or "candidate").lower()


def _interpretation(group: str, raw: Mapping[str, Any]) -> str:
    direction = _value(raw.get("direction")) or "unknown"
    scope = _value(raw.get("structure_scope")) or "unspecified"
    return f"{group.rstrip('s')} candidate; direction={direction}; scope={scope}; no predictive reaction is guaranteed."


def _competing_interpretations(group: str) -> list[str]:
    if group == "structure_breaks":
        return ["internal shift rather than external break", "wick probe or failed breakout", "range expansion without accepted structure"]
    if group == "sweeps":
        return ["penetration awaiting rejection", "accepted breakout beyond liquidity", "local wick with no structural consequence"]
    if group in {"order_blocks", "fvgs", "poi_grade_fvgs", "active_pois", "pois"}:
        return ["secondary reaction zone", "execution refinement rather than controlling POI", "already compromised or non-causal zone"]
    if group == "swings":
        return ["internal pivot", "noise inside displacement", "competing external swing hierarchy"]
    if group == "inducements":
        return ["ordinary internal liquidity", "retrospective label", "unresolved hypothesis"]
    return ["local observation without structural consequence"]


def _invalidation(group: str) -> str:
    if group == "structure_breaks":
        return "Downgrade if no accepted close/follow-through or the broken level is not structurally controlling."
    if group == "sweeps":
        return "Invalidate sweep if price accepts beyond the pool without rejection and opposing consequence."
    if group in {"order_blocks", "fvgs", "poi_grade_fvgs", "active_pois", "pois"}:
        return "Invalidate or consume according to the point-in-time POI lifecycle and close-through doctrine."
    if group == "swings":
        return "Supersede when a later confirmed hierarchy objectively becomes controlling."
    return "Abstain or downgrade when source anchors, temporal order, or structural consequence cannot be proven."


def _doctrine_assumptions(group: str) -> list[str]:
    assumptions = ["completed candles only", "internal structure cannot flip parent structure"]
    if group == "structure_breaks":
        assumptions.append("close-based confirmation; wick penetration is not confirmed BOS")
    if group == "sweeps":
        assumptions.append("penetration alone is provisional until rejection/acceptance evidence develops")
    if group in {"order_blocks", "fvgs", "poi_grade_fvgs", "active_pois", "pois"}:
        assumptions.append("causal origin outranks proximity or later reaction")
    return assumptions


def _causal_ids(evidence: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    predecessor_keys = ("sweep_id", "source_swing_id", "origin_id", "protected_point_id")
    consequence_keys = ("related_break_id", "linked_break_id", "break_id", "confirmation_event_id")
    predecessors = [str(evidence[key]) for key in predecessor_keys if evidence.get(key)]
    consequences = [str(evidence[key]) for key in consequence_keys if evidence.get(key)]
    return predecessors, consequences


def _first(raw: Mapping[str, Any], *keys: str) -> Any:
    return next((raw[key] for key in keys if raw.get(key) is not None), None)


def _event_time(raw: Mapping[str, Any], event_type: str) -> Any:
    for event in raw.get("event_history", []) or raw.get("events", []) or []:
        if isinstance(event, Mapping) and str(event.get("event_type")) == event_type and event.get("timestamp") is not None:
            return event["timestamp"]
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _value(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


__all__ = ["build_object_evidence_contracts", "contract_ids_for_object"]
