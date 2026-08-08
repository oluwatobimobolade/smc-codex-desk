from __future__ import annotations

import pandas as pd

from smc_desk.perception.formal_causal_episode_graph import (
    build_formal_causal_episode_graph,
    episode_graph_failure_codes,
)
from smc_desk.perception.structure_engine_v3 import StructureEngineV3Shadow


def _df(*, weak: bool = False) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=24, freq="15min", tz="UTC")
    rows = []
    for index, timestamp in enumerate(timestamps):
        if index < 10:
            open_, high, low, close = 99.4, 99.8, 99.1, 99.5
        elif index == 10:
            if weak:
                open_, high, low, close = 99.99, 100.06, 99.98, 100.02
            else:
                open_, high, low, close = 99.5, 100.8, 99.4, 100.7
        else:
            open_, high, low, close = 100.6, 101.1, 100.3, 100.8
        rows.append({"timestamp": timestamp, "open": open_, "high": high, "low": low, "close": close, "volume": 1000.0})
    return pd.DataFrame(rows)


def _payload() -> dict:
    return {
        "swings": [
            {
                "object_id": "swing-high-1",
                "object_type": "swing",
                "pivot_time": "2026-01-01T01:00:00Z",
                "candidate_at": "2026-01-01T01:00:00Z",
                "confirmed_at": "2026-01-01T01:30:00Z",
                "price_high": 100.0,
                "price_low": 99.5,
                "evidence": {"scale_name": "external"},
            }
        ],
        "structure_breaks": [
            {
                "object_id": "break-1",
                "object_type": "structure_break",
                "timeframe": "15m",
                "direction": "bullish",
                "structure_scope": "external",
                "break_type": "BOS",
                "candidate_at": "2026-01-01T02:30:00Z",
                "confirmed_at": "2026-01-01T02:45:00Z",
                "confirmation_status": "confirmed",
                "price_low": 99.4,
                "price_high": 100.8,
                "evidence": {
                    "broken_swing_id": "swing-high-1",
                    "broken_price": 100.0,
                    "structure_scope": "external",
                    "broke_protected_swing": False,
                },
            }
        ],
        "order_blocks": [],
        "fvgs": [],
        "poi_grade_fvgs": [],
        "sweeps": [],
        "inducements": [],
        "liquidity_levels": [],
    }


def _v1_graph() -> dict:
    return {
        "schema": "formal_mtf_structure_graph_v1",
        "timeframes": {
            "15m": {
                "latest_external_break": {"object_id": "break-1"},
                "latest_internal_break": None,
            }
        },
        "parent_child_context": {"status": "INSUFFICIENT_CONTEXT", "has_conflict": False},
        "active_range": {"status": "RESOLVED", "high": 105.0, "low": 95.0},
    }


def _poi_authority() -> dict:
    return {
        "scenarios": {
            "bullish": {
                "status": "SELECTED",
                "accepted_break_id": "break-1",
                "primary_causal_poi": {
                    "poi_id": "15m:order_block:ob-1",
                    "source_object_id": "ob-1",
                    "timeframe": "15m",
                    "kind": "order_block",
                    "direction": "bullish",
                    "poi_role": "primary_causal_poi",
                    "causal_status": "ELIGIBLE_CAUSAL_OB",
                    "linked_break_id": "break-1",
                    "price_low": 98.8,
                    "price_high": 99.6,
                    "origin_time": "2026-01-01T01:45:00Z",
                    "freshness": "fresh",
                },
                "secondary_reaction_pois": [],
                "execution_refinements": [],
                "inducement_candidates": [],
            }
        }
    }


def test_v3_shadow_relabels_first_accepted_break_and_builds_causal_episode():
    df = _df()
    shadow = StructureEngineV3Shadow().analyze(
        symbol="TESTUSDT",
        detector_candidates={"15m": _payload()},
        timeframe_dfs={"15m": df},
        decision_time="2026-01-01T06:00:00Z",
    ).to_dict()

    event = shadow["timeframes"]["15m"]["events"][0]
    assert event["event_type"] == "INITIAL_DIRECTION_BREAK"
    assert event["accepted_for_shadow_story"] is True

    graph = build_formal_causal_episode_graph(
        symbol="TESTUSDT",
        decision_time="2026-01-01T06:00:00Z",
        detector_candidates={"15m": _payload()},
        structure_shadow=shadow,
        formal_structure_graph_v1=_v1_graph(),
        causal_poi_authority=_poi_authority(),
    )

    assert graph["invariants"]["status"] == "PASS"
    episode = graph["timeframes"]["15m"]["latest_external_episode"]
    assert episode["structure_event_id"] == "break-1"
    assert episode["protected_origin"]["price"] == 98.8
    assert any(edge["relation"] == "originates" for edge in graph["edges"])
    assert graph["authority_contract"]["signal_allowed"] is False


def test_v3_shadow_challenges_weak_v1_break_and_graph_requires_review():
    shadow = StructureEngineV3Shadow().analyze(
        symbol="TESTUSDT",
        detector_candidates={"15m": _payload()},
        timeframe_dfs={"15m": _df(weak=True)},
        decision_time="2026-01-01T06:00:00Z",
    ).to_dict()
    graph = build_formal_causal_episode_graph(
        symbol="TESTUSDT",
        decision_time="2026-01-01T06:00:00Z",
        detector_candidates={"15m": _payload()},
        structure_shadow=shadow,
        formal_structure_graph_v1=_v1_graph(),
        causal_poi_authority=_poi_authority(),
    )

    assert graph["invariants"]["status"] == "REVIEW_REQUIRED"
    assert "15m_v1_controlling_external_break_survives_v3" in episode_graph_failure_codes(graph)
    assert "bullish_primary_poi_links_v3_accepted_break" in episode_graph_failure_codes(graph)
    assert graph["current_story"]["status"] == "INCOMPLETE"
