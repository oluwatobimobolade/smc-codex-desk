"""Current MTF graph — PEV2-driven, no legacy dependency.

This module replaces smc_desk.mtf.py in the active-authority pipeline.
It consumes PEV2 snapshots on each timeframe and the event ledger to build
a structural graph. It does not import or call the legacy engine.

Output: MTFGraph with nodes, edges, and a conservative trading state
(OBSERVE, WATCH, ABSTAIN). No PAPER_EXECUTE until a certified strategy
runtime exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from smc_desk.colleague.event_ledger import EventLedger
from smc_desk.perception.engine_v2 import PerceptionSnapshot


@dataclass(frozen=True)
class MTFNode:
    """A node in the multi-timeframe structural graph."""

    node_id: str
    node_type: str  # "timeframe", "structure_break", "fvg", "swing", "regime"
    timeframe: str  # "15m", "1h", "4h", "1d"
    direction: str  # "bullish", "bearish", "neutral"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MTFEdge:
    """A directed relationship between two MTF nodes."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str  # CONTAINS, REFINES, ALIGNS_WITH, CONTRADICTS, INVALIDATES
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MTFState:
    """Conservative trading state from MTF analysis.

    Outputs are intentionally limited: no PAPER_EXECUTE until a certified
    strategy runtime exists.
    """

    decision: str  # OBSERVE, WATCH, ABSTAIN
    direction_bias: str  # bullish, bearish, neutral, insufficient_history
    confidence_note: str
    execution_blocked: bool


@dataclass(frozen=True)
class MTFGraph:
    """Multi-timeframe structural graph from PEV2 snapshots."""

    nodes: list[MTFNode] = field(default_factory=list)
    edges: list[MTFEdge] = field(default_factory=list)
    unresolved_relationships: list[str] = field(default_factory=list)
    state: MTFState = field(
        default_factory=lambda: MTFState(
            decision="ABSTAIN",
            direction_bias="neutral",
            confidence_note="no_strategy_runtime_active",
            execution_blocked=True,
        )
    )
    authority_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "timeframe": n.timeframe,
                    "direction": n.direction,
                    "metadata": n.metadata,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "edge_id": e.edge_id,
                    "source_node_id": e.source_node_id,
                    "target_node_id": e.target_node_id,
                    "edge_type": e.edge_type,
                    "metadata": e.metadata,
                }
                for e in self.edges
            ],
            "unresolved": self.unresolved_relationships,
            "state": {
                "decision": self.state.decision,
                "direction_bias": self.state.direction_bias,
                "confidence_note": self.state.confidence_note,
                "execution_blocked": self.state.execution_blocked,
            },
            "authority_sources": self.authority_sources,
        }


