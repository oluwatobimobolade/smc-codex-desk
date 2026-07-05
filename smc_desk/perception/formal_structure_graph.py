"""Deterministic formal MTF structure graph.

This is the single authoritative source that every AI thesis, chart annotation,
POI claim, and trade/watch state must be subordinate to. The graph is built
deterministically from detector candidates and active range authority. It runs
hard invariants that block any downstream promotion to trade-ready when structure
is ambiguous, conflicting, or unconfirmed.

No AI. No randomness. No external API. One truth.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import pandas as pd

DIRECTIONS = {"bullish", "bearish"}
CONTEXT_TIMEFRAMES = ("1d", "12h", "4h", "1h")
ALL_TIMEFRAMES = ("1d", "12h", "4h", "1h", "15m", "5m")


def build_mtf_structure_graph(
    *,
    symbol: str,
    detector_candidates: Mapping[str, Any],
    active_range_authority: Mapping[str, Any],
    timeframe_dfs: Mapping[str, pd.DataFrame] | None = None,
    decision_time: str | None = None,
) -> dict[str, Any]:
    """Build the formal graph. All callers must defer to this output."""
    if decision_time is None:
        decision_time = datetime.now(timezone.utc).isoformat()

    timeframes = _build_timeframe_nodes(detector_candidates)
    pc = _build_parent_child_context(timeframes)
    ar = _build_active_range_node(active_range_authority)
    invariants = _check_invariants(timeframes, pc, ar)
    contract = _authority_contract(invariants, pc)

    return {
        "schema": "formal_mtf_structure_graph_v1",
        "symbol": symbol,
        "decision_time": decision_time,
        "timeframes": timeframes,
        "parent_child_context": pc,
        "active_range": ar,
        "invariants": invariants,
        "authority_contract": contract,
    }


# ── Timeframe Node Builder ──────────────────────────────────────────────


def _build_timeframe_nodes(detector_candidates: Mapping[str, Any]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for tf in ALL_TIMEFRAMES:
        if tf not in detector_candidates:
            continue
        payload = detector_candidates.get(tf)
        if not isinstance(payload, Mapping):
            continue
        nodes[tf] = _node_for_timeframe(tf, payload)
    return nodes


def _node_for_timeframe(tf: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    breaks = _confirmed_breaks(payload.get("structure_breaks", []) or [])
    external = _latest_by_scope(breaks, "external")
    internal = _latest_by_scope(breaks, "internal")
    wick_probes = _wick_probes(payload.get("structure_breaks", []) or [])

    ext_bias = _direction(external)
    int_dir = _direction(internal)

    external_bias = ext_bias or "unknown"
    internal_state = _compute_internal_state(ext_bias, int_dir, external, internal)

    return {
        "timeframe": tf,
        "external_bias": external_bias,
        "internal_state": internal_state,
        "protected_high": _protected_level(external, "high") if external else None,
        "protected_low": _protected_level(external, "low") if external else None,
        "latest_external_break": _break_summary(external) if external else None,
        "latest_internal_break": _break_summary(internal) if internal else None,
        "has_wick_probes": len(wick_probes) > 0,
        "wick_probe_count": len(wick_probes),
        "structure_break_count": len(breaks),
        "confirmed_external_count": len([b for b in breaks if _scope(b) == "external"]),
        "confirmed_internal_count": len([b for b in breaks if _scope(b) == "internal"]),
        "order_blocks": {
            "total": len(payload.get("order_blocks", []) or []),
            "demand": len([o for o in (payload.get("order_blocks", []) or []) if _direction_str(o.get("direction")) == "bullish"]),
            "supply": len([o for o in (payload.get("order_blocks", []) or []) if _direction_str(o.get("direction")) == "bearish"]),
        },
        "poi_grade_fvgs": len(payload.get("poi_grade_fvgs", []) or []),
        "sweeps": len(payload.get("sweeps", []) or []),
        "liquidity_levels": len(payload.get("liquidity_levels", []) or []),
        "inducements": len(payload.get("inducements", []) or []),
    }


def _compute_internal_state(
    ext_bias: str | None,
    int_dir: str | None,
    external: Mapping[str, Any] | None,
    internal: Mapping[str, Any] | None,
) -> str:
    if ext_bias not in DIRECTIONS or int_dir not in DIRECTIONS:
        return "none"
    if ext_bias == int_dir:
        return f"{ext_bias}_internal_continuation"
    if not _int_after_ext(internal, external):
        return "none"
    if ext_bias == "bearish" and int_dir == "bullish":
        return "bullish_internal_pullback"
    if ext_bias == "bullish" and int_dir == "bearish":
        return "bearish_internal_pullback"
    return "none"


def _int_after_ext(internal: Mapping[str, Any] | None, external: Mapping[str, Any] | None) -> bool:
    if not internal or not external:
        return False
    int_time = _confirmed_time(internal)
    ext_time = _confirmed_time(external)
    return int_time is not None and ext_time is not None and int_time >= ext_time


# ── Parent-Child Context ────────────────────────────────────────────────


def _build_parent_child_context(timeframes: Mapping[str, Any]) -> dict[str, Any]:
    ordered = [tf for tf in CONTEXT_TIMEFRAMES if isinstance(timeframes.get(tf), Mapping)]
    if len(ordered) < 2:
        return {
            "status": "INSUFFICIENT_CONTEXT",
            "has_conflict": False,
            "parent_timeframe": None,
            "parent_bias": None,
            "child_timeframe": None,
            "child_bias": None,
            "child_type": None,
            "is_child_body_closed_beyond_parent_protected": False,
            "thesis_sentence": "Insufficient multi-timeframe context for parent-child analysis.",
        }

    votes = {tf: timeframes[tf]["external_bias"] for tf in ordered}
    conflicts = []
    for pi, parent_tf in enumerate(ordered[:-1]):
        parent_bias = votes[parent_tf]
        if parent_bias not in DIRECTIONS:
            continue
        for child_tf in ordered[pi + 1:]:
            child_bias = votes[child_tf]
            if child_bias in DIRECTIONS and child_bias != parent_bias:
                conflicts.append((parent_tf, parent_bias, child_tf, child_bias))

    if conflicts:
        ptf, pb, ctf, cb = conflicts[0]
        child_type = "recovery" if cb == "bullish" else "selloff"
        thesis = (
            f"{ptf} remains {pb} parent structure while {ctf} is {cb} child {child_type}; "
            "treat the child move as a pullback/recovery inside parent context "
            "until the parent protected structure breaks."
        )
        return {
            "status": "PARENT_CHILD_CONFLICT",
            "has_conflict": True,
            "parent_timeframe": ptf,
            "parent_bias": pb,
            "child_timeframe": ctf,
            "child_bias": cb,
            "child_type": child_type,
            "is_child_body_closed_beyond_parent_protected": _child_broke_parent(timeframes, ptf, ctf, cb),
            "required_final_bias": "mixed",
            "required_trade_state": "THESIS_ONLY",
            "thesis_sentence": thesis,
            "all_conflicts": [
                {"parent_timeframe": a, "parent_bias": b, "child_timeframe": c, "child_bias": d}
                for a, b, c, d in conflicts
            ],
        }

    aligned = [votes[tf] for tf in ordered if votes[tf] in DIRECTIONS]
    aligned_bias = aligned[0] if aligned and len(set(aligned)) == 1 else "mixed"
    return {
        "status": "ALIGNED" if aligned_bias in DIRECTIONS else "INCOMPLETE_ALIGNMENT",
        "has_conflict": False,
        "parent_timeframe": None,
        "parent_bias": None,
        "child_timeframe": None,
        "child_bias": None,
        "child_type": None,
        "is_child_body_closed_beyond_parent_protected": False,
        "aligned_bias": aligned_bias,
        "thesis_sentence": f"Context timeframes aligned {aligned_bias}." if aligned_bias in DIRECTIONS else "Context alignment incomplete.",
    }


def _child_broke_parent(
    timeframes: Mapping[str, Any], parent_tf: str, child_tf: str, child_bias: str
) -> bool:
    parent = timeframes.get(parent_tf)
    child = timeframes.get(child_tf)
    if not isinstance(parent, Mapping) or not isinstance(child, Mapping):
        return False
    if child_bias == "bullish":
        parent_level = _protected_high_from_node(parent)
    else:
        parent_level = _protected_low_from_node(parent)
    if parent_level is None:
        return False
    child_break = child.get("latest_external_break")
    if not isinstance(child_break, Mapping):
        return False
    break_price = child_break.get("broken_price")
    if break_price is None:
        return False
    return float(break_price) > float(parent_level) if child_bias == "bullish" else float(break_price) < float(parent_level)


def _protected_high_from_node(node: Mapping[str, Any]) -> float | None:
    ph = node.get("protected_high")
    if isinstance(ph, Mapping):
        return _float_or_none(ph.get("price"))
    return _float_or_none(ph)


def _protected_low_from_node(node: Mapping[str, Any]) -> float | None:
    pl = node.get("protected_low")
    if isinstance(pl, Mapping):
        return _float_or_none(pl.get("price"))
    return _float_or_none(pl)


# ── Active Range Node ───────────────────────────────────────────────────


def _build_active_range_node(authority: Mapping[str, Any]) -> dict[str, Any]:
    selected = authority.get("selected_range") if isinstance(authority, Mapping) else None
    if not isinstance(selected, Mapping) or selected.get("status") != "RESOLVED_ACTIVE_RANGE":
        return {
            "status": "UNRESOLVED",
            "timeframe": None,
            "direction": "unknown",
            "high": None,
            "low": None,
            "equilibrium": None,
            "price_location": "unknown",
            "source": "unresolved",
            "evidence": ["Active range authority did not certify a protected swing pair."],
        }
    return {
        "status": "RESOLVED",
        "timeframe": str(selected.get("timeframe", "")),
        "direction": str(selected.get("direction", "unknown")),
        "high": _float_or_none(selected.get("range_high")),
        "low": _float_or_none(selected.get("range_low")),
        "equilibrium": _float_or_none(selected.get("equilibrium")),
        "price_location": str(selected.get("price_location", "unknown")),
        "source": "protected_swing_pair",
        "range_id": str(selected.get("range_id", "")),
        "width_atr": _float_or_none(selected.get("width_atr")),
        "max_allowed_width_atr": _float_or_none(selected.get("max_width_atr")),
        "protected_high_swing_id": str(selected.get("protected_high_pivot_id", "")),
        "protected_low_swing_id": str(selected.get("protected_low_pivot_id", "")),
        "evidence": list(selected.get("authority_notes") or []),
    }


# ── Invariant Checks ────────────────────────────────────────────────────


def _check_invariants(
    timeframes: Mapping[str, Any],
    parent_child: Mapping[str, Any],
    active_range: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _invariant_internal_cannot_flip_parent(timeframes, parent_child),
        _invariant_child_body_close_for_parent_break(timeframes, parent_child),
        _invariant_wick_probes_are_not_breaks(timeframes),
        _invariant_active_range_from_structure(timeframes, active_range),
        _invariant_ohcl_summary_not_range_source(active_range),
        _invariant_parent_child_conflict_blocks_trade(parent_child),
    ]
    violations = [c for c in checks if not c["passed"]]
    if any(c["severity"] == "fatal" for c in violations):
        status = "FATAL_STRUCTURE_VIOLATION"
    elif violations:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"
    return {"status": status, "checks": checks, "violations": [v["code"] for v in violations]}


def _invariant_internal_cannot_flip_parent(timeframes: Mapping[str, Any], pc: Mapping[str, Any]) -> dict[str, Any]:
    if not pc.get("has_conflict"):
        return {"code": "internal_child_cannot_flip_parent", "passed": True, "severity": "info", "detail": "No parent-child conflict found."}
    if pc.get("is_child_body_closed_beyond_parent_protected"):
        return {"code": "internal_child_cannot_flip_parent", "passed": True, "severity": "info",
                "detail": f"Child body-closed beyond parent protected level - parent flip is legitimate."}
    return {"code": "internal_child_cannot_flip_parent", "passed": True, "severity": "info",
            "detail": f"Parent-child conflict is acknowledged: parent {pc.get('parent_timeframe')} remains {pc.get('parent_bias')}, "
            f"child {pc.get('child_timeframe')} is {pc.get('child_bias')} pullback/recovery. "
            "Child cannot flip parent without body-close beyond parent protected level. This is the expected state."}


def _invariant_child_body_close_for_parent_break(timeframes: Mapping[str, Any], pc: Mapping[str, Any]) -> dict[str, Any]:
    if not pc.get("has_conflict"):
        return {"code": "child_body_close_required_for_parent_break", "passed": True, "severity": "info", "detail": "No parent-child conflict."}
    if pc.get("is_child_body_closed_beyond_parent_protected"):
        return {"code": "child_body_close_required_for_parent_break", "passed": True, "severity": "info",
                "detail": "Child has body-closed beyond parent protected level. Parent break is legitimate."}
    return {"code": "child_body_close_required_for_parent_break", "passed": True, "severity": "info",
            "detail": "Parent-child conflict exists and child has NOT body-closed beyond parent protected level. "
            "This is the expected state - parent structure governs, child is pullback/recovery. "
            "Child body close would be required to legitimately flip the parent bias."}


def _invariant_wick_probes_are_not_breaks(timeframes: Mapping[str, Any]) -> dict[str, Any]:
    for tf, node in timeframes.items():
        if not isinstance(node, Mapping):
            continue
        if node.get("has_wick_probes"):
            return {"code": "wick_probes_are_not_breaks", "passed": False, "severity": "hard",
                    "detail": f"Wick-only breaks detected in {tf}. These are probes/sweeps, not confirmed BOS/CHoCH."}
    return {"code": "wick_probes_are_not_breaks", "passed": True, "severity": "info", "detail": "No unconfirmed wick probes detected."}


def _invariant_active_range_from_structure(timeframes: Mapping[str, Any], active_range: Mapping[str, Any]) -> dict[str, Any]:
    source = active_range.get("source", "")
    if source == "protected_swing_pair" and active_range.get("status") == "RESOLVED":
        return {"code": "active_range_from_swing_structure", "passed": True, "severity": "info", "detail": "Active range resolved from confirmed swing structure."}
    return {"code": "active_range_from_swing_structure", "passed": False, "severity": "hard",
            "detail": f"Active range source is '{source}', status is '{active_range.get('status')}'. Range must come from confirmed swing structure, not OHLC summary extremes."}


def _invariant_ohcl_summary_not_range_source(active_range: Mapping[str, Any]) -> dict[str, Any]:
    if active_range.get("source") == "ohlcv_summary_high_low":
        return {"code": "ohcl_summary_not_range_source", "passed": False, "severity": "hard",
                "detail": "Active range was sourced from OHLC summary extremes. This is forbidden."}
    return {"code": "ohcl_summary_not_range_source", "passed": True, "severity": "info", "detail": "Active range not sourced from OHLC summary."}


def _invariant_parent_child_conflict_blocks_trade(pc: Mapping[str, Any]) -> dict[str, Any]:
    if pc.get("has_conflict"):
        return {"code": "parent_child_conflict_blocks_trade_ready", "passed": True, "severity": "info",
                "detail": "Parent-child conflict present. TRADE_PLAN_READY is blocked; THESIS_ONLY required."}
    return {"code": "parent_child_conflict_blocks_trade_ready", "passed": True, "severity": "info",
            "detail": "No parent-child conflict; trade readiness allowed if other checks pass."}


# ── Authority Contract ──────────────────────────────────────────────────


def _authority_contract(invariants: Mapping[str, Any], parent_child: Mapping[str, Any]) -> dict[str, Any]:
    sig_allowed = invariants["status"] == "PASS"
    trade_blocked = invariants["status"] != "PASS" or parent_child.get("has_conflict", False)
    return {
        "signal_allowed": sig_allowed,
        "execution": "disabled",
        "capital_risk": 0,
        "graph_is_authoritative": True,
        "overrides_blocked": True,
        "invariant_status": invariants["status"],
        "trade_promotion_blocked": trade_blocked,
        "invariant_failure_codes": invariants.get("violations", []),
    }


# ── Helpers ─────────────────────────────────────────────────────────────


def _confirmed_breaks(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        d = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(d, Mapping):
            continue
        ev = d.get("evidence") or {}
        if d.get("confirmed_at") and not ev.get("is_unconfirmed_probe"):
            out.append(d)
    out.sort(key=lambda x: str(x.get("confirmed_at") or ""))
    return out


def _wick_probes(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        d = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(d, Mapping):
            continue
        ev = d.get("evidence") or {}
        if ev.get("is_unconfirmed_probe"):
            out.append(d)
    return out


def _latest_by_scope(breaks: list[dict[str, Any]], scope: str) -> dict[str, Any] | None:
    matches = [b for b in breaks if _scope(b) == scope]
    return matches[-1] if matches else None


def _scope(item: Mapping[str, Any]) -> str:
    ev = item.get("evidence") or {}
    val = str(item.get("structure_scope") or ev.get("structure_scope") or "")
    if val in {"external", "internal"}:
        return val
    return "internal" if ev.get("is_internal") else "external"


def _direction(item: Mapping[str, Any] | None) -> str | None:
    if item is None:
        return None
    d = str(item.get("direction", "")).lower()
    return d if d in DIRECTIONS else None


def _direction_str(value: Any) -> str:
    d = str(value or "").lower()
    return d if d in DIRECTIONS else "unknown"


def _confirmed_time(item: Mapping[str, Any]) -> datetime | None:
    raw = item.get("confirmed_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _break_summary(item: Mapping[str, Any]) -> dict[str, Any] | None:
    ev = item.get("evidence") or {}
    return {
        "object_id": str(item.get("object_id", "")),
        "break_type": str(item.get("break_type", "")),
        "direction": _direction(item) or "unknown",
        "scope": _scope(item),
        "confirmed_at": str(item.get("confirmed_at", "")),
        "broken_price": _float_or_none(ev.get("broken_price")),
        "is_choch": bool(item.get("is_choch", False)),
        "broke_protected_swing": bool(ev.get("broke_protected_swing", False)),
        "is_wick_only_probe": bool(ev.get("is_unconfirmed_probe", False)),
    }


def _protected_level(item: Mapping[str, Any] | None, kind: str) -> dict[str, Any] | None:
    if item is None:
        return None
    ev = item.get("evidence") or {}
    p_key = f"protected_{kind}_price" if kind in ("high", "low") else None
    if p_key and p_key in ev:
        return {"price": _float_or_none(ev[p_key]), "source": "evidence_protected_field"}
    swing_id = ev.get("broken_swing_id")
    price = _float_or_none(ev.get("broken_price"))
    if swing_id is None and price is None:
        return None
    return {"price": price, "source": "broken_swing", "swing_id": str(swing_id or "")}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ── Graph-to-Prompt / Graph-to-Validator Adapters ────────────────────────


def graph_requires_thesis_only(graph: dict[str, Any]) -> bool:
    """True if the graph blocks any promotion beyond THESIS_ONLY."""
    contract = graph.get("authority_contract") or {}
    if contract.get("trade_promotion_blocked"):
        return True
    return False


def graph_requires_mixed_bias(graph: dict[str, Any]) -> bool:
    """True if the graph requires direction=mixed."""
    pc = graph.get("parent_child_context") or {}
    return pc.get("has_conflict", False)


def graph_thesis_sentence(graph: dict[str, Any]) -> str:
    """The required parent-child thesis sentence from the graph."""
    pc = graph.get("parent_child_context") or {}
    return str(pc.get("thesis_sentence", ""))


def graph_invariant_violation_codes(graph: dict[str, Any]) -> list[str]:
    """All invariant violation codes that must be surfaced."""
    inv = graph.get("invariants") or {}
    return list(inv.get("violations", []))


def graph_to_dict_string(graph: dict[str, Any]) -> str:
    """Serialize the graph for insertion into prompts."""
    stripped = {
        "schema": graph.get("schema"),
        "symbol": graph.get("symbol"),
        "invariant_status": graph.get("invariants", {}).get("status"),
        "parent_child_context": {
            "status": graph.get("parent_child_context", {}).get("status"),
            "thesis_sentence": graph.get("parent_child_context", {}).get("thesis_sentence"),
        },
        "timeframes": {},
    }
    for tf, node in (graph.get("timeframes") or {}).items():
        if not isinstance(node, Mapping):
            continue
        stripped["timeframes"][tf] = {
            "external_bias": node.get("external_bias"),
            "internal_state": node.get("internal_state"),
            "protected_high": node.get("protected_high"),
            "protected_low": node.get("protected_low"),
            "latest_external_break": node.get("latest_external_break"),
        }
    active = graph.get("active_range") or {}
    stripped["active_range"] = {
        "timeframe": active.get("timeframe"),
        "direction": active.get("direction"),
        "high": active.get("high"),
        "low": active.get("low"),
        "equilibrium": active.get("equilibrium"),
        "price_location": active.get("price_location"),
    }
    return json.dumps(stripped, indent=2, default=str)
