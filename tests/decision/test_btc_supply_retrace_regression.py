"""Regression for the BTCUSDT NO_SIGNAL incident (WP-0021A).

The engine refused correctly but spoke blindly: a 1h bullish CHoCH (that did NOT break
the 4h protected high) flipped the whole 1h to bullish, discarded the bearish supply, and
produced a flat NO_SIGNAL via INVALIDATE_ALL. The fix makes the child's break subordinate
to the parent leg, keeps the bearish supply alive, and lets the report name the watch state.

Observe-only invariant: signal_allowed is False everywhere; this never implies execution.
"""
from __future__ import annotations

from smc_desk.decision.contradiction_resolver import resolve_timeframe_contradictions
from smc_desk.decision.timeframe_role_engine import assess_timeframe_roles
from smc_desk.decision.watch_state_engine import evaluate_watch_state
from smc_desk.perception.poi_lifecycle import build_poi_lifecycle_by_timeframe
from smc_desk.perception.structure_hierarchy import (
    build_mtf_structure_hierarchy,
    hierarchy_timeframe_signals,
)


def _break(object_id, direction, broken_price, close, body_ratio, low, high, ts):
    bcp = (close - broken_price) if direction == "bullish" else (broken_price - close)
    return {
        "object_id": object_id,
        "direction": direction,
        "confirmed_at": ts,
        "candidate_at": ts,
        "price_low": str(low),
        "price_high": str(high),
        "evidence": {
            "broken_price": str(broken_price),
            "body_close_penetration": str(bcp),
            "candle_body_ratio": body_ratio,
            "wick_penetration": str(bcp),
            "impulse_candle_count": 1,
            "is_unconfirmed_probe": False,
        },
    }


def _fvg(object_id, direction, low, high, ts):
    return {
        "object_id": object_id,
        "direction": direction,
        "price_low": str(low),
        "price_high": str(high),
        "terminal_reason": "none",
        "mitigation_status": "fresh",
        "confirmed_at": ts,
        "candidate_at": ts,
    }


def _btc_perception(*, choch_close: int) -> dict:
    """4h bearish leg; 1h ends on a bullish CHoCH that closes at ``choch_close``.

    With choch_close below the 4h protected high (66000) the CHoCH is an internal
    retracement; above it, a legitimate flip.
    """
    return {
        "4h": {
            "structure_breaks": [
                _break("h4_bear", "bearish", 65000, 64500, 0.70, 64400, 65100, "2026-06-27T00:00:00+00:00"),
            ],
            "fvgs": [
                _fvg("h4_fvg1", "bearish", 65200, 65500, "2026-06-27T01:00:00+00:00"),
                _fvg("h4_fvg2", "bearish", 65600, 65900, "2026-06-27T02:00:00+00:00"),
            ],
            "structure_state": {
                "current_direction": "bearish",
                "last_confirmed_external_high": "h4_high",
                "last_confirmed_external_low": "h4_low",
            },
            "swings": {
                "highs": [{"object_id": "h4_high", "price_high": "66000"}],
                "lows": [{"object_id": "h4_low", "price_low": "63000"}],
            },
            "candle_count": 500,
        },
        "1h": {
            "structure_breaks": [
                _break("h1_bear", "bearish", 64800, 64600, 0.60, 64500, 64900, "2026-06-27T06:00:00+00:00"),
                _break("h1_choch_bull", "bullish", 64300, choch_close, 0.70, 64250, choch_close + 50, "2026-06-27T08:00:00+00:00"),
            ],
            "fvgs": [
                _fvg(f"h1_fvg{i}", "bearish", 64700 + i * 30, 64760 + i * 30, "2026-06-27T07:00:00+00:00")
                for i in range(7)
            ],
            "structure_state": {
                "current_direction": "bullish",  # the raw, buggy per-TF label
                "last_confirmed_external_high": "h1_high",
                "last_confirmed_external_low": "h1_low",
            },
            "swings": {
                "highs": [{"object_id": "h1_high", "price_high": "64600"}],
                "lows": [{"object_id": "h1_low", "price_low": "63800"}],
            },
            "candle_count": 1000,
        },
    }


_PRICES = {"4h": "64300", "1h": "64300"}


def test_1h_bullish_choch_is_internal_retracement_not_a_flip():
    perception = _btc_perception(choch_close=64500)  # below the 4h 66000 ceiling
    hierarchy = build_mtf_structure_hierarchy(perception, current_prices=_PRICES)
    assert hierarchy["1h"]["external_bias"] == "bearish"
    assert hierarchy["1h"]["internal_state"] == "bullish_retracement"
    assert hierarchy["1h"]["structure_phase"] == "retracement_inside_bearish_external_range"
    assert hierarchy["1h"]["evidence"]["subordinated_to_parent"] is True


def test_contradiction_is_not_invalidate_all():
    perception = _btc_perception(choch_close=64500)
    hierarchy = build_mtf_structure_hierarchy(perception, current_prices=_PRICES)
    resolution = resolve_timeframe_contradictions(hierarchy_timeframe_signals(hierarchy))
    assert resolution.outcome != "INVALIDATE_ALL"


def test_bearish_supply_poi_survives_on_1h():
    perception = _btc_perception(choch_close=64500)
    hierarchy = build_mtf_structure_hierarchy(perception, current_prices=_PRICES)
    pois = build_poi_lifecycle_by_timeframe(perception, hierarchy, current_prices=_PRICES)
    bearish = [p for p in pois["1h"] if p["direction"] == "bearish"]
    assert bearish, "expected at least one active bearish 1h POI (supply)"


def test_watch_state_is_bearish_retrace_and_observe_only():
    perception = _btc_perception(choch_close=64500)
    hierarchy = build_mtf_structure_hierarchy(perception, current_prices=_PRICES)
    pois = build_poi_lifecycle_by_timeframe(perception, hierarchy, current_prices=_PRICES)
    roles = assess_timeframe_roles(hierarchy).to_dict()
    decision = evaluate_watch_state(hierarchy_by_tf=hierarchy, roles=roles, pois_by_tf=pois)
    assert decision.final_state == "WATCH_BEARISH_RETRACE_TO_SUPPLY"
    assert decision.direction == "bearish"
    assert decision.final_state != "NO_TRADE_HTF_CONFLICT"
    assert decision.active_poi is not None
    assert decision.active_poi["selection_score"] > 0
    assert decision.active_poi["selection_reasons"]
    assert decision.poi_selection["method"] == "ranked_active_poi_v3_protected_range_first_deeper_ob_reaction_priority"
    # observe-only invariant — the whole point of the repair
    assert decision.signal_allowed is False
    assert decision.final_action != "EXECUTE"


def test_gate_still_allows_a_legitimate_flip_above_parent_protection():
    # A 1h bullish break that DOES close above the 4h 66000 ceiling is a real flip.
    perception = _btc_perception(choch_close=66200)
    hierarchy = build_mtf_structure_hierarchy(perception, current_prices={"4h": "66300", "1h": "66300"})
    assert hierarchy["1h"]["external_bias"] == "bullish"


def test_deterministic_output():
    perception = _btc_perception(choch_close=64500)
    a = build_mtf_structure_hierarchy(perception, current_prices=_PRICES)
    b = build_mtf_structure_hierarchy(perception, current_prices=_PRICES)
    assert a == b
