from __future__ import annotations

from smc_desk.colleague.smc_thesis_v2 import assert_smc_thesis_v2_quality, build_smc_thesis_v2
from smc_desk.decision.contradiction_resolver import resolve_timeframe_contradictions
from smc_desk.decision.timeframe_role_engine import assess_timeframe_roles
from smc_desk.decision.watch_state_engine import evaluate_watch_state
from smc_desk.perception.displacement import score_break_displacement
from smc_desk.perception.poi_lifecycle import build_poi_lifecycle_by_timeframe
from smc_desk.perception.structure_hierarchy import (
    build_mtf_structure_hierarchy,
    build_structure_hierarchy,
    hierarchy_timeframe_signals,
)


def _break(
    object_id: str,
    direction: str,
    *,
    price_low: str,
    price_high: str,
    body_ratio: float,
    body_penetration: str,
    broken_price: str = "60000",
    confirmed_at: str = "2026-06-27T08:00:00Z",
) -> dict:
    return {
        "object_id": object_id,
        "direction": direction,
        "break_type": "CHOCH",
        "price_low": price_low,
        "price_high": price_high,
        "candidate_at": "2026-06-27T07:00:00Z",
        "confirmed_at": confirmed_at,
        "confirmation_status": "confirmed",
        "evidence": {
            "broken_swing_id": f"swing_{object_id}",
            "broken_price": broken_price,
            "wick_penetration": body_penetration,
            "body_close_penetration": body_penetration,
            "penetration_ticks": 1000,
            "penetration_atr_pct": 0.0,
            "candle_body_ratio": body_ratio,
            "displacement_strength": 0.0,
            "is_internal": False,
            "is_unconfirmed_probe": False,
        },
    }


def _swing(object_id: str, direction: str, low: str, high: str) -> dict:
    return {
        "object_id": object_id,
        "direction": direction,
        "price_low": low,
        "price_high": high,
        "confirmed_at": "2026-06-27T06:00:00Z",
    }


def _one_hour_btc_failure_snapshot() -> dict:
    strong_bearish = _break(
        "CHOCH_bearish_1782392400.0",
        "bearish",
        price_low="58030.0",
        price_high="61346.4",
        body_ratio=-0.8949,
        body_penetration="2399.6",
        broken_price="60648.0",
        confirmed_at="2026-06-25T14:00:00Z",
    )
    weak_bullish_retrace = _break(
        "CHOCH_bullish_1782453600.0",
        "bullish",
        price_low="59666.2",
        price_high="60440.0",
        body_ratio=0.4872,
        body_penetration="53.9",
        broken_price="60245.0",
        confirmed_at="2026-06-26T07:00:00Z",
    )
    return {
        "candle_count": 1000,
        "last_price": "60407.0",
        "structure_state": {
            "current_direction": "bullish",
            "last_external_break_id": weak_bullish_retrace["object_id"],
            "last_confirmed_external_high": "swing_high",
            "last_confirmed_external_low": "swing_low",
        },
        "swings": {
            "external": [
                _swing("swing_high", "bearish", "61200.0", "61500.0"),
                _swing("swing_low", "bullish", "58030.0", "58500.0"),
            ],
            "internal": [],
            "local": [],
        },
        "structure_breaks": [strong_bearish, weak_bullish_retrace],
        "fvgs": [],
    }


def test_displacement_quality_separates_strong_from_weak_breaks():
    strong = _break(
        "strong_bear",
        "bearish",
        price_low="58000",
        price_high="61300",
        body_ratio=-0.9,
        body_penetration="2400",
        broken_price="60600",
    )
    weak = _break(
        "weak_bull",
        "bullish",
        price_low="59600",
        price_high="60400",
        body_ratio=0.3,
        body_penetration="20",
        broken_price="60200",
    )

    assert score_break_displacement(strong).break_quality == "strong"
    assert score_break_displacement(strong).valid_for_bias_flip is True
    assert score_break_displacement(weak).break_quality == "weak"
    assert score_break_displacement(weak).valid_for_bias_flip is False


