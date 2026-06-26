"""Stage 12 audit: End-to-end replay.

Verifies that the complete pipeline produces byte-identical output when
run twice from the same starting state. Covers: PEV2 → event ledger →
MTF graph → decision pipeline.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smc_desk.colleague.event_ledger import EventLedger
from smc_desk.mtf_current import build_mtf_graph
from smc_desk.decision.contracts import Direction
from smc_desk.decision.state_engine import StateEngine
from smc_desk.decision.scenario_builder import build_decision_envelope
from smc_desk.perception.engine_v2 import PerceptionSnapshot


def _make_snapshot(tf: str = "15m") -> PerceptionSnapshot:
    return PerceptionSnapshot(
        decision_time=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        swings={},
        structure_state={"current_direction": "bullish"},
        structure_breaks=[],
        fvgs=[],
    )


def _run_pipeline(snapshots: dict) -> dict:
    """Run the full PEV2 → ledger → MTF → decision pipeline once."""
    ledger = EventLedger(
        events=[], decision_time=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        ontology_version="2.0.0",
    )
    graph = build_mtf_graph(
        snapshots, ledger,
        bar_counts={"15m": 100, "1h": 25, "4h": 20, "1d": 15},
    )
    engine = StateEngine()
    state = engine.evaluate(
        {"SWING_CONFIRMED", "STRUCTURE_BREAK_CANDIDATE"},
        {"mtf_graph_valid", "dual_timeframe_aligned"},
        direction=Direction.BULLISH,
        timestamp=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )
    envelope = build_decision_envelope(state, graph.to_dict())
    return {
        "graph": graph.to_dict(),
        "state": state.state.value,
        "decision": envelope.decision.value,
    }


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


class TestEndToEndReplay:
    """Stage 12: End-to-end deterministic replay."""

    def test_pipeline_run_twice_produces_identical_output(self):
        snapshots = {
            "15m": _make_snapshot("15m"),
            "1h": _make_snapshot("1h"),
            "4h": _make_snapshot("4h"),
            "1d": _make_snapshot("1d"),
        }
        run1 = _run_pipeline(snapshots)
        run2 = _run_pipeline(snapshots)
        assert _canonical_json(run1) == _canonical_json(run2)

    def test_empty_input_produces_abstain(self):
        run = _run_pipeline({})
        assert run["decision"] == "ABSTAIN"

    def test_single_timeframe_produces_abstain(self):
        run = _run_pipeline({"15m": _make_snapshot()})
        assert run["decision"] == "ABSTAIN"

    def test_decision_never_execute(self):
        for direction in Direction:
            snapshots = {"15m": _make_snapshot(), "1h": _make_snapshot()}
            run = _run_pipeline(snapshots)
            assert run["decision"] in ("ABSTAIN", "OBSERVE", "WATCH")
            assert run["decision"] != "PAPER_EXECUTE"
            assert run["decision"] != "EXECUTE"
            assert run["decision"] != "LIVE_EXECUTE"

    def test_pipeline_deterministic_across_restarts(self):
        """Simulate restart: reset all state, rerun, must produce same output."""
        snapshots = {"15m": _make_snapshot(), "1h": _make_snapshot()}
        run1 = _run_pipeline(snapshots)
        # "Restart" — fresh objects
        run2 = _run_pipeline(snapshots)
        assert _canonical_json(run1) == _canonical_json(run2)
