from __future__ import annotations

import pandas as pd

from smc_desk.colleague.smc_thesis_ai_v1 import _format_scenario_watch_pois
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


def _two_stage_mss_fixture(*, reclaim: bool = False) -> tuple[pd.DataFrame, dict]:
    timestamps = pd.date_range("2026-02-01", periods=42, freq="15min", tz="UTC")
    rows = []
    for index, timestamp in enumerate(timestamps):
        if index < 8:
            open_, high, low, close = 99.5, 99.8, 99.2, 99.6
        elif index == 8:  # initial accepted bullish direction
            open_, high, low, close = 99.6, 100.9, 99.5, 100.7
        elif index < 20:
            open_, high, low, close = 100.6, 101.0, 100.2, 100.7
        elif index == 20:  # protected low body-closes, but body ratio is weak
            open_, high, low, close = 99.2, 99.3, 98.4, 98.8
        elif reclaim and index == 25:
            open_, high, low, close = 98.8, 99.4, 98.7, 99.2
        elif index < 30:
            open_, high, low, close = 98.75, 98.95, 98.3, 98.7
        elif index == 30:  # independently strong second external displacement
            open_, high, low, close = 98.5, 98.6, 97.0, 97.2
        else:
            open_, high, low, close = 97.2, 97.5, 96.8, 97.0
        rows.append(
            {
                "timestamp": timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
            }
        )
    payload = {
        "swings": [
            {
                "object_id": "initial-high",
                "pivot_time": timestamps[2].isoformat(),
                "confirmed_at": timestamps[5].isoformat(),
                "price_high": 100.0,
                "price_low": 99.6,
                "evidence": {"scale_name": "external"},
            },
            {
                "object_id": "protected-low",
                "pivot_time": timestamps[10].isoformat(),
                "confirmed_at": timestamps[13].isoformat(),
                "price_high": 99.4,
                "price_low": 99.0,
                "evidence": {"scale_name": "external"},
            },
            {
                "object_id": "followup-low",
                "pivot_time": timestamps[22].isoformat(),
                "confirmed_at": timestamps[25].isoformat(),
                "price_high": 98.3,
                "price_low": 98.0,
                "evidence": {"scale_name": "external"},
            },
        ],
        "structure_breaks": [
            {
                "object_id": "initial-bullish",
                "timeframe": "15m",
                "direction": "bullish",
                "structure_scope": "external",
                "break_type": "BOS",
                "candidate_at": timestamps[8].isoformat(),
                "confirmed_at": (timestamps[8] + pd.Timedelta(minutes=15)).isoformat(),
                "confirmation_status": "confirmed",
                "evidence": {
                    "broken_swing_id": "initial-high",
                    "broken_price": 100.0,
                    "structure_scope": "external",
                    "broke_protected_swing": False,
                },
            },
            {
                "object_id": "weak-protected-break",
                "timeframe": "15m",
                "direction": "bearish",
                "structure_scope": "external",
                "break_type": "CHOCH",
                "candidate_at": timestamps[20].isoformat(),
                "confirmed_at": (timestamps[20] + pd.Timedelta(minutes=15)).isoformat(),
                "confirmation_status": "confirmed",
                "evidence": {
                    "broken_swing_id": "protected-low",
                    "protected_swing_id": "protected-low",
                    "broken_price": 99.0,
                    "structure_scope": "external",
                    "broke_protected_swing": True,
                },
            },
            {
                "object_id": "strong-followup-break",
                "timeframe": "15m",
                "direction": "bearish",
                "structure_scope": "external",
                "break_type": "BOS",
                "candidate_at": timestamps[30].isoformat(),
                "confirmed_at": (timestamps[30] + pd.Timedelta(minutes=15)).isoformat(),
                "confirmation_status": "confirmed",
                "evidence": {
                    "broken_swing_id": "followup-low",
                    "broken_price": 98.0,
                    "structure_scope": "external",
                    "broke_protected_swing": False,
                },
            },
        ],
        "order_blocks": [],
        "fvgs": [],
        "poi_grade_fvgs": [],
        "sweeps": [],
        "inducements": [],
        "liquidity_levels": [],
    }
    return pd.DataFrame(rows), payload


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