def build_mtf_graph(
    snapshots: dict[str, PerceptionSnapshot],
    event_ledger: EventLedger,
    *,
    decision_time: str = "",
) -> MTFGraph:
    """Build a multi-timeframe structural graph from PEV2 snapshots.

    This is the CURRENT authority path. It does not import or call the
    legacy engine. It produces conservative output only.

    Args:
        snapshots: PEV2 snapshots keyed by timeframe ("15m", "1h", "4h", "1d").
        event_ledger: The canonical event ledger for temporal context.
        decision_time: ISO timestamp for provenance.

    Returns:
        MTFGraph with nodes, edges, and a conservative state.
    """
    timeframe_order = ["15m", "1h", "4h", "1d"]
    nodes: list[MTFNode] = []
    edges: list[MTFEdge] = []
    unresolved: list[str] = []

    # Track which timeframes have data
    available_timeframes: set[str] = set()

    for tf in timeframe_order:
        if tf not in snapshots:
            unresolved.append(f"missing_{tf}_snapshot")
            continue
        snapshot = snapshots[tf]
        available_timeframes.add(tf)

        # Accept both PerceptionSnapshot objects and dicts
        if isinstance(snapshot, dict):
            structure_state = snapshot.get("structure_state", {}) or {}
            current_direction = structure_state.get("current_direction", "neutral")
            protected_high = structure_state.get("protected_high_id")
            protected_low = structure_state.get("protected_low_id")
            breaks = snapshot.get("structure_breaks", [])
            fvgs_list = snapshot.get("fvgs", [])
            swings_dict = snapshot.get("swings", {})
            swing_count = sum(len(v) for v in swings_dict.values()) if isinstance(swings_dict, dict) else len(swings_dict) if isinstance(swings_dict, list) else 0
            break_count = len(breaks) if isinstance(breaks, list) else 0
            fvg_count = len(fvgs_list) if isinstance(fvgs_list, list) else 0
        else:
            structure_state = snapshot.structure_state or {}
            current_direction = structure_state.get("current_direction", "neutral")
            protected_high = structure_state.get("protected_high_id")
            protected_low = structure_state.get("protected_low_id")
            breaks = snapshot.structure_breaks
            fvgs_list = snapshot.fvgs
            swings_dict = snapshot.swings
            swing_count = sum(len(swings) for swings in snapshot.swings.values())
            break_count = len(snapshot.structure_breaks)
            fvg_count = len(snapshot.fvgs)

        tf_node_id = f"tf_node_{tf}"
        nodes.append(
            MTFNode(
                node_id=tf_node_id,
                node_type="timeframe",
                timeframe=tf,
                direction=current_direction if current_direction in ("bullish", "bearish") else "neutral",
                metadata={
                    "swing_count": swing_count,
                    "break_count": break_count,
                    "fvg_count": fvg_count,
                    "protected_high": protected_high or "",
                    "protected_low": protected_low or "",
                    "decision_time": decision_time,
                },
            )
        )

        # Create structure break nodes
        for brk in breaks:
            if isinstance(brk, dict):
                brk_node_id = f"break_{tf}_{brk.get('object_id', 'unknown')}"
                break_type = "CHOCH" if brk.get("is_choch") else "BOS"
                direction = str(brk.get("direction", "neutral"))
                evidence = brk.get("evidence", {})
                broken_price = str(evidence.get("broken_price", ""))
                confirmed = brk.get("confirmation_status") == "CONFIRMED"
            else:
                brk_node_id = f"break_{tf}_{brk.object_id}"
                break_type = "CHOCH" if brk.is_choch else "BOS"
                direction = str(brk.direction)
                broken_price = str(brk.evidence.broken_price)
                confirmed = brk.confirmation_status == "CONFIRMED"
            nodes.append(
                MTFNode(
                    node_id=brk_node_id,
                    node_type="structure_break",
                    timeframe=tf,
                    direction=direction,
                    metadata={
                        "break_type": break_type,
                        "confirmed": confirmed,
                        "broken_price": broken_price,
                    },
                )
            )
            # Edge: timeframe CONTAINS this break
            edges.append(
                MTFEdge(
                    edge_id=f"edge_contains_{tf_node_id}_{brk_node_id}",
                    source_node_id=tf_node_id,
                    target_node_id=brk_node_id,
                    edge_type="CONTAINS",
                )
            )

        # Create FVG nodes
        for fvg in fvgs_list:
            if isinstance(fvg, dict):
                fvg_node_id = f"fvg_{tf}_{fvg.get('object_id', 'unknown')}"
                fvg_dir = str(fvg.get("direction", "neutral"))
                fvg_evidence = fvg.get("evidence", {})
                fvg_gap = str(fvg_evidence.get("gap_size_bps", ""))
                fvg_mitigated = fvg_evidence.get("is_mitigated_on_creation", False)
                fvg_high = str(fvg.get("price_high", ""))
                fvg_low = str(fvg.get("price_low", ""))
            else:
                fvg_node_id = f"fvg_{tf}_{fvg.object_id}"
                fvg_dir = str(fvg.direction)
                fvg_gap = str(fvg.evidence.gap_size_bps)
                fvg_mitigated = fvg.evidence.is_mitigated_on_creation
                fvg_high = str(fvg.price_high)
                fvg_low = str(fvg.price_low)
            nodes.append(
                MTFNode(
                    node_id=fvg_node_id,
                    node_type="fvg",
                    timeframe=tf,
                    direction=fvg_dir,
                    metadata={
                        "price_high": fvg_high,
                        "price_low": fvg_low,
                        "gap_size_bps": fvg_gap,
                        "mitigated": fvg_mitigated,
                    },
                )
            )
            edges.append(
                MTFEdge(
                    edge_id=f"edge_contains_{tf_node_id}_{fvg_node_id}",
                    source_node_id=tf_node_id,
                    target_node_id=fvg_node_id,
                    edge_type="CONTAINS",
                )
            )

    # Build cross-timeframe alignment edges
    for i in range(len(timeframe_order)):
        for j in range(i + 1, len(timeframe_order)):
            htf = timeframe_order[j]
            ltf = timeframe_order[i]
            if htf not in available_timeframes or ltf not in available_timeframes:
                continue

            htf_dir = _get_tf_direction(snapshots[htf])
            ltf_dir = _get_tf_direction(snapshots[ltf])

            if htf_dir == ltf_dir:
                edges.append(
                    MTFEdge(
                        edge_id=f"edge_aligns_{ltf}_{htf}",
                        source_node_id=f"tf_node_{ltf}",
                        target_node_id=f"tf_node_{htf}",
                        edge_type="ALIGNS_WITH",
                    )
                )
            elif htf_dir != "neutral" and ltf_dir != "neutral":
                edges.append(
                    MTFEdge(
                        edge_id=f"edge_contradicts_{ltf}_{htf}",
                        source_node_id=f"tf_node_{ltf}",
                        target_node_id=f"tf_node_{htf}",
                        edge_type="CONTRADICTS",
                    )
                )
                unresolved.append(f"directional_conflict_{ltf}_{ltf_dir}_vs_{htf}_{htf_dir}")

    # Determine state
    state = _derive_state(snapshots, available_timeframes, unresolved)

    return MTFGraph(
        nodes=nodes,
        edges=edges,
        unresolved_relationships=unresolved,
        state=state,
        authority_sources=[
            "perception_engine_v2",
            "event_ledger",
            "mtf_current_v1",
            f"timeframes: {','.join(sorted(available_timeframes))}",
        ],
    )


