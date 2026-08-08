from __future__ import annotations

from smc_desk.perception.structure_narrative import prefer_formal_graph_override
from tools.run_live_ai_smc_full_system import (
    _display_bias_labels,
    _formal_graph_aware_fallback_bias,
    _vote_bias_labels,
)


def test_formal_unknown_blocks_raw_drift_bias_promotion() -> None:
    narrative = {
        "timeframes": {
            "1d": {
                "external_bias": "unknown",
                "internal_state": "none",
                "label": "bullish",
                "vote_bias": "bullish",
                "latest_external_break_id": None,
            },
            "4h": {
                "external_bias": "bullish",
                "internal_state": "bullish_internal_continuation",
                "label": "bullish",
                "vote_bias": "bullish",
            },
        },
        "conflicts": [],
        "evidence": [],
        "parent_child_context": {},
    }
    graph = {
        "timeframes": {
            "1d": {
                "external_bias": "unknown",
                "internal_state": "none",
                "latest_external_break": None,
                "latest_internal_break": None,
            },
            "4h": {
                "external_bias": "bullish",
                "internal_state": "bullish_internal_continuation",
                "latest_external_break": {
                    "object_id": "4h_bos",
                    "confirmed_at": "2026-07-10T04:00:00Z",
                },
                "latest_internal_break": None,
            },
        },
        "parent_child_context": {"status": "ALIGNED", "has_conflict": False},
    }

    result = prefer_formal_graph_override(narrative, graph)

    assert result["timeframes"]["1d"]["label"] == "unknown"
    assert result["timeframes"]["1d"]["vote_bias"] == "unknown"
    assert result["timeframes"]["1d"]["formal_graph_authority"] is True
    assert result["timeframes"]["4h"]["label"] == "bullish"
    assert result["timeframes"]["4h"]["latest_external_break_id"] == "4h_bos"
    assert any("raw OHLC drift" in note for note in result["evidence"])


def test_formal_graph_preserves_external_bias_and_opposing_internal_pullback() -> None:
    narrative = {"timeframes": {}, "conflicts": [], "evidence": []}
    graph = {
        "timeframes": {
            "1h": {
                "external_bias": "bullish",
                "internal_state": "bearish_internal_pullback",
                "latest_external_break": {"object_id": "1h_bos", "confirmed_at": "2026-07-10T02:00:00Z"},
                "latest_internal_break": {"object_id": "1h_internal_choch", "confirmed_at": "2026-07-10T19:00:00Z"},
            }
        },
        "parent_child_context": {"status": "ALIGNED", "has_conflict": False},
    }

    result = prefer_formal_graph_override(narrative, graph)

    node = result["timeframes"]["1h"]
    assert node["label"] == "bullish_external_bearish_internal_pullback"
    assert node["vote_bias"] == "bullish"
    assert node["latest_external_break_id"] == "1h_bos"
    assert node["latest_internal_break_id"] == "1h_internal_choch"


def test_live_harness_does_not_rehydrate_formal_unknown_from_raw_drift() -> None:
    raw = {"1d": "bullish", "4h": "bullish", "1h": "bullish"}
    narrative = {
        "timeframes": {
            "1d": {"label": "unknown", "vote_bias": "unknown", "formal_graph_authority": True},
            "4h": {"label": "bullish", "vote_bias": "bullish", "formal_graph_authority": True},
            "1h": {
                "label": "bullish_external_bearish_internal_pullback",
                "vote_bias": "bullish",
                "formal_graph_authority": True,
            },
        }
    }

    display = _display_bias_labels(raw, narrative)
    votes = _vote_bias_labels(raw, narrative)
    fallback = _formal_graph_aware_fallback_bias(raw, narrative)

    assert display["1d"] == "unknown"
    assert votes["1d"] == "unknown"
    assert display["1h"] == "bullish_external_bearish_internal_pullback"
    assert fallback == {}