def test_v3_acceptance_is_bound_to_source_candidate_body_close() -> None:
    payload = _payload()
    payload["structure_breaks"][0]["confirmed_at"] = "2026-01-01T03:00:00Z"

    shadow = StructureEngineV3Shadow().analyze(
        symbol="TESTUSDT",
        detector_candidates={"15m": payload},
        timeframe_dfs={"15m": _df()},
        decision_time="2026-01-01T06:00:00Z",
    ).to_dict()
    event = shadow["timeframes"]["15m"]["events"][0]

    assert event["source_binding_matches"] is False
    assert event["event_type"] == "SOURCE_BINDING_MISMATCH"
    assert event["accepted_for_shadow_story"] is False
    assert "replayed_body_close_does_not_match_source_confirmed_at" in event["reasons"]


def test_v3_acceptance_is_scoped_to_native_timeframe() -> None:
    shared_id = "break-shared"
    payload = _payload()
    payload["structure_breaks"][0]["object_id"] = shared_id
    accepted_event = {
        "source_break_object_id": shared_id,
        "accepted_for_shadow_story": True,
        "scope": "external",
        "direction": "bullish",
        "event_type": "INITIAL_DIRECTION_BREAK",
        "lifecycle_state": "ACCEPTED_BREAKOUT",
        "broken_swing_id": "swing-high-1",
        "broken_level_price": 100.0,
        "body_close_time": "2026-01-01T02:45:00Z",
        "confirmation_time": "2026-01-01T03:15:00Z",
        "displacement_score": 1.0,
    }
    rejected_event = {
        **accepted_event,
        "accepted_for_shadow_story": False,
        "event_type": "FAILED_BREAKOUT",
        "lifecycle_state": "FAILED_BREAKOUT",
        "reasons": ["confirmation_horizon_expired_without_acceptance"],
    }
    graph = build_formal_causal_episode_graph(
        symbol="TESTUSDT",
        decision_time="2026-01-01T06:00:00Z",
        detector_candidates={"15m": payload, "4h": payload},
        structure_shadow={
            "schema": "structure_engine_v3_shadow_v1",
            "timeframes": {
                "15m": {"events": [accepted_event], "counts": {}},
                "4h": {"events": [rejected_event], "counts": {}},
            },
        },
        formal_structure_graph_v1={
            "schema": "formal_mtf_structure_graph_v1",
            "timeframes": {
                "4h": {"latest_external_break": {"object_id": shared_id}}
            },
            "parent_child_context": {"status": "INSUFFICIENT_CONTEXT", "has_conflict": False},
            "active_range": {},
        },
        causal_poi_authority={"scenarios": {}},
    )

    check = graph["invariants"]["checks"][0]
    assert check["source_timeframe"] == "4h"
    assert check["passed"] is False
    assert graph["invariants"]["status"] == "REVIEW_REQUIRED"


def test_v3_confirms_two_stage_mss_only_after_held_protected_break_and_strong_followup() -> None:
    frame, payload = _two_stage_mss_fixture()
    shadow = StructureEngineV3Shadow().analyze(
        symbol="TESTUSDT",
        detector_candidates={"15m": payload},
        timeframe_dfs={"15m": frame},
        decision_time="2026-02-01T10:30:00Z",
    ).to_dict()
    events = shadow["timeframes"]["15m"]["events"]
    protected = next(event for event in events if event["source_break_object_id"] == "weak-protected-break")
    followup = next(event for event in events if event["source_break_object_id"] == "strong-followup-break")

    assert protected["accepted_for_shadow_story"] is False
    assert protected["parent_invalidation_probe"] is True
    assert followup["event_type"] == "EXTERNAL_MSS_CONFIRMED_BEARISH"
    assert followup["accepted_for_shadow_story"] is True
    assert followup["parent_invalidation_chain"]["protected_break_event_id"] == "weak-protected-break"
    assert followup["parent_invalidation_chain"]["held_without_body_close_reclaim"] is True


