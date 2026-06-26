"""Tests for smc_desk.mtf_current — PEV2-driven MTF graph."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _default_bar_counts() -> dict[str, int]:
    return {"15m": 100, "1h": 25, "4h": 20, "1d": 15}

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
            events=[], decision_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), ontology_version="2.0.0",
        )
        snapshots = {"15m": _make_empty_snapshot()}
        graph = build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
        assert graph.state.decision == "ABSTAIN"
        assert "no_timeframe" in graph.state.confidence_note or "only_1" in graph.state.confidence_note

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
        graph =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
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
        graph =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
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
        graph =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
        assert graph.state.decision == "ABSTAIN"
        assert any("contradiction" in r.lower() for r in graph.unresolved_relationships)

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
        graph =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
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
        graph =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
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
        g1 =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
        g2 =     build_mtf_graph(snapshots, ledger, bar_counts=_default_bar_counts())
        assert g1.to_dict() == g2.to_dict()
