from __future__ import annotations

from smc_desk.perception.liquidity_sequence import summarize_liquidity_sequence


def test_liquidity_sequence_buy_side_then_bearish_shift():
    snapshot = {
        "liquidity_levels": [
            {"object_id": "low_pool", "price_low": "59850", "evidence": {"side": "sell_side"}},
        ],
        "sweeps": [
            {
                "object_id": "sweep_buy_side",
                "direction": "bearish",
                "confirmed_at": "2026-06-27T20:15:00+00:00",
                "price_low": "60300",
                "price_high": "60800",
                "evidence": {"side": "buy_side", "swept_level_id": "liq_equal_highs"},
            }
        ],
    }

    seq = summarize_liquidity_sequence(snapshot).to_dict()

    assert seq["buy_side_liquidity_taken"] is True
    assert seq["sell_side_liquidity_taken"] is False
    assert seq["last_liquidity_event"] == "buy_side_sweep"
    assert seq["current_liquidity_draw"] == "sell_side_liquidity"
    assert seq["next_likely_liquidity"].startswith("sell_side@")