def test_v3_two_stage_mss_chain_expires_on_protected_level_reclaim() -> None:
    frame, payload = _two_stage_mss_fixture(reclaim=True)
    shadow = StructureEngineV3Shadow().analyze(
        symbol="TESTUSDT",
        detector_candidates={"15m": payload},
        timeframe_dfs={"15m": frame},
        decision_time="2026-02-01T10:30:00Z",
    ).to_dict()
    followup = next(
        event
        for event in shadow["timeframes"]["15m"]["events"]
        if event["source_break_object_id"] == "strong-followup-break"
    )

    assert followup["event_type"] == "EXTERNAL_MSS_CANDIDATE_BEARISH"
    assert followup["accepted_for_shadow_story"] is False
    assert followup["parent_invalidation_chain"] is None


def test_rejected_primary_poi_is_withheld_from_current_route_map() -> None:
    payload = _payload()
    poi_authority = _poi_authority()
    duplicate = dict(poi_authority["scenarios"]["bullish"]["primary_causal_poi"])
    duplicate["poi_role"] = "secondary_reaction_poi"
    poi_authority["scenarios"]["bullish"]["secondary_reaction_pois"] = [duplicate]
    old_event = {
        "source_break_object_id": "break-old",
        "accepted_for_shadow_story": True,
        "scope": "external",
        "direction": "bullish",
        "event_type": "INITIAL_DIRECTION_BREAK",
        "lifecycle_state": "ACCEPTED_BREAKOUT",
        "broken_swing_id": "swing-high-1",
        "broken_level_price": 100.0,
        "body_close_time": "2026-01-01T02:45:00Z",
        "confirmation_time": "2026-01-01T03:15:00Z",
        "displacement_score": 1.0,
    }
    graph = build_formal_causal_episode_graph(
        symbol="TESTUSDT",
        decision_time="2026-01-01T06:00:00Z",
        detector_candidates={"15m": payload},
        structure_shadow={
            "schema": "structure_engine_v3_shadow_v1",
            "timeframes": {"15m": {"events": [old_event], "counts": {}}},
        },
        formal_structure_graph_v1=_v1_graph(),
        causal_poi_authority=poi_authority,
    )

    route = graph["current_story"]["route_map"]
    assert graph["current_story"]["status"] == "RECONCILIATION_REQUIRED"
    assert route["primary_poi"] is None
    assert route["poi_resolution_status"] == "DISPUTED_BY_V3"
    assert route["disputed_objects"][0]["linked_break_id"] == "break-1"
    assert route["disputed_objects"][0]["display_authority"] == "WITHHELD"
    assert len(route["disputed_objects"]) == 1

    thesis_text = _format_scenario_watch_pois(
        {
            "causal_poi_authority": poi_authority,
            "formal_causal_episode_graph": graph,
        }
    )
    assert thesis_text is not None
    assert "No authority is granted to disputed POIs" in thesis_text
    assert "replay.." not in thesis_text
    assert "withheld" in thesis_text
    assert "bullish scenario:" not in thesis_text


# -- reconciliation is scoped: narrative vs entry timing ----------------------
#
# Every V1/V3 disagreement used to carry the same veto, so one marginal
# lower-timeframe break suppressed a higher-timeframe read that both engines
# agreed on. On live BTCUSDT the 1d and 4h controlling breaks survived V3
# (displacement 0.82 and 1.0, both bearish) while 1h (5.7 bps beyond structure)
# and 15m failed -- and the whole run refused. SMC reads top-down: the context
# timeframe owns the story, everything below it is timing.

