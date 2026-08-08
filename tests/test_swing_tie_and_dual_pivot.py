"""Regression tests for swing detector v2.1 tie handling and dual pivots.

Pins two canonical-perception defects found in the 2026-07-11 semantic audit:

C1 — exact-tie annihilation: under strict inequality on both windows, two
     tick-equal extremes within one fractal window annihilated BOTH pivots,
     so an EQH/EQL liquidity pool had no swing, no liquidity level, and no
     break/sweep target. v2.1 rule: strictly above the left window,
     at-or-above the right window — the FIRST touch wins.

C2 — dual-pivot collapse: a wide outside/reversal candle that is a valid
     fractal high AND low was recorded only as a bullish low; its high side
     was invisible to structure and could never be broken. v2.1 emits both
     objects (the high twin carries an explicit ``_high`` id suffix).

The real-data invariant at the bottom pins C1 against live BTCUSDT candles:
five swing lows in this 351-bar window were annihilated by exact ties under
the old rule.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from smc_desk.data.schemas import Candle
from smc_desk.perception.liquidity import LiquidityLevelDetector
from smc_desk.perception.structure import StructureDetector
from smc_desk.perception.swings import SwingDetector

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_BTC_CSV = REPO_ROOT / "data" / "live_btc.csv"


def _dv(value):
    return getattr(value, "value", value)


def _mk(i, o, h, l, c):
    return Candle(
        venue="TEST", instrument="BTCUSDT", timeframe="15m",
        open_time=T0 + timedelta(minutes=15 * i),
        close_time=T0 + timedelta(minutes=15 * (i + 1)),
        open=Decimal(str(o)), high=Decimal(str(h)), low=Decimal(str(l)), close=Decimal(str(c)),
        volume=Decimal("100"), trade_count=10, is_closed=True, is_complete=True, contains_gap=False,
    )


def _series(vals):
    return [_mk(i, o, h, l, c) for i, (o, h, l, c) in enumerate(vals)]


def _flat(n, px=100.0, amp=0.05):
    return [(px, px + amp, px - amp, px) for _ in range(n)]


def _detect(vals, bars=5, scale="external"):
    candles = _series(vals)
    now = candles[-1].close_time
    return candles, SwingDetector(bars_left=bars, bars_right=bars, scale_name=scale).detect(candles, now)


# -- C1: exact-tie equal extremes ---------------------------------------------


def test_exact_equal_double_top_first_touch_is_pivot():
    vals = _flat(6) + [(100, 110, 99.9, 101)] + _flat(4) + [(100, 110, 99.9, 100.5)] + _flat(6)
    _, swings = _detect(vals)
    highs = [s for s in swings if _dv(s.direction) == "bearish"]
    assert len(highs) == 1, "an exact equal double top must yield exactly one pivot"
    assert highs[0].evidence.pivot_index == 6, "the FIRST touch is the pivot"
    assert highs[0].price_high == Decimal("110")


def test_exact_equal_double_bottom_first_touch_is_pivot():
    vals = _flat(6) + [(100, 100.1, 90, 99)] + _flat(4) + [(100, 100.1, 90, 99.5)] + _flat(6)
    _, swings = _detect(vals)
    lows = [s for s in swings if _dv(s.direction) == "bullish"]
    assert len(lows) == 1
    assert lows[0].evidence.pivot_index == 6
    assert lows[0].price_low == Decimal("90")


def test_near_equal_double_top_still_single_pivot_at_higher_price():
    vals = _flat(6) + [(100, 110, 99.9, 101)] + _flat(4) + [(100, 109.99, 99.9, 100.5)] + _flat(6)
    _, swings = _detect(vals)
    highs = [s for s in swings if _dv(s.direction) == "bearish"]
    assert len(highs) == 1
    assert highs[0].price_high == Decimal("110")


def test_equal_lows_now_produce_a_liquidity_level():
    """The tied low is a swing again, so liquidity can finally see the pool."""
    vals = _flat(6) + [(100, 100.1, 90, 99)] + _flat(4) + [(100, 100.1, 90, 99.5)] + _flat(6)
    candles, swings = _detect(vals)
    levels = LiquidityLevelDetector().detect(swings, candles[-1].close_time)
    sell_side = [lv for lv in levels if float(lv.price_low) == 90.0 or float(lv.price_high) == 90.0]
    assert sell_side, "the tick-equal double bottom must be a visible liquidity level"


# -- C2: dual-pivot outside bars ----------------------------------------------


def _dual_pivot_vals():
    # Bar 6 is simultaneously the highest high and lowest low of its window.
    return _flat(6) + [(100, 112, 90, 105)] + _flat(6, px=101)


def test_dual_pivot_bar_emits_both_swing_objects():
    _, swings = _detect(_dual_pivot_vals())
    at_pivot = [s for s in swings if s.evidence.pivot_index == 6]
    directions = sorted(_dv(s.direction) for s in at_pivot)
    assert directions == ["bearish", "bullish"], "both sides of a dual pivot must exist"
    ids = sorted(s.object_id for s in at_pivot)
    assert ids[1].endswith("_high"), "the high twin carries the explicit _high suffix"
    assert not ids[0].endswith("_high"), "the low keeps the stable base id"


def test_dual_pivot_high_is_a_breakable_target():
    """A V-reversal that clears the dual bar's high must confirm a break.

    Under the old detector the 112 high never existed as a swing, so this
    exact sequence produced zero confirmed breaks.
    """
    vals = _flat(6) + [(100, 112, 90, 105)] + _flat(5, px=101)
    vals += [(101, 113, 100.9, 112.8)]        # body-closes above the dual bar's high
    vals += _flat(6, px=112)
    candles = _series(vals)
    now = candles[-1].close_time
    swings = SwingDetector(bars_left=5, bars_right=5, scale_name="external").detect(candles, now)
    _, breaks = StructureDetector().detect(candles, swings, now)
    confirmed = [b for b in breaks if _dv(b.confirmation_status) == "confirmed"]
    assert any(
        _dv(b.direction) == "bullish" and b.evidence.broken_price == Decimal("112")
        for b in confirmed
    ), "the dual bar's high must be a breakable structural target"


# -- real-data invariant -------------------------------------------------------


@pytest.mark.skipif(not LIVE_BTC_CSV.exists(), reason="live BTC fixture not present")
def test_no_tick_equal_extreme_is_invisible_on_real_btc():
    """Every real bar whose low ties-or-beats its full ±5 window must be
    represented by a swing at that price within the window (first touch)."""
    df = pd.read_csv(LIVE_BTC_CSV)
    candles = [
        _mk(i, row["open"], row["high"], row["low"], row["close"])
        for i, row in df.iterrows()
    ]
    now = candles[-1].close_time
    swings = SwingDetector(bars_left=5, bars_right=5, scale_name="external").detect(candles, now)
    low_pivots = {}
    for s in swings:
        if _dv(s.direction) == "bullish":
            low_pivots.setdefault(float(s.price_low), []).append(s.evidence.pivot_index)

    lows = df["low"].astype(float).to_list()
    n = len(lows)
    uncovered = []
    for i in range(5, n - 5):
        window = lows[i - 5:i] + lows[i + 1:i + 6]
        if all(lows[i] <= other for other in window):
            pivots = low_pivots.get(lows[i], [])
            if not any(abs(p - i) <= 5 for p in pivots):
                uncovered.append((i, lows[i]))
    assert not uncovered, f"tie-killed extremes remain invisible: {uncovered}"
