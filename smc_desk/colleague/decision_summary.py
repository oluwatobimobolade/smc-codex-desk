from __future__ import annotations

from typing import Any

from smc_desk.colleague.smc_semantics import build_semantic_overlay


TIMEFRAME_CHAIN = ("1d", "4h", "1h", "15m")
CHECKLIST_LABELS = {
    "directional_bias": "HTF directional bias",
    "fresh_or_partial_poi": "fresh or valid POI",
    "premium_discount_aligned": "premium/discount location",
    "liquidity_sweep": "liquidity sweep",
    "displacement_break": "displacement or structure break",
    "sweep_before_break": "sweep before break",
    "price_at_or_near_poi": "price at or near POI",
    "stop_has_volatility_buffer": "volatility-buffered stop",
    "risk_reward_floor": "minimum R:R",
}


def _latest(items: list[dict[str, Any]], key: str = "confirmed_at") -> dict[str, Any] | None:
    visible = [item for item in items if item.get(key) or item.get("candidate_at") or item.get("pivot_time")]
    if not visible:
        return None
    return sorted(visible, key=lambda item: str(item.get(key) or item.get("candidate_at") or item.get("pivot_time")))[-1]


def _latest_active_fvgs(payload: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    fvgs = [
        item
        for item in payload.get("fvgs", [])
        if item.get("confirmation_status") == "confirmed"
        and item.get("activity_status") != "terminal"
        and item.get("mitigation_status") != "full"
    ]
    return sorted(fvgs, key=lambda item: str(item.get("confirmed_at") or item.get("candidate_at") or item.get("pivot_time")), reverse=True)[:limit]


def _structure_summary(payload: dict[str, Any]) -> dict[str, Any]:
    structure_state = payload.get("structure_state", {}) or {}
    latest_break = _latest(payload.get("structure_breaks", []))
    return {
        "current_direction": structure_state.get("current_direction"),
        "protected_high_id": structure_state.get("protected_high_id"),
        "protected_low_id": structure_state.get("protected_low_id"),
        "last_external_break_id": structure_state.get("last_external_break_id"),
        "last_internal_break_id": structure_state.get("last_internal_break_id"),
        "latest_break": None
        if latest_break is None
        else {
            "object_id": latest_break.get("object_id"),
            "break_type": latest_break.get("break_type") or ("CHOCH" if latest_break.get("is_choch") else "BOS"),
            "direction": latest_break.get("direction"),
            "confirmation_status": latest_break.get("confirmation_status"),
            "confirmed_at": latest_break.get("confirmed_at"),
            "price_low": latest_break.get("price_low"),
            "price_high": latest_break.get("price_high"),
        },
    }


def build_confirmed_state(perception_by_tf: dict[str, dict[str, Any]], mtf_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_type": "confirmed_closed_candle_state",
        "source": "PerceptionEngineV2",
        "execution_consensus": mtf_snapshot.get("execution_consensus"),
        "timeframes": {
            tf: {
                "swing_counts": {scale: len(items) for scale, items in payload.get("swings", {}).items()},
                "structure_break_count": len(payload.get("structure_breaks", [])),
                "fvg_count": len(payload.get("fvgs", [])),
                "structure_state": payload.get("structure_state", {}),
                "structure_summary": _structure_summary(payload),
                "active_fvg_count": len(_latest_active_fvgs(payload, limit=10)),
            }
            for tf, payload in perception_by_tf.items()
        },
    }


def build_provisional_state() -> dict[str, Any]:
    return {
        "state_type": "provisional_live_state",
        "status": "not_enabled_for_closed_candle_historical_run",
        "display_warning": "PROVISIONAL - NOT CONFIRMED UNTIL CLOSE",
        "objects": [],
    }


def build_mtf_state_graph(
    perception_by_tf: dict[str, dict[str, Any]],
    mtf_snapshot: dict[str, Any],
    legacy_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = []
    edges = []
    semantic_overlay = build_semantic_overlay(
        perception_by_tf=perception_by_tf,
        mtf_snapshot=mtf_snapshot,
        legacy_analysis=None,
    )

    for tf in TIMEFRAME_CHAIN:
        payload = perception_by_tf.get(tf, {})
        mtf_ctx = mtf_snapshot.get(tf, {}) if tf in mtf_snapshot else {}
        structure = _structure_summary(payload)
        nodes.append(
            {
                "node_id": f"timeframe:{tf}",
                "timeframe": tf,
                "object_type": "timeframe_context",
                "status": "active",
                "confirmation_time": payload.get("decision_time"),
                "summary": {
                    "swings": sum(len(items) for items in payload.get("swings", {}).values()),
                    "structure_breaks": len(payload.get("structure_breaks", [])),
                    "fvgs": len(payload.get("fvgs", [])),
                    "bias": mtf_ctx.get("bias") or structure.get("current_direction") or "neutral",
                    "last_close": mtf_ctx.get("last_close"),
                    "latest_break": structure.get("latest_break"),
                },
            }
        )
        latest_break = structure.get("latest_break")
        if latest_break:
            break_node = {
                "node_id": f"structure_break:{tf}:{latest_break['object_id']}",
                "timeframe": tf,
                "object_type": "structure_break",
                "status": latest_break.get("confirmation_status"),
                "direction": latest_break.get("direction"),
                "break_type": latest_break.get("break_type"),
                "confirmed_at": latest_break.get("confirmed_at"),
                "price_low": latest_break.get("price_low"),
                "price_high": latest_break.get("price_high"),
            }
            nodes.append(break_node)
            edges.append({"from": break_node["node_id"], "to": f"timeframe:{tf}", "relationship": "LATEST_STRUCTURE_SIGNAL"})
        for fvg in _latest_active_fvgs(payload):
            node_id = f"fvg:{tf}:{fvg.get('object_id')}"
            nodes.append(
                {
                    "node_id": node_id,
                    "timeframe": tf,
                    "object_type": "fvg",
                    "status": fvg.get("mitigation_status"),
                    "activity_status": fvg.get("activity_status"),
                    "direction": fvg.get("direction"),
                    "confirmed_at": fvg.get("confirmed_at"),
                    "price_low": fvg.get("price_low"),
                    "price_high": fvg.get("price_high"),
                    "confidence": fvg.get("confidence"),
                }
            )
            edges.append({"from": f"timeframe:{tf}", "to": node_id, "relationship": "HAS_ACTIVE_FVG"})

    selected_htf_poi = mtf_snapshot.get("selected_htf_poi")
    if selected_htf_poi:
        zone = selected_htf_poi.get("zone", {})
        node_id = "poi:selected_htf"
        nodes.append(
            {
                "node_id": node_id,
                "object_type": "selected_htf_poi",
                "timeframe": selected_htf_poi.get("timeframe"),
                "status": selected_htf_poi.get("state"),
                "direction": zone.get("direction"),
                "kind": zone.get("kind"),
                "price_low": zone.get("low"),
                "price_high": zone.get("high"),
                "distance_atr": selected_htf_poi.get("distance_atr"),
                "rank": selected_htf_poi.get("rank"),
            }
        )
        edges.append({"from": f"timeframe:{selected_htf_poi.get('timeframe')}", "to": node_id, "relationship": "SELECTED_POI"})

    nodes.extend(semantic_overlay["nodes"])
    edges.extend(semantic_overlay["edges"])

    current_context = _current_decision_context(mtf_snapshot=mtf_snapshot, mtf_graph=None)
    decision_node = {
        "node_id": "decision:current",
        "object_type": "decision_state",
        "status": current_context["action"],
        "direction": current_context["direction"],
        "setup_grade": None,
        "risk_pct": 0,
        "confluence_score": None,
        "passed_conditions": [item["condition"] for item in current_context["preconditions"]["passed"]],
        "failed_conditions": [item["condition"] for item in current_context["preconditions"]["failed"]],
        "authority": "current_perception_mtf_context_no_execution_authority",
        "legacy_trade_plan_used": False,
    }
    nodes.append(decision_node)
    edges.append({"from": "timeframe:15m", "to": "decision:current", "relationship": "EXECUTION_CONTEXT"})

    for parent, child in (("1d", "4h"), ("4h", "1h"), ("1h", "15m")):
        if parent in perception_by_tf and child in perception_by_tf:
            edges.append({"from": f"timeframe:{parent}", "to": f"timeframe:{child}", "relationship": "CONTAINS"})
            edges.append({"from": f"timeframe:{child}", "to": f"timeframe:{parent}", "relationship": "REFINES"})
    execution_consensus = mtf_snapshot.get("execution_consensus")
    for tf in ("1h", "4h", "1d"):
        bias = (mtf_snapshot.get(tf) or {}).get("bias")
        if execution_consensus in {"bullish", "bearish"} and bias in {"bullish", "bearish"}:
            edges.append(
                {
                    "from": f"timeframe:{tf}",
                    "to": "decision:current",
                    "relationship": "BIAS_SUPPORTS" if bias == execution_consensus else "BIAS_CONFLICTS",
                }
            )
    return {
        "graph_version": "0.3",
        "source": "PerceptionEngineV2 snapshots plus MTF consensus",
        "execution_consensus": mtf_snapshot.get("execution_consensus"),
        "semantic_overlay": {
            "version": semantic_overlay["semantic_version"],
            "authority": semantic_overlay["authority"],
            "summary": semantic_overlay["summary"],
        },
        "market_story": {
            "htf_alignment": {
                "descriptive_alignment": mtf_snapshot.get("alignment"),
                "execution_consensus": mtf_snapshot.get("execution_consensus"),
                "agreement_count": mtf_snapshot.get("agreement_count"),
                "total_count": mtf_snapshot.get("total_count"),
            },
            "structure_path": {tf: _structure_summary(perception_by_tf.get(tf, {})) for tf in TIMEFRAME_CHAIN},
            "poi_context": {
                "selected_htf_poi": selected_htf_poi,
                "active_fvg_counts": {tf: len(_latest_active_fvgs(perception_by_tf.get(tf, {}), limit=20)) for tf in TIMEFRAME_CHAIN},
            },
            "semantic_summary": semantic_overlay["summary"],
            "execution_blockers": current_context["preconditions"]["failed"],
        },
        "nodes": nodes,
        "edges": edges,
    }


def _alignment_failed(source_alignment_status: str) -> bool:
    return str(source_alignment_status).upper() in {"SOURCE_MISMATCH", "FAILED", "FAIL"}


def _selected_htf_poi_summary(selected_htf_poi: dict[str, Any] | None) -> str | None:
    if not selected_htf_poi:
        return None
    zone = selected_htf_poi.get("zone", {}) or {}
    low = zone.get("low")
    high = zone.get("high")
    parts = [
        str(selected_htf_poi.get("timeframe") or "unknown_tf"),
        str(zone.get("kind") or "poi"),
        str(zone.get("direction") or "neutral"),
        f"{low}-{high}" if low is not None and high is not None else "zone_unpriced",
        str(selected_htf_poi.get("state") or "unknown_state"),
    ]
    return " ".join(parts)


def _current_decision_context(
    *,
    mtf_snapshot: dict[str, Any],
    mtf_graph: dict[str, Any] | None = None,
    source_alignment_status: str = "NOT_ATTACHED",
) -> dict[str, Any]:
    selected_htf_poi = mtf_snapshot.get("selected_htf_poi")
    zone = (selected_htf_poi or {}).get("zone", {}) or {}
    consensus = mtf_snapshot.get("execution_consensus")
    direction = zone.get("direction") or consensus or "neutral"
    source_failed = _alignment_failed(source_alignment_status)

    passed: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    supporting_evidence = [
        f"Execution consensus: {consensus}",
    ]
    poi_summary = _selected_htf_poi_summary(selected_htf_poi)
    if poi_summary:
        supporting_evidence.append(f"Selected HTF POI: {poi_summary}")

    if consensus in {"bullish", "bearish"}:
        passed.append({"condition": "htf_execution_consensus", "label": "HTF execution consensus exists"})
    else:
        failed.append({"condition": "no_directional_execution_consensus", "label": "no directional HTF execution consensus"})

    if str(source_alignment_status).upper() == "PASS":
        passed.append({"condition": "source_alignment_verified", "label": "TradingView/source alignment verified"})
    elif source_failed:
        failed.append({"condition": "source_alignment_failed", "label": "TradingView/source alignment failed"})

    if selected_htf_poi:
        passed.append({"condition": "selected_htf_poi_mapped", "label": "selected HTF POI mapped"})
    else:
        failed.append({"condition": "no_selected_htf_poi", "label": "no selected HTF POI in current MTF context"})

    if source_failed:
        action = "SOURCE_MISMATCH"
        action_state = "BLOCKED"
        status = "blocked"
        setup_stage = "source_mismatch"
        next_best_action = "repair_source_alignment"
    elif selected_htf_poi and str(selected_htf_poi.get("state")).lower() in {"approaching", "at_poi"}:
        action = "WATCH"
        action_state = "WATCH"
        status = "watch"
        setup_stage = "monitoring_higher_timeframe_poi"
        next_best_action = "monitor_for_15m_confirmation"
        failed.append({"condition": "no_current_execution_state", "label": "no validated current execution state"})
    else:
        action = "NO_SETUP"
        action_state = "NO_SETUP"
        status = "candidate"
        setup_stage = "htf_poi_mapped_not_in_play" if selected_htf_poi else "no_complete_setup"
        next_best_action = "stand_aside"
        failed.append({"condition": "no_current_execution_state", "label": "no validated current execution state"})

    failed.append({"condition": "prediction_not_certified", "label": "prediction model is not certified"})
    failed.append({"condition": "paper_live_execution_disabled", "label": "paper/live execution remains disabled"})

    if mtf_graph:
        semantic_summary = (mtf_graph.get("market_story") or {}).get("semantic_summary") or {}
        if semantic_summary:
            supporting_evidence.append(f"Semantic candidates: {semantic_summary}")

    if action == "WATCH":
        confirmations = [
            "15m confirmation must form from closed candles at or after the mapped POI interaction.",
            "Any execution thesis must be separately validated by the strategy state-machine and outcome ledger.",
            "TradingView alignment must remain PASS if external visual evidence is attached.",
        ]
    elif action == "SOURCE_MISMATCH":
        confirmations = [
            "Repair symbol/exchange/timeframe/candle-state mismatch before using this package for review.",
        ]
    else:
        confirmations = [
            "Wait for a valid aligned POI context plus closed-candle confirmation before considering a trade plan.",
        ]

    return {
        "action": action,
        "action_state": action_state,
        "status": status,
        "setup_stage": setup_stage,
        "direction": direction,
        "next_best_action": next_best_action,
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": [item["label"] for item in failed],
        "preconditions": {"passed": passed, "failed": failed},
        "required_confirmation_events": confirmations,
    }


def _context_invalidation(selected_htf_poi: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not selected_htf_poi:
        return []
    zone = selected_htf_poi.get("zone", {}) or {}
    direction = zone.get("direction")
    if direction == "bearish":
        price = zone.get("high")
    elif direction == "bullish":
        price = zone.get("low")
    else:
        price = None
    return [
        {
            "type": "context_invalidation_reference",
            "price": price,
            "authority": "context_only_not_execution_sl",
        }
    ]


def build_scenario_tree(
    mtf_snapshot: dict[str, Any],
    mtf_graph: dict[str, Any] | None = None,
    source_alignment_status: str = "NOT_ATTACHED",
) -> dict[str, Any]:
    context = _current_decision_context(
        mtf_snapshot=mtf_snapshot,
        mtf_graph=mtf_graph,
        source_alignment_status=source_alignment_status,
    )
    selected_htf_poi = mtf_snapshot.get("selected_htf_poi")
    scenario = {
        "scenario_id": f"scenario:{context['direction']}:{context['status']}",
        "direction": context["direction"],
        "scope": "mtf",
        "status": context["status"],
        "setup_stage": context["setup_stage"],
        "decision_time": mtf_snapshot.get("decision_time"),
        "supporting_evidence": context["supporting_evidence"],
        "contradicting_evidence": context["contradicting_evidence"],
        "preconditions": context["preconditions"],
        "required_confirmation_events": context["required_confirmation_events"],
        "invalidation_events": _context_invalidation(selected_htf_poi),
        "target_definition": {"status": "not_defined_no_execution_plan", "targets": [], "liquidity_target": None},
        "expiry_rule": {"type": "strategy_profile_default", "value": "48 completed 15m candles after entry for RASC-SMC-V1"},
        "current_action_state": context["action_state"],
        "next_best_action": context["next_best_action"],
        "probability": None,
        "probability_status": "not_modelled",
        "model_version": None,
        "sample_support": {"status": "not_retrieved_in_wp0002_slice"},
        "uncertainty": {"status": "prediction_not_certified"},
        "alternative_scenarios": [
            {
                "scenario_id": "alternative:range_continuation",
                "status": "watch_only",
                "reason": "If sweep/displacement/POI confirmation remains absent, treat movement as range liquidity until proven otherwise.",
            },
            {
                "scenario_id": "alternative:opposite_break",
                "status": "invalidates_primary_bias",
                "reason": "A confirmed protected-structure break against the HTF consensus invalidates the current directional read.",
            },
        ],
    }
    return {
        "scenario_contract": "SCENARIO_CONTRACT_V1",
        "scenario_tree_version": "0.3",
        "graph_source": "perception/mtf_state_graph.json" if mtf_graph else None,
        "market_story": (mtf_graph or {}).get("market_story"),
        "scenarios": [scenario],
    }


def build_decision(
    mtf_snapshot: dict[str, Any],
    mtf_graph: dict[str, Any] | None = None,
    source_alignment_status: str = "NOT_ATTACHED",
) -> dict[str, Any]:
    context = _current_decision_context(
        mtf_snapshot=mtf_snapshot,
        mtf_graph=mtf_graph,
        source_alignment_status=source_alignment_status,
    )
    return {
        "decision_policy": "DECISION_POLICY_V1",
        "action": context["action"],
        "paper_execution_enabled": False,
        "live_execution_enabled": False,
        "capital_risk": 0,
        "reason": "Current decision is derived from PerceptionEngineV2 plus MTF context only; legacy engine comparison is not decision authority.",
        "authority_source": "PerceptionEngineV2+MTF_CONTEXT",
        "legacy_trade_plan_used": False,
        "decision_basis": {
            "source_alignment_status": source_alignment_status,
            "setup_stage": context["setup_stage"],
            "next_best_action": context["next_best_action"],
        },
    }