from smc_desk.perception.formal_causal_episode_graph import (  # noqa: E402
    _invariants,
    _structure_role,
    _timeframe_minutes,
)


def _graph_v1(context_timeframe: str | None, *, coherent: bool = True) -> dict:
    node = {"narrative_context": {"is_coherent": coherent}}
    if context_timeframe is not None:
        node["narrative_context"]["context_timeframe"] = context_timeframe
    node["timeframes"] = {
        tf: {"latest_external_break": {"object_id": f"{tf}-break"}}
        for tf in ("1d", "4h", "1h", "15m")
    }
    return node


def _run_invariants(context_timeframe: str | None, accepted: set[str], *, coherent: bool = True) -> dict:
    return _invariants(
        timeframes={},
        formal_structure_graph_v1=_graph_v1(context_timeframe, coherent=coherent),
        causal_poi_authority={},
        accepted_ids_by_timeframe={
            tf: ({f"{tf}-break"} if f"{tf}-break" in accepted else set())
            for tf in ("1d", "4h", "1h", "15m")
        },
        shadow_timeframes={},
    )


def test_timeframe_minutes_parses_the_shapes_the_system_uses() -> None:
    assert _timeframe_minutes("15m") == 15
    assert _timeframe_minutes("4h") == 240
    assert _timeframe_minutes("1d") == 1440
    assert _timeframe_minutes("1w") == 10080
    assert _timeframe_minutes("garbage") is None
    assert _timeframe_minutes("") is None


def test_lower_timeframe_disagreement_withholds_entry_not_the_narrative() -> None:
    """The live BTCUSDT case: 1d and 4h survive, 1h and 15m do not."""
    result = _run_invariants("1d", {"1d-break", "4h-break"})
    assert result["status"] == "ENTRY_TIMING_WITHHELD"
    assert result["narrative_violations"] == []
    assert set(result["entry_timing_violations"]) == {
        "1h_v1_controlling_external_break_survives_v3",
        "15m_v1_controlling_external_break_survives_v3",
    }


def test_context_timeframe_disagreement_still_refuses_everything() -> None:
    """A broken daily read is not a timing problem. This must not be softened."""
    result = _run_invariants("1d", {"4h-break", "1h-break", "15m-break"})
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["narrative_violations"] == ["1d_v1_controlling_external_break_survives_v3"]


def test_all_reconciled_still_passes() -> None:
    result = _run_invariants("1d", {"1d-break", "4h-break", "1h-break", "15m-break"})
    assert result["status"] == "PASS"
    assert result["violations"] == []


def test_unknown_context_timeframe_fails_closed_to_narrative() -> None:
    """An unclassifiable disagreement must never be downgraded to a timing note."""
    result = _run_invariants(None, {"1d-break", "4h-break"})
    assert result["status"] == "REVIEW_REQUIRED"
    assert set(result["narrative_violations"]) == {
        "1h_v1_controlling_external_break_survives_v3",
        "15m_v1_controlling_external_break_survives_v3",
    }
    assert result["entry_timing_violations"] == []


def test_incoherent_narrative_read_cannot_grant_timing_leniency() -> None:
    """If the narrative itself is not coherent, there is no context to rank against."""
    result = _run_invariants("1d", {"1d-break", "4h-break"}, coherent=False)
    assert result["status"] == "REVIEW_REQUIRED"


def test_structure_role_boundary_is_inclusive_of_the_context_timeframe() -> None:
    assert _structure_role("1d", "1d") == "narrative"
    assert _structure_role("4h", "1d") == "timing"
    assert _structure_role("1w", "1d") == "narrative"
    assert _structure_role("15m", "15m") == "narrative"
    # Unrankable either side -> narrative, never a silent downgrade.
    assert _structure_role("4h", "nonsense") == "narrative"
    assert _structure_role("nonsense", "1d") == "narrative"
