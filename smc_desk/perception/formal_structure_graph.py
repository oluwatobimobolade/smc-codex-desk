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
        # Hierarchical read alongside the unanimity vote in
        # parent_child_context. The vote answers "do the timeframes agree?";
        # this answers "what story do they tell, and where is price drawn?".
        # Additive and observe-only: it cannot promote, and every existing
        # consumer of parent_child_context is untouched.
        "narrative_context": _build_narrative_context(
            timeframes, ar, detector_candidates, timeframe_dfs
        ),
    }


def _current_price(timeframe_dfs: Mapping[str, Any] | None) -> float | None:
    """Last close of the fastest available timeframe.

    The narrative needs to know where price actually is to rank liquidity
    above and below it; the active-range node carries the range but not the
    current price.
    """
    if not timeframe_dfs:
        return None
    for tf in ("5m", "15m", "1h", "4h", "12h", "1d"):
        frame = timeframe_dfs.get(tf)
        if frame is None or not hasattr(frame, "empty") or frame.empty:
            continue
        for column in ("close", "Close"):
            if column in frame.columns:
                return _float_or_none(frame[column].iloc[-1])
    return None


def _build_narrative_context(
    timeframes: Mapping[str, Any],
    active_range: Mapping[str, Any],
    detector_candidates: Mapping[str, Any],
    timeframe_dfs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach the hierarchical narrative read. Never raises into the hot path."""
    from smc_desk.perception.narrative_hierarchy import read_narrative

    try:
        liquidity: list[Mapping[str, Any]] = []
        if isinstance(detector_candidates, Mapping):
            for payload in detector_candidates.values():
                if not isinstance(payload, Mapping):
                    continue
                levels = payload.get("liquidity_levels")
                if isinstance(levels, Sequence) and not isinstance(levels, (str, bytes)):
                    liquidity.extend(x for x in levels if isinstance(x, Mapping))
        current_price = (
            _float_or_none((active_range or {}).get("current_price"))
            or _current_price(timeframe_dfs)
        )
        return read_narrative(
            timeframes=timeframes,
            active_range=active_range,
            current_price=current_price,
            liquidity_levels=liquidity,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001 -- observe-only layer must never break the graph
        return {
            "schema": "mtf_narrative_read_v1",
            "state": "INSUFFICIENT_CONTEXT",
            "is_coherent": False,
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
            "authority": "observe_only_narrative_read",
            "signal_allowed": False,
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
    protected_high, protected_low = _protected_levels(payload, external)

    return {
        "timeframe": tf,
        "external_bias": external_bias,
        "internal_state": internal_state,
        "protected_high": protected_high,
        "protected_low": protected_low,
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
    stale_child_breaks: list[dict[str, Any]] = []
    ignored_stale_timeframes: set[str] = set()
    conflicts = []
    for pi, parent_tf in enumerate(ordered[:-1]):
        if parent_tf in ignored_stale_timeframes:
            continue
        parent_bias = votes[parent_tf]
        if parent_bias not in DIRECTIONS:
            continue
        for child_tf in ordered[pi + 1:]:
            stale_relation = _stale_child_relation(timeframes, parent_tf, child_tf)
            if stale_relation:
                stale_child_breaks.append(stale_relation)
                ignored_stale_timeframes.add(child_tf)
                continue
            child_bias = votes[child_tf]
            if child_bias in DIRECTIONS and child_bias != parent_bias:
                conflicts.append((parent_tf, parent_bias, child_tf, child_bias))

    if conflicts:
        ptf, pb, ctf, cb = conflicts[0]
        broke_parent = _child_broke_parent(timeframes, ptf, ctf, cb)
        if broke_parent:
            thesis = (
                f"{ctf} {cb} child structure body-closed beyond the {ptf} {pb} parent protected level. "
                "Treat this as a confirmed parent-break candidate, not an internal pullback."
            )
            return {
                "status": "PARENT_BREAK_CONFIRMED",
                "has_conflict": False,
                "parent_timeframe": ptf,
                "parent_bias": pb,
                "child_timeframe": ctf,
                "child_bias": cb,
                "child_type": "parent_break_candidate",
                "is_child_body_closed_beyond_parent_protected": True,
                "aligned_bias": cb,
                "thesis_sentence": thesis,
                "stale_child_breaks": stale_child_breaks,
                "all_conflicts": [
                    {"parent_timeframe": a, "parent_bias": b, "child_timeframe": c, "child_bias": d}
                    for a, b, c, d in conflicts
                ],
            }

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
            "is_child_body_closed_beyond_parent_protected": False,
            "required_final_bias": "mixed",
            "required_trade_state": "THESIS_ONLY",
            "thesis_sentence": thesis,
            "stale_child_breaks": stale_child_breaks,
            "all_conflicts": [
                {"parent_timeframe": a, "parent_bias": b, "child_timeframe": c, "child_bias": d}
                for a, b, c, d in conflicts
            ],
        }

    aligned = [votes[tf] for tf in ordered if tf not in ignored_stale_timeframes and votes[tf] in DIRECTIONS]
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
        "stale_child_breaks": stale_child_breaks,
        "thesis_sentence": f"Context timeframes aligned {aligned_bias}." if aligned_bias in DIRECTIONS else "Context alignment incomplete.",
    }


def _child_broke_parent(
    timeframes: Mapping[str, Any], parent_tf: str, child_tf: str, child_bias: str
) -> bool:
    parent = timeframes.get(parent_tf)
    child = timeframes.get(child_tf)
    if not isinstance(parent, Mapping) or not isinstance(child, Mapping):
        return False
    if _anchors_collapsed(parent):
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
    body_close = child_break.get("body_close_price")
    if body_close is None:
        return False
    return float(body_close) > float(parent_level) if child_bias == "bullish" else float(body_close) < float(parent_level)


def _stale_child_relation(timeframes: Mapping[str, Any], parent_tf: str, child_tf: str) -> dict[str, Any] | None:
    parent = timeframes.get(parent_tf)
    child = timeframes.get(child_tf)
    if not isinstance(parent, Mapping) or not isinstance(child, Mapping):
        return None
    parent_break = parent.get("latest_external_break")
    child_break = child.get("latest_external_break")
    if not isinstance(parent_break, Mapping) or not isinstance(child_break, Mapping):
        return None
    parent_time = _confirmed_time(parent_break)
    child_time = _confirmed_time(child_break)
    if parent_time is None or child_time is None or child_time >= parent_time:
        return None
    return {
        "parent_timeframe": parent_tf,
        "parent_break_id": parent_break.get("object_id"),
        "parent_confirmed_at": parent_break.get("confirmed_at"),
        "child_timeframe": child_tf,
        "child_break_id": child_break.get("object_id"),
        "child_confirmed_at": child_break.get("confirmed_at"),
        "reason": "Child external break is older than the current parent external break, so it is stale context and cannot influence parent-child alignment.",
    }


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
        _invariant_protected_anchors_are_distinct(timeframes),
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


def _invariant_protected_anchors_are_distinct(timeframes: Mapping[str, Any]) -> dict[str, Any]:
    collapsed = [tf for tf, node in timeframes.items() if isinstance(node, Mapping) and _anchors_collapsed(node)]
    if collapsed:
        return {
            "code": "protected_high_low_must_be_distinct",
            "passed": False,
            "severity": "fatal",
            "detail": "The same swing/price cannot be both protected high and protected low: " + ", ".join(collapsed) + ".",
        }
    return {
        "code": "protected_high_low_must_be_distinct",
        "passed": True,
        "severity": "info",
        "detail": "Protected high and low anchors are side-specific; no collapsed anchor pair was found.",
    }


def _invariant_internal_cannot_flip_parent(timeframes: Mapping[str, Any], pc: Mapping[str, Any]) -> dict[str, Any]:
    """A child conflict without body-close MUST carry the mixed-bias downgrade.

    Reachable failure: _build_parent_child_context regresses and stops
    stamping required_final_bias on an unresolved conflict — the exact drift
    that would let a child timeframe silently flip the parent bias.
    """
    if not pc.get("has_conflict"):
        return {"code": "internal_child_cannot_flip_parent", "passed": True, "severity": "info", "detail": "No parent-child conflict found."}
    if pc.get("is_child_body_closed_beyond_parent_protected"):
        return {"code": "internal_child_cannot_flip_parent", "passed": True, "severity": "info",
                "detail": "Child body-closed beyond parent protected level - parent flip is legitimate."}
    if pc.get("required_final_bias") != "mixed":
        return {"code": "internal_child_cannot_flip_parent", "passed": False, "severity": "fatal",
                "detail": "Unresolved parent-child conflict does not require mixed bias; "
                          "a child could flip the parent without body-close. "
                          f"required_final_bias={pc.get('required_final_bias')!r}."}
    return {"code": "internal_child_cannot_flip_parent", "passed": True, "severity": "info",
            "detail": f"Parent-child conflict is acknowledged: parent {pc.get('parent_timeframe')} remains {pc.get('parent_bias')}, "
            f"child {pc.get('child_timeframe')} is {pc.get('child_bias')} pullback/recovery with required mixed bias. "
            "Child cannot flip parent without body-close beyond parent protected level."}


def _invariant_child_body_close_for_parent_break(timeframes: Mapping[str, Any], pc: Mapping[str, Any]) -> dict[str, Any]:
    """A claimed parent break MUST replay against the recorded levels.

    Reachable failure: parent_child_context claims PARENT_BREAK_CONFIRMED but
    the child's recorded body-close does not actually exceed the parent
    protected level (or the levels are missing) when recomputed here.
    """
    if pc.get("status") == "PARENT_BREAK_CONFIRMED" or pc.get("is_child_body_closed_beyond_parent_protected"):
        ptf = str(pc.get("parent_timeframe") or "")
        ctf = str(pc.get("child_timeframe") or "")
        cb = str(pc.get("child_bias") or "")
        if not _child_broke_parent(timeframes, ptf, ctf, cb):
            return {"code": "child_body_close_required_for_parent_break", "passed": False, "severity": "fatal",
                    "detail": f"Parent break claimed for {ctf} {cb} over {ptf}, but the recorded child "
                              "body-close does not exceed the parent protected level on recomputation."}
        return {"code": "child_body_close_required_for_parent_break", "passed": True, "severity": "info",
                "detail": "Parent break recomputed: child body-close genuinely exceeds the parent protected level."}
    if not pc.get("has_conflict"):
        return {"code": "child_body_close_required_for_parent_break", "passed": True, "severity": "info", "detail": "No parent-child conflict."}
    return {"code": "child_body_close_required_for_parent_break", "passed": True, "severity": "info",
            "detail": "Parent-child conflict exists and child has NOT body-closed beyond parent protected level. "
            "Parent structure governs; child is pullback/recovery."}


def _invariant_wick_probes_are_not_breaks(timeframes: Mapping[str, Any]) -> dict[str, Any]:
    """No wick-only probe may occupy a confirmed-break position.

    Reachable failure: the _confirmed_breaks filter regresses and a probe
    (is_wick_only_probe, or a break without confirmed_at) leaks into a
    timeframe node's latest_external_break / latest_internal_break slot.
    """
    leaked: list[str] = []
    probe_summary: list[str] = []
    for tf, node in timeframes.items():
        if not isinstance(node, Mapping):
            continue
        count = node.get("wick_probe_count", 0)
        if count > 0:
            probe_summary.append(f"{tf}={count}")
        for key in ("latest_external_break", "latest_internal_break"):
            summary = node.get(key)
            if not isinstance(summary, Mapping):
                continue
            if summary.get("is_wick_only_probe") or not summary.get("confirmed_at"):
                leaked.append(f"{tf}.{key}={summary.get('object_id', '?')}")
    if leaked:
        return {"code": "wick_probes_are_not_breaks", "passed": False, "severity": "fatal",
                "detail": f"Unconfirmed probe occupies a confirmed-break slot: {', '.join(leaked)}."}
    if probe_summary:
        return {"code": "wick_probes_are_not_breaks", "passed": True, "severity": "info",
                "detail": f"Wick probes present (normal market noise): {', '.join(probe_summary)}. "
                          "None occupy confirmed-break slots."}
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
    """An unresolved conflict MUST demand THESIS_ONLY.

    Reachable failure: the conflict branch of _build_parent_child_context
    stops stamping required_trade_state, which would let downstream trade
    gating treat a conflicted graph as promotable.
    """
    if pc.get("has_conflict"):
        if pc.get("required_trade_state") != "THESIS_ONLY":
            return {"code": "parent_child_conflict_blocks_trade_ready", "passed": False, "severity": "fatal",
                    "detail": "Parent-child conflict present but required_trade_state is "
                              f"{pc.get('required_trade_state')!r} instead of THESIS_ONLY."}
        return {"code": "parent_child_conflict_blocks_trade_ready", "passed": True, "severity": "info",
                "detail": "Parent-child conflict present. TRADE_PLAN_READY is blocked; THESIS_ONLY required."}
    return {"code": "parent_child_conflict_blocks_trade_ready", "passed": True, "severity": "info",
            "detail": "No parent-child conflict; trade readiness allowed if other checks pass."}


# ── Authority Contract ──────────────────────────────────────────────────


def _authority_contract(invariants: Mapping[str, Any], parent_child: Mapping[str, Any]) -> dict[str, Any]:
    invariant_passed = invariants["status"] == "PASS"
    trade_blocked = invariants["status"] != "PASS" or parent_child.get("has_conflict", False)
    return {
        "signal_allowed": False,
        "execution": "disabled",
        "capital_risk": 0,
        "graph_is_authoritative": True,
        "overrides_blocked": True,
        "invariant_passed": invariant_passed,
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
        "body_close_price": _body_close_price(item),
        "is_choch": bool(item.get("is_choch", False)),
        "broke_protected_swing": bool(ev.get("broke_protected_swing", False)),
        "is_wick_only_probe": bool(ev.get("is_unconfirmed_probe", False)),
    }


def _body_close_price(item: Mapping[str, Any]) -> float | None:
    ev = item.get("evidence") or {}
    broken = _float_or_none(ev.get("broken_price"))
    penetration = _float_or_none(ev.get("body_close_penetration"))
    direction = _direction(item)
    if broken is None or penetration is None or direction not in DIRECTIONS:
        return None
    return broken + penetration if direction == "bullish" else broken - penetration


def _protected_levels(
    payload: Mapping[str, Any], external: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve each protected side from its own detector swing.

    A broken swing is never copied into both slots. Exact detector state wins;
    otherwise the latest confirmed external high and low visible at the break
    are retained as conservative side-specific anchors.
    """
    swings = _flatten_swings(payload.get("swings"))
    by_id = {str(item.get("object_id") or ""): item for item in swings}
    state = payload.get("structure_state") or {}
    if not isinstance(state, Mapping):
        state = {}

    direction = _direction(external)
    # Only one side is protected in a directional leg. The opposite field in
    # the track can be stale from the prior regime, so pair the protected side
    # with the latest confirmed swing on the other side.
    high_id = state.get("protected_high_id") if direction == "bearish" else state.get("last_confirmed_external_high")
    low_id = state.get("protected_low_id") if direction == "bullish" else state.get("last_confirmed_external_low")
    high = _swing_anchor(by_id.get(str(high_id or "")), "high", "detector_structure_state")
    low = _swing_anchor(by_id.get(str(low_id or "")), "low", "detector_structure_state")

    cutoff = _confirmed_time(external) if external else None
    if high is None:
        high = _latest_side_anchor(swings, "high", cutoff)
    if low is None:
        low = _latest_side_anchor(swings, "low", cutoff)

    # Compatibility for small synthetic fixtures with no swing pool. Only the
    # directionally protected side may fall back to break evidence.
    if external is not None:
        ev = external.get("evidence") or {}
        if high is None and direction == "bearish":
            high = _explicit_or_break_anchor(ev, "high")
        if low is None and direction == "bullish":
            low = _explicit_or_break_anchor(ev, "low")
    return high, low


def _flatten_swings(raw: Any) -> list[dict[str, Any]]:
    groups = raw.values() if isinstance(raw, Mapping) else [raw]
    out: list[dict[str, Any]] = []
    for group in groups:
        for item in group or []:
            value = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            if isinstance(value, Mapping):
                out.append(dict(value))
    return out


def _latest_side_anchor(
    swings: list[dict[str, Any]], side: str, cutoff: datetime | None,
) -> dict[str, Any] | None:
    expected_direction = "bearish" if side == "high" else "bullish"
    eligible = []
    for swing in swings:
        if _direction(swing) != expected_direction or not _is_external_swing(swing):
            continue
        confirmed = _confirmed_time(swing)
        if cutoff is not None and confirmed is not None and confirmed > cutoff:
            continue
        eligible.append(swing)
    if not eligible:
        return None
    eligible.sort(key=lambda item: str(item.get("confirmed_at") or item.get("pivot_time") or ""))
    return _swing_anchor(eligible[-1], side, "latest_confirmed_external_swing")


def _is_external_swing(swing: Mapping[str, Any]) -> bool:
    scale = str(swing.get("scale") or (swing.get("evidence") or {}).get("scale_name") or "")
    return scale in {"external", "raw_pivot_candidate_window_5"} or bool((swing.get("evidence") or {}).get("is_external"))


def _swing_anchor(swing: Mapping[str, Any] | None, side: str, source: str) -> dict[str, Any] | None:
    if not isinstance(swing, Mapping):
        return None
    price = _float_or_none(swing.get("price_high" if side == "high" else "price_low"))
    if price is None:
        return None
    return {"price": price, "source": source, "swing_id": str(swing.get("object_id") or "")}


def _explicit_or_break_anchor(ev: Mapping[str, Any], side: str) -> dict[str, Any] | None:
    explicit = _float_or_none(ev.get(f"protected_{side}_price"))
    if explicit is not None:
        return {"price": explicit, "source": "evidence_protected_field", "swing_id": str(ev.get(f"protected_{side}_id") or "")}
    price = _float_or_none(ev.get("broken_price"))
    if price is None:
        return None
    return {"price": price, "source": "legacy_directional_break_fallback", "swing_id": str(ev.get("broken_swing_id") or "")}


def _anchors_collapsed(node: Mapping[str, Any]) -> bool:
    high = node.get("protected_high")
    low = node.get("protected_low")
    if not isinstance(high, Mapping) or not isinstance(low, Mapping):
        return False
    high_id, low_id = str(high.get("swing_id") or ""), str(low.get("swing_id") or "")
    high_price, low_price = _float_or_none(high.get("price")), _float_or_none(low.get("price"))
    return bool(high_id and low_id and high_id == low_id) or (
        high_price is not None and low_price is not None and high_price <= low_price
    )


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
