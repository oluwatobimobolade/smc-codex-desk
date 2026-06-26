"""Current MTF graph — PEV2-driven, per-timeframe completeness, rich relationships.

This module replaces smc_desk.mtf.py in the active-authority pipeline.
It consumes PEV2 snapshots on each timeframe and builds a multi-timeframe
structural graph with:

1. Per-timeframe completeness tracking (bar count, latest candle, structure)
2. Rich relationship types that respect structural scope
3. Insufficient-history detection per timeframe
4. Conservative trading state (OBSERVE/WATCH/ABSTAIN)

Design principles:
- Lower-timeframe opposition is NOT automatically HTF contradiction.
  A 15m bullish BOS within 4H bearish structure is a RETRACEMENT.
- Direction alone is insufficient; structural scope matters.
- PROTECTED structure at HTF dominates LTF internal moves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TimeframeStatus:
    """Per-timeframe completeness and health."""

    timeframe: str
    available: bool
    bar_count: int
    latest_candle: str  # ISO
    has_structure: bool  # at least one break or protected level
    has_swings: bool
    has_fvgs: bool
    insufficient_history: bool  # too few bars for reliable structure
    missing: str  # empty string if present, reason if missing


@dataclass(frozen=True)
class MTFNode:
    node_id: str
    node_type: str  # "timeframe", "structure_break", "fvg", "swing"
    timeframe: str
    direction: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MTFEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str  # CONTAINS, REFINES, RETRACES_WITHIN, PROTECTS, ALIGNS_WITH, CONTRADICTS
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MTFState:
    decision: str  # OBSERVE, WATCH, ABSTAIN
    direction_bias: str
    confidence_note: str
    execution_blocked: bool


@dataclass(frozen=True)
class MTFGraph:
    nodes: list[MTFNode] = field(default_factory=list)
    edges: list[MTFEdge] = field(default_factory=list)
    timeframe_statuses: dict[str, TimeframeStatus] = field(default_factory=dict)
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
                {"node_id": n.node_id, "node_type": n.node_type,
                 "timeframe": n.timeframe, "direction": n.direction,
                 "metadata": n.metadata}
                for n in self.nodes
            ],
            "edges": [
                {"edge_id": e.edge_id, "source_node_id": e.source_node_id,
                 "target_node_id": e.target_node_id, "edge_type": e.edge_type,
                 "metadata": e.metadata}
                for e in self.edges
            ],
            "timeframe_statuses": {
                tf: {
                    "timeframe": ts.timeframe,
                    "available": ts.available,
                    "bar_count": ts.bar_count,
                    "latest_candle": ts.latest_candle,
                    "has_structure": ts.has_structure,
                    "has_swings": ts.has_swings,
                    "has_fvgs": ts.has_fvgs,
                    "insufficient_history": ts.insufficient_history,
                    "missing": ts.missing,
                }
                for tf, ts in self.timeframe_statuses.items()
            },
            "unresolved": self.unresolved_relationships,
            "state": {
                "decision": self.state.decision,
                "direction_bias": self.state.direction_bias,
                "confidence_note": self.state.confidence_note,
                "execution_blocked": self.state.execution_blocked,
            },
            "authority_sources": self.authority_sources,
        }


# Minimum bars required per timeframe for reliable structure detection
MIN_BARS = {"15m": 30, "1h": 20, "4h": 15, "1d": 10}

TIMEFRAME_ORDER = ["15m", "1h", "4h", "1d"]


def build_mtf_graph(
    snapshots: dict[str, Any],
    event_ledger: Any = None,
    *,
    decision_time: str = "",
    bar_counts: dict[str, int] | None = None,
) -> MTFGraph:
    """Build a multi-timeframe structural graph from PEV2 snapshots.

    Per-timeframe completeness is tracked. Structural scope determines
    whether lower-timeframe opposition is a contradiction or a retracement.
    """
    bar_counts = bar_counts or {}
    nodes: list[MTFNode] = []
    edges: list[MTFEdge] = []
    unresolved: list[str] = []
    timeframe_statuses: dict[str, TimeframeStatus] = {}

    # ── Phase 1: Per-timeframe completeness + nodes ──
    for tf in TIMEFRAME_ORDER:
        if tf not in snapshots:
            timeframe_statuses[tf] = TimeframeStatus(
                timeframe=tf, available=False, bar_count=0, latest_candle="",
                has_structure=False, has_swings=False, has_fvgs=False,
                insufficient_history=True, missing=f"no_snapshot_for_{tf}",
            )
            unresolved.append(f"missing_{tf}_snapshot")
            continue

        snapshot = snapshots[tf]
        bar_count = bar_counts.get(tf, 0)
        min_bars = MIN_BARS.get(tf, 20)
        insufficient_history = bar_count < min_bars

        # Extract data from snapshot or dict
        if isinstance(snapshot, dict):
            structure_state = snapshot.get("structure_state", {}) or {}
            current_dir = structure_state.get("current_direction", "neutral")
            ph = structure_state.get("protected_high_id")
            pl = structure_state.get("protected_low_id")
            breaks = snapshot.get("structure_breaks", [])
            fvgs_list = snapshot.get("fvgs", [])
            swings_dict = snapshot.get("swings", {})
            swing_count = (
                sum(len(v) for v in swings_dict.values())
                if isinstance(swings_dict, dict)
                else len(swings_dict) if isinstance(swings_dict, list)
                else 0
            )
            break_count = len(breaks) if isinstance(breaks, list) else 0
            fvg_count = len(fvgs_list) if isinstance(fvgs_list, list) else 0
            latest_candle = snapshot.get("latest_candle", decision_time)
        else:
            structure_state = snapshot.structure_state or {}
            current_dir = structure_state.get("current_direction", "neutral")
            ph = structure_state.get("protected_high_id")
            pl = structure_state.get("protected_low_id")
            breaks = snapshot.structure_breaks
            fvgs_list = snapshot.fvgs
            swings_dict = snapshot.swings
            swing_count = sum(len(swings) for swings in snapshot.swings.values())
            break_count = len(snapshot.structure_breaks)
            fvg_count = len(snapshot.fvgs)
            latest_candle = str(snapshot.decision_time)

        has_structure = bool(ph or pl or break_count > 0)
        has_swings = swing_count > 0
        has_fvgs = fvg_count > 0

        direction = current_dir if current_dir in ("bullish", "bearish") else "neutral"
        tf_node_id = f"tf_node_{tf}"

        if insufficient_history:
            unresolved.append(f"insufficient_history_{tf}_{bar_count}_bars_need_{min_bars}")

        timeframe_statuses[tf] = TimeframeStatus(
            timeframe=tf, available=True, bar_count=bar_count,
            latest_candle=latest_candle, has_structure=has_structure,
            has_swings=has_swings, has_fvgs=has_fvgs,
            insufficient_history=insufficient_history,
            missing="",
        )

        nodes.append(MTFNode(
            node_id=tf_node_id, node_type="timeframe", timeframe=tf,
            direction=direction,
            metadata={
                "swing_count": swing_count, "break_count": break_count,
                "fvg_count": fvg_count, "bar_count": bar_count,
                "protected_high": ph or "", "protected_low": pl or "",
                "decision_time": decision_time,
                "has_structure": has_structure,
                "insufficient_history": insufficient_history,
            },
        ))

        # Break nodes
        for brk in breaks:
            if isinstance(brk, dict):
                bid = f"break_{tf}_{brk.get('object_id', 'unknown')}"
                btype = "CHOCH" if brk.get("is_choch") else "BOS"
                bdir = str(brk.get("direction", "neutral"))
                ev = brk.get("evidence", {})
                bprice = str(ev.get("broken_price", ""))
                bconf = brk.get("confirmation_status") == "CONFIRMED"
            else:
                bid = f"break_{tf}_{brk.object_id}"
                btype = "CHOCH" if brk.is_choch else "BOS"
                bdir = str(brk.direction)
                bprice = str(brk.evidence.broken_price)
                bconf = brk.confirmation_status == "CONFIRMED"
            nodes.append(MTFNode(
                node_id=bid, node_type="structure_break", timeframe=tf,
                direction=bdir,
                metadata={"break_type": btype, "confirmed": bconf,
                          "broken_price": bprice},
            ))
            edges.append(MTFEdge(
                edge_id=f"edge_contains_{tf_node_id}_{bid}",
                source_node_id=tf_node_id, target_node_id=bid,
                edge_type="CONTAINS",
            ))

        # FVG nodes
        for fvg in fvgs_list:
            if isinstance(fvg, dict):
                fid = f"fvg_{tf}_{fvg.get('object_id', 'unknown')}"
                fdir = str(fvg.get("direction", "neutral"))
                fev = fvg.get("evidence", {})
                fgap = str(fev.get("gap_size_bps", ""))
                fmit = fev.get("is_mitigated_on_creation", False)
                fhi = str(fvg.get("price_high", ""))
                flo = str(fvg.get("price_low", ""))
            else:
                fid = f"fvg_{tf}_{fvg.object_id}"
                fdir = str(fvg.direction)
                fgap = str(fvg.evidence.gap_size_bps)
                fmit = fvg.evidence.is_mitigated_on_creation
                fhi = str(fvg.price_high)
                flo = str(fvg.price_low)
            nodes.append(MTFNode(
                node_id=fid, node_type="fvg", timeframe=tf, direction=fdir,
                metadata={"price_high": fhi, "price_low": flo,
                          "gap_size_bps": fgap, "mitigated": fmit},
            ))
            edges.append(MTFEdge(
                edge_id=f"edge_contains_{tf_node_id}_{fid}",
                source_node_id=tf_node_id, target_node_id=fid,
                edge_type="CONTAINS",
            ))

    # ── Phase 2: Cross-timeframe relationships ──
    for i in range(len(TIMEFRAME_ORDER)):
        for j in range(i + 1, len(TIMEFRAME_ORDER)):
            htf = TIMEFRAME_ORDER[j]
            ltf = TIMEFRAME_ORDER[i]
            hts = timeframe_statuses.get(htf)
            lts = timeframe_statuses.get(ltf)
            if not hts or not hts.available or not lts or not lts.available:
                continue

            htf_dir = _get_tf_direction(snapshots[htf])
            ltf_dir = _get_tf_direction(snapshots[ltf])
            htf_has_structure = hts.has_structure
            ltf_has_structure = lts.has_structure
            htf_protected = _has_protected(snapshots[htf])
            ltf_protected = _has_protected(snapshots[ltf])

            htf_node = f"tf_node_{htf}"
            ltf_node = f"tf_node_{ltf}"

            if htf_dir == ltf_dir and htf_dir != "neutral":
                # Same direction: ALIGNS_WITH
                edges.append(MTFEdge(
                    edge_id=f"edge_aligns_{ltf}_{htf}",
                    source_node_id=ltf_node, target_node_id=htf_node,
                    edge_type="ALIGNS_WITH",
                    metadata={"htf_dir": htf_dir, "ltf_dir": ltf_dir},
                ))
            elif htf_dir != "neutral" and ltf_dir != "neutral":
                # Opposite directions. Is this a contradiction or a retracement?
                # If HTF has protected structure and LTF doesn't break it,
                # this is a RETRACEMENT, not a contradiction.
                if htf_protected and ltf_has_structure:
                    # LTF move is contained within HTF structure
                    edges.append(MTFEdge(
                        edge_id=f"edge_retraces_{ltf}_{htf}",
                        source_node_id=ltf_node, target_node_id=htf_node,
                        edge_type="RETRACES_WITHIN",
                        metadata={
                            "htf_dir": htf_dir, "ltf_dir": ltf_dir,
                            "reason": "ltf_opposition_is_retracement_not_contradiction",
                            "htf_protected": htf_protected,
                        },
                    ))
                else:
                    edges.append(MTFEdge(
                        edge_id=f"edge_contradicts_{ltf}_{htf}",
                        source_node_id=ltf_node, target_node_id=htf_node,
                        edge_type="CONTRADICTS",
                        metadata={"htf_dir": htf_dir, "ltf_dir": ltf_dir},
                    ))
                    unresolved.append(
                        f"genuine_contradiction_{ltf}_{ltf_dir}_vs_{htf}_{htf_dir}"
                    )
            elif htf_dir == "neutral" or ltf_dir == "neutral":
                # One timeframe neutral: REFINES
                edges.append(MTFEdge(
                    edge_id=f"edge_refines_{ltf}_{htf}",
                    source_node_id=ltf_node, target_node_id=htf_node,
                    edge_type="REFINES",
                ))

            # PROTECTS: HTF protected level protects LTF structure
            if _has_protected(snapshots[htf]):
                edges.append(MTFEdge(
                    edge_id=f"edge_protects_{htf}_{ltf}",
                    source_node_id=f"tf_node_{htf}",
                    target_node_id=f"tf_node_{ltf}",
                    edge_type="PROTECTS",
                    metadata={"htf_protected": True},
                ))

    # ── Phase 3: Derive state ──
    state = _derive_state(timeframe_statuses, snapshots, unresolved)

    available_tfs = [t for t in TIMEFRAME_ORDER if timeframe_statuses.get(t) and timeframe_statuses[t].available]

    return MTFGraph(
        nodes=nodes, edges=edges,
        timeframe_statuses=timeframe_statuses,
        unresolved_relationships=unresolved,
        state=state,
        authority_sources=[
            "perception_engine_v2",
            "event_ledger",
            "mtf_current_v2",
            f"timeframes: {','.join(sorted(available_tfs))}",
        ],
    )


def _has_protected(snapshot) -> bool:
    """Check if the snapshot has any protected structure."""
    if isinstance(snapshot, dict):
        state = snapshot.get("structure_state", {}) or {}
    else:
        state = snapshot.structure_state or {}
    return bool(state.get("protected_high_id") or state.get("protected_low_id"))


def _get_tf_direction(snapshot) -> str:
    """Extract the directional bias from a PEV2 snapshot or dict."""
    if isinstance(snapshot, dict):
        state = snapshot.get("structure_state", {}) or {}
    else:
        state = snapshot.structure_state or {}
    direction = state.get("current_direction", "neutral")
    return direction if direction in ("bullish", "bearish") else "neutral"


def _derive_state(
    timeframe_statuses: dict[str, TimeframeStatus],
    snapshots: dict,
    unresolved: list[str],
) -> MTFState:
    """Derive conservative trading state considering per-timeframe health."""
    available = {t for t, ts in timeframe_statuses.items() if ts.available}
    has_structure = {t for t, ts in timeframe_statuses.items() if ts.has_structure}
    insufficient = {t for t, ts in timeframe_statuses.items()
                    if ts.insufficient_history and ts.available}

    if not available:
        return MTFState("ABSTAIN", "insufficient_history",
                        "no_timeframe_data_available", True)
    if len(available) < 2:
        return MTFState("ABSTAIN", "insufficient_history",
                        f"only_{len(available)}_timeframes", True)
    if insufficient:
        tfs = ",".join(sorted(insufficient))
        return MTFState("ABSTAIN", "insufficient_history",
                        f"insufficient_bars_on_{tfs}", True)

    # Genuine contradictions (not retracements)
    blocking = [r for r in unresolved if r.startswith("genuine_contradiction")]
    if blocking:
        return MTFState("ABSTAIN", "contested",
                        "genuine_directional_contradictions", True)

    # Collect directions from timeframes with structure
    bias_dirs = []
    for tf in TIMEFRAME_ORDER:
        if tf in snapshots:
            d = _get_tf_direction(snapshots[tf])
            if d != "neutral":
                bias_dirs.append(d)

    if not bias_dirs:
        return MTFState("OBSERVE", "neutral",
                        "no_clear_directional_bias", True)

    # All non-neutral directions agree
    consensus = list(set(bias_dirs))
    if len(consensus) == 1 and len(bias_dirs) >= 2:
        return MTFState("WATCH", consensus[0],
                        "mtf_aligned_no_certified_strategy", True)

    return MTFState("OBSERVE", "mixed",
                    "ambiguous_mtf_state", True)