def _get_tf_direction(snapshot) -> str:
    """Extract the directional bias from a PEV2 snapshot or dict."""
    if isinstance(snapshot, dict):
        state = snapshot.get("structure_state", {}) or {}
    else:
        state = snapshot.structure_state or {}
    direction = state.get("current_direction", "neutral")
    return direction if direction in ("bullish", "bearish") else "neutral"


def _derive_state(
    snapshots: dict[str, PerceptionSnapshot],
    available_timeframes: set[str],
    unresolved: list[str],
) -> MTFState:
    """Derive a conservative trading state. No PAPER_EXECUTE."""
    if not available_timeframes:
        return MTFState(
            decision="ABSTAIN",
            direction_bias="insufficient_history",
            confidence_note="no_timeframe_data_available",
            execution_blocked=True,
        )

    if len(available_timeframes) < 2:
        return MTFState(
            decision="ABSTAIN",
            direction_bias="insufficient_history",
            confidence_note="insufficient_timeframe_coverage",
            execution_blocked=True,
        )

    # Check for structural conflicts (not missing timeframes).
    blocking_conflicts = [
        r for r in unresolved
        if r.startswith("directional_conflict") or r.startswith("stale")
    ]
    if blocking_conflicts:
        return MTFState(
            decision="ABSTAIN",
            direction_bias="contested",
            confidence_note="directional_conflicts_detected",
            execution_blocked=True,
        )

    # Check directions across all available timeframes.
    directions = {
        tf: _get_tf_direction(snapshots[tf])
        for tf in available_timeframes
        if tf in snapshots
    }

    bias_dirs = [d for d in directions.values() if d != "neutral"]
    if not bias_dirs:
        return MTFState(
            decision="OBSERVE",
            direction_bias="neutral",
            confidence_note="no_clear_directional_bias",
            execution_blocked=True,
        )

    # All non-neutral directions agree
    consensus = list(set(bias_dirs))
    if len(consensus) == 1 and len(bias_dirs) >= 2:
        return MTFState(
            decision="WATCH",
            direction_bias=consensus[0],
            confidence_note="mtf_aligned_no_certified_strategy",
            execution_blocked=True,
        )

    return MTFState(
        decision="OBSERVE",
        direction_bias="mixed",
        confidence_note="ambiguous_mtf_state",
        execution_blocked=True,
    )
