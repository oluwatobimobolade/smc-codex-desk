"""Decision policy and evidence graph builder.

Produces conservative DecisionEnvelopes from StrategyStateResult
and MTF graph output. No PAPER_EXECUTE. No trade.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from smc_desk.decision.contracts import (
    Decision,
    DecisionEnvelope,
    Direction,
    EvidenceItem,
    ScenarioResult,
    StrategyStateResult,
    TraderState,
)


def build_decision_envelope(
    strategy_result: StrategyStateResult,
    mtf_graph: Dict[str, Any],
    *,
    authority_sources: Optional[Dict[str, str]] = None,
) -> DecisionEnvelope:
    """Build a conservative decision envelope from strategy state and MTF graph.

    The decision policy operates after the state engine. It applies
    additional safety gates and produces the final action.
    """
    authority = authority_sources or {}
    direction = strategy_result.direction
    state = strategy_result.state
    now = datetime.now(tz=timezone.utc)

    # ── Priority-order decision gates ──

    # Gate 1: Market truth failure
    if authority.get("market_truth") == "FAILED":
        return DecisionEnvelope(
            decision=Decision.ABSTAIN, direction=Direction.NEUTRAL,
            state=state, strategy_id=strategy_result.strategy_id,
            scenarios=[],
            reason="market_truth_unavailable",
            authority=authority, timestamp=now,
        )

    # Gate 2: Stale or incomplete timeframe
    timeframe_statuses = mtf_graph.get("timeframe_statuses", {})
    unhealthy = [
        tf for tf, ts in timeframe_statuses.items()
        if not ts.get("available", True) or ts.get("insufficient_history", False)
    ]
    if unhealthy:
        return DecisionEnvelope(
            decision=Decision.ABSTAIN, direction=Direction.NEUTRAL,
            state=state, strategy_id=strategy_result.strategy_id,
            scenarios=[],
            reason=f"unhealthy_timeframes:{','.join(sorted(unhealthy))}",
            authority=authority, timestamp=now,
        )

    # Gate 3: State determines action
    state_to_decision = {
        TraderState.NO_SETUP: Decision.OBSERVE,
        TraderState.CONTEXT_FORMING: Decision.OBSERVE,
        TraderState.WATCH: Decision.WATCH,
        TraderState.ARMED: Decision.WATCH,
        TraderState.TRIGGERED: Decision.WATCH,  # no execution yet
        TraderState.INVALIDATED: Decision.ABSTAIN,
        TraderState.EXPIRED: Decision.ABSTAIN,
        TraderState.RESOLVED: Decision.OBSERVE,
        TraderState.ABSTAIN: Decision.ABSTAIN,
    }
    decision = state_to_decision.get(state, Decision.ABSTAIN)

    # Gate 4: No strategy = OBSERVE only
    if strategy_result.strategy_id == "NONE" and decision == Decision.WATCH:
        decision = Decision.OBSERVE

    # Build scenarios from MTF graph
    scenarios = _build_scenarios(strategy_result, mtf_graph)

    return DecisionEnvelope(
        decision=decision, direction=direction,
        state=state, strategy_id=strategy_result.strategy_id,
        scenarios=scenarios,
        reason=f"state:{state.value}_strategy:{strategy_result.strategy_id}",
        authority=authority, timestamp=now,
    )


def _build_scenarios(
    strategy_result: StrategyStateResult,
    mtf_graph: Dict[str, Any],
) -> List[ScenarioResult]:
    """Build scenario evidence graph from MTF graph and strategy state."""
    scenarios: List[ScenarioResult] = []
    unresolved = mtf_graph.get("unresolved", [])
    nodes = mtf_graph.get("nodes", [])
    edges = mtf_graph.get("edges", [])

    # Determine direction from MTF state
    mtf_state = mtf_graph.get("state", {})
    direction_str = mtf_state.get("direction_bias", "neutral")
    direction = Direction.BULLISH if direction_str == "bullish" else (
        Direction.BEARISH if direction_str == "bearish" else Direction.NEUTRAL
    )

    # Build supporting evidence from confirmed breaks and FVGs
    supporting: List[EvidenceItem] = []
    opposing: List[EvidenceItem] = []
    missing: List[EvidenceItem] = []
    confirmation_events: List[str] = []

    for node in nodes:
        if node.get("node_type") == "structure_break" and node.get("metadata", {}).get("confirmed"):
            break_id = node["node_id"]
            bt = node.get("metadata", {}).get("break_type", "")
            d = node.get("direction", "neutral")
            supporting.append(EvidenceItem(
                evidence_id=f"ev_{break_id}",
                evidence_type="supporting",
                description=f"{bt} break on {node['timeframe']} ({d})",
                event_ids=[break_id],
            ))
            confirmation_events.append(break_id)

    for node in nodes:
        if node.get("node_type") == "fvg":
            fvg_id = node["node_id"]
            mitigated = node.get("metadata", {}).get("mitigated", False)
            if not mitigated:
                supporting.append(EvidenceItem(
                    evidence_id=f"ev_{fvg_id}",
                    evidence_type="supporting",
                    description=f"Active FVG on {node['timeframe']} ({node['direction']})",
                    event_ids=[fvg_id],
                ))

    # Unresolved items become opposing or missing evidence
    for item in unresolved:
        if "contradiction" in item or "conflict" in item:
            opposing.append(EvidenceItem(
                evidence_id=f"ev_opp_{hash(item) & 0xffff}",
                evidence_type="opposing",
                description=item,
                event_ids=[],
            ))
        elif "missing" in item or "insufficient" in item:
            missing.append(EvidenceItem(
                evidence_id=f"ev_miss_{hash(item) & 0xffff}",
                evidence_type="missing",
                description=item,
                event_ids=[],
            ))

    # Find invalidation events from CONTRADICTS edges
    invalidation_events: List[str] = []
    for edge in edges:
        if edge.get("edge_type") == "CONTRADICTS":
            invalidation_events.append(edge["edge_id"])

    scenario = ScenarioResult(
        scenario_id=f"scenario_{strategy_result.strategy_id}_{direction.value}",
        claim=_build_claim(direction, nodes, edges),
        direction=direction,
        state=strategy_result.state,
        supporting=supporting,
        opposing=opposing,
        missing=missing,
        confirmation_events=confirmation_events,
        invalidation_events=invalidation_events,
        expiry_condition="8 completed bars without continuation" if strategy_result.state not in (
            TraderState.INVALIDATED, TraderState.EXPIRED, TraderState.NO_SETUP, TraderState.ABSTAIN
        ) else None,
        authority_status="research_observation",
    )
    scenarios.append(scenario)

    return scenarios


def _build_claim(direction: Direction, nodes: List[Dict], edges: List[Dict]) -> str:
    """Build a human-readable scenario claim."""
    breaks = [n for n in nodes if n.get("node_type") == "structure_break" and n.get("metadata", {}).get("confirmed")]
    fvgs = [n for n in nodes if n.get("node_type") == "fvg"]
    has_retrace = any(e.get("edge_type") == "RETRACES_WITHIN" for e in edges)
    has_contradiction = any(e.get("edge_type") == "CONTRADICTS" for e in edges)

    parts = []
    if direction != Direction.NEUTRAL:
        parts.append(f"{direction.value} structure detected")
    if breaks:
        parts.append(f"{len(breaks)} confirmed breaks")
    if fvgs:
        parts.append(f"{len(fvgs)} FVGs")
    if has_retrace:
        parts.append("LTF opposition is retracement within HTF structure")
    if has_contradiction:
        parts.append("genuine MTF contradiction detected")

    if not parts:
        return "No clear directional scenario"

    return ". ".join(parts) + "."