def test_internal_retracement_cannot_flip_external_bias_even_if_raw_current_direction_is_bullish():
    hierarchy = build_structure_hierarchy(
        timeframe="1h",
        snapshot=_one_hour_btc_failure_snapshot(),
        current_price="60407.0",
    ).to_dict()

    assert hierarchy["evidence"]["raw_current_direction"] == "bullish"
    assert hierarchy["external_bias"] == "bearish"
    assert hierarchy["internal_state"] == "bullish_retracement"
    assert hierarchy["structure_phase"] == "retracement_inside_bearish_external_range"
    assert hierarchy["latest_external_break_id"] == "CHOCH_bearish_1782392400.0"
    assert hierarchy["latest_internal_break_id"] == "CHOCH_bullish_1782453600.0"


def test_btcusdt_20260627_regression_outputs_bearish_watch_not_htf_conflict():
    snapshots = {
        "4h": {
            "candle_count": 500,
            "last_price": "60522.3",
            "structure_state": {"current_direction": "bearish"},
            "swings": {
                "external": [
                    _swing("4h_high", "bearish", "63000.0", "65775.0"),
                    _swing("4h_low", "bullish", "60238.0", "61870.0"),
                ],
                "internal": [],
                "local": [],
            },
            "structure_breaks": [
                _break(
                    "BOS_bearish_1782302400.0",
                    "bearish",
                    price_low="60238.0",
                    price_high="62939.3",
                    body_ratio=-0.9746,
                    body_penetration="1615.1",
                    broken_price="61870.0",
                    confirmed_at="2026-06-24T16:00:00Z",
                )
            ],
            "fvgs": [],
        },
        "1h": _one_hour_btc_failure_snapshot(),
        "15m": {
            "candle_count": 1500,
            "last_price": "60372.6",
            "structure_state": {"current_direction": "bullish"},
            "swings": {"external": [], "internal": [], "local": []},
            "structure_breaks": [],
            "fvgs": [],
        },
    }
    hierarchy = build_mtf_structure_hierarchy(
        snapshots,
        current_prices={"4h": "60522.3", "1h": "60407.0", "15m": "60372.6"},
    )
    roles = assess_timeframe_roles(hierarchy).to_dict()
    pois = build_poi_lifecycle_by_timeframe(
        snapshots,
        hierarchy,
        current_prices={"4h": "60522.3", "1h": "60407.0", "15m": "60372.6"},
    )
    watch = evaluate_watch_state(hierarchy_by_tf=hierarchy, roles=roles, pois_by_tf=pois).to_dict()
    contradiction = resolve_timeframe_contradictions(hierarchy_timeframe_signals(hierarchy))

    assert hierarchy["4h"]["external_bias"] == "bearish"
    assert hierarchy["1h"]["external_bias"] == "bearish"
    assert hierarchy["1h"]["internal_state"] == "bullish_retracement"
    assert roles["15m_role"] == "entry_confirmation"
    assert roles["ltf_override_allowed"] is False
    assert contradiction.outcome != "INVALIDATE_ALL"
    assert watch["final_state"] == "WATCH_BEARISH_RETRACE_TO_SUPPLY"
    assert watch["final_action"] == "NO_SIGNAL"
    assert watch["signal_allowed"] is False


def test_smc_thesis_v2_contains_required_trader_sections_without_live_entry_language():
    snapshots = {"1h": _one_hour_btc_failure_snapshot()}
    hierarchy = build_mtf_structure_hierarchy(snapshots, current_prices={"1h": "60407.0"})
    roles = assess_timeframe_roles(hierarchy).to_dict()
    pois = build_poi_lifecycle_by_timeframe(snapshots, hierarchy, current_prices={"1h": "60407.0"})
    watch = evaluate_watch_state(hierarchy_by_tf=hierarchy, roles=roles, pois_by_tf=pois).to_dict()
    payload = build_smc_thesis_v2(
        symbol="BTCUSDT",
        cognitive_result={"refusal": {"reasons": ["observe-only"]}},
        structure_hierarchy=hierarchy,
        timeframe_roles=roles,
        pois_by_tf=pois,
        watch_state=watch,
    )

    assert payload["schema"] == "smc_thesis_v2"
    assert payload["claim_count"] == 12
    assert payload["forbidden_language_present"] is False
    setup_claim = next(claim for claim in payload["claims"] if claim["claim_id"] == "one_hour_setup_story")
    active = watch["active_poi"]
    if active:
        assert str(active["price_low"]) in setup_claim["claim"]
        assert str(active["price_high"]) in setup_claim["claim"]
    assert_smc_thesis_v2_quality(payload)
