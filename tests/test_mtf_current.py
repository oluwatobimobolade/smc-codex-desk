"""Tests for smc_desk.mtf_current — PEV2-driven MTF graph."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.mtf_current import (
    MTFGraph,
    MTFState,
    build_mtf_graph,
)
from smc_desk.colleague.event_ledger import EventLedger
from smc_desk.perception.engine_v2 import PerceptionSnapshot


def _make_empty_snapshot(tf: str = "15m") -> PerceptionSnapshot:
    return PerceptionSnapshot(
        decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        swings={},
        structure_state={},
        structure_breaks=[],
        fvgs=[],
    )


def _make_snapshot_with_bias(
    direction: str, tf: str = "15m"
) -> PerceptionSnapshot:
    return PerceptionSnapshot(
        decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        swings={},
        structure_state={"current_direction": direction},
        structure_breaks=[],
        fvgs=[],
    )


class TestMTFGraphBuilding:
    def test_empty_input_abstains(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        graph = build_mtf_graph({}, ledger)
        assert graph.state.decision == "ABSTAIN"
        assert graph.state.execution_blocked is True

    def test_single_timeframe_abstains(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {"15m": _make_empty_snapshot()}
        graph = build_mtf_graph(snapshots, ledger)
        assert graph.state.decision == "ABSTAIN"
        assert "insufficient_timeframe_coverage" in graph.state.confidence_note

    def test_neutral_all_observes(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {
            "15m": _make_empty_snapshot("15m"),
            "1h": _make_empty_snapshot("1h"),
        }
        graph = build_mtf_graph(snapshots, ledger)
        assert graph.state.decision == "OBSERVE"

    def test_aligned_bullish_watches(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {
            "15m": _make_snapshot_with_bias("bullish", "15m"),
            "1h": _make_snapshot_with_bias("bullish", "1h"),
            "4h": _make_snapshot_with_bias("bullish", "4h"),
        }
        graph = build_mtf_graph(snapshots, ledger)
        assert graph.state.decision == "WATCH"
        assert graph.state.direction_bias == "bullish"
        assert graph.state.execution_blocked is True

    def test_contradicting_timeframes_abstain(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {
            "15m": _make_snapshot_with_bias("bullish", "15m"),
            "4h": _make_snapshot_with_bias("bearish", "4h"),
        }
        graph = build_mtf_graph(snapshots, ledger)
        assert graph.state.decision == "ABSTAIN"
        assert "directional_conflict" in " ".join(graph.unresolved_relationships).lower()

    def test_graph_has_nodes_and_edges(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {
            "15m": _make_snapshot_with_bias("bullish", "15m"),
            "1h": _make_snapshot_with_bias("bullish", "1h"),
        }
        graph = build_mtf_graph(snapshots, ledger)
        assert len(graph.nodes) >= 2  # at least 15m + 1h timeframe nodes
        assert any(n.node_id == "tf_node_15m" for n in graph.nodes)
        assert any(n.node_id == "tf_node_1h" for n in graph.nodes)

    def test_graph_serializes(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {"15m": _make_empty_snapshot()}
        graph = build_mtf_graph(snapshots, ledger)
        payload = graph.to_dict()
        assert "nodes" in payload
        assert "edges" in payload
        assert "state" in payload
        assert payload["state"]["execution_blocked"] is True

    def test_deterministic_output(self):
        ledger = EventLedger(
            events=[],
            decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            ontology_version="2.0.0",
        )
        snapshots = {
            "15m": _make_snapshot_with_bias("bullish", "15m"),
            "1h": _make_snapshot_with_bias("bullish", "1h"),
        }
        g1 = build_mtf_graph(snapshots, ledger)
        g2 = build_mtf_graph(snapshots, ledger)
        assert g1.to_dict() == g2.to_dict()
