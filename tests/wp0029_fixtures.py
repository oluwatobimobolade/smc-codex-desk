from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd


def sample_df(bars: int = 80, start_price: float = 100.0) -> pd.DataFrame:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    price = start_price
    for index in range(bars):
        ts = start + timedelta(minutes=15 * index)
        open_price = price
        close = price + (0.35 if index % 4 else -0.22)
        high = max(open_price, close) + 0.35
        low = min(open_price, close) - 0.35
        rows.append({
            "timestamp": ts.isoformat(),
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": 1000 + index,
        })
        price = close
    return pd.DataFrame(rows)


def sample_cognitive(
    *,
    symbol: str = "BTCUSDT",
    active_poi: dict | None = None,
    readiness_state: str = "WAIT_FOR_RETRACE_TO_LTF_SUPPLY",
    move_state: str = "EARLY_CONTINUATION_CONFIRMATION",
    watch_state: str = "WATCH_BEARISH_RETRACE_TO_SUPPLY",
) -> dict:
    active_poi = active_poi if active_poi is not None else {
        "poi_id": "15m:order_block:test_supply",
        "kind": "supply",
        "timeframe": "15m",
        "direction": "bearish",
        "price_low": "100.50",
        "price_high": "101.00",
        "freshness": "fresh",
        "price_relation": "below_poi",
        "validity_status": "VALID_ACTIVE_SETUP_POI",
        "selection_score": 2.9,
    }
    return {
        "symbol": symbol,
        "final_action": "NO_SIGNAL",
        "signal_allowed": False,
        "watch_state": {
            "final_state": watch_state,
            "final_action": "NO_SIGNAL",
            "signal_allowed": False,
            "direction": "bearish",
            "active_poi": active_poi,
            "reasons": ["Price should wait for retracement into supply."],
        },
        "execution_readiness": {
            "state": readiness_state,
            "confidence": 0.62,
            "signal_allowed": False,
            "capital_risk": 0,
        },
        "inducement_continuation": {
            "state": move_state,
            "direction": "bearish",
            "confidence": 0.64,
            "continuation_confirmed_if": [
                "price retests active 15m supply 100.50-101.00",
                "price rejects from that supply",
                "price breaks the next sell-side liquidity after rejection",
            ],
            "inducement_confirmed_if": [
                "price reclaims above active 15m supply 100.50-101.00",
                "price holds above the reclaimed supply",
                "price expands back toward buy-side liquidity",
            ],
            "do_not_chase_reason": "Shift exists, but continuation needs a retest/rejection instead of a chase entry.",
            "evidence": {
                "same_direction_15m_break_count": 3,
                "near_target_liquidity": False,
            },
        },
        "structure_hierarchy": {
            "4h": {
                "external_bias": "bearish",
                "latest_external_break_id": "BOS_bearish_4h",
                "external_range_low": "96.00",
                "external_range_high": "105.00",
                "protected_low": "96.00",
                "protected_high": "105.00",
            },
            "1h": {
                "external_bias": "bearish",
                "latest_external_break_id": "BOS_bearish_1h",
                "external_range_low": "98.00",
                "external_range_high": "103.00",
                "protected_low": "98.00",
                "protected_high": "103.00",
            },
            "15m": {
                "external_bias": "bearish",
                "latest_external_break_id": "BOS_bearish_15m",
                "external_range_low": "99.00",
                "external_range_high": "102.00",
                "protected_low": "99.00",
                "protected_high": "102.00",
            },
        },
        "liquidity_sequence": {
            "15m": {
                "buy_side_liquidity_taken": True,
                "sell_side_liquidity_taken": False,
                "current_liquidity_draw": "sell_side_liquidity",
            }
        },
        "refusal": {
            "final_action": "NO_SIGNAL",
            "signal_allowed": False,
            "blocking_codes": ["watch_state_not_executable"],
            "reasons": ["Cognitive checks passed, but execution authority remains disabled."],
        },
    }
