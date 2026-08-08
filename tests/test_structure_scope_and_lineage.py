"""Regression tests for the two structural defects from the 2026-07-14 audit.

F1 — cross-scope protected-point substitution
    Protected-point candidates were pooled across every swing scale with the
    structure scope discarded, then matched back by price within 5bps and
    direction alone. A local or internal pivot at a similar price could
    therefore become an *external* break's protected point: 34 substitutions
    on 1,500 BTCUSDT candles, 19 on SOLUSDT. Doctrine is explicit that equal
    prices never make two swing ids interchangeable.

F2 — mixed-candle displacement
    A break object is created on the wick-probe candle, so its body ratio and
    price_low/high describe that candle. When confirmation arrived later, only
    body_close_penetration was updated, so displacement was scored from the
    probe's body and the confirmation's penetration. On real data this read a
    0.82 body-ratio impulse as -0.17.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from smc_desk.data.schemas import Candle
from smc_desk.perception.displacement import score_break_displacement
from smc_desk.perception.ontology import Direction
from smc_desk.perception.structure import StructureDetector, _match_candidate_to_swing
from smc_desk.perception.swings import MultiScaleSwingDetector, SwingDetector

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


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
    return [_mk(i, *v) for i, v in enumerate(vals)]


def _flat(n, px=100.0, amp=0.05):
    return [(px, px + amp, px - amp, px) for _ in range(n)]


# -- F1: scope locking --------------------------------------------------------


def _swing_at(price, *, scale, index=6, bars=5):
    """Build one confirmed swing low of the requested scale at ``price``."""
    vals = _flat(index, 100.0) + [(100, 100.1, price, price + 0.5)] + _flat(bars + 2, 100.0)
    candles = _series(vals)
    return SwingDetector(bars_left=bars, bars_right=bars, scale_name=scale).detect(
        candles, candles[-1].close_time
    )


def test_external_break_cannot_adopt_a_local_swing_at_the_same_price():
    """The F1 failure, reproduced directly against the matcher."""
    external = _swing_at(95.0, scale="external", bars=5)
    local = _swing_at(95.0, scale="local", bars=1)
    assert external and local, "fixture must produce both scales"

    pool = external + local
    # A candidate naming the LOCAL swing must not resolve while the break is
    # external, even though an identically priced external swing exists.
    candidate = {"candidate_id": local[0].object_id + "#internal",
                 "pivot_price": 95.0}
    matched = _match_candidate_to_swing(
        candidate, pool, Direction.BULLISH, scope="external", timeframe="15m"
    )
    assert matched is None, "a local pivot must never satisfy an external break"


def test_identity_match_wins_over_an_equally_priced_neighbour():
    external = _swing_at(95.0, scale="external", bars=5)
    assert external
    candidate = {"candidate_id": external[0].object_id + "#internal", "pivot_price": 95.0}
    matched = _match_candidate_to_swing(
        candidate, external, Direction.BULLISH, scope="external", timeframe="15m"
    )
    assert matched is not None and matched.object_id == external[0].object_id


def test_unknown_id_refuses_rather_than_sliding_to_a_near_price():
    """An id that names nothing in scope must fail closed."""
    external = _swing_at(95.0, scale="external", bars=5)
    candidate = {"candidate_id": "ghost_swing#internal", "pivot_price": 95.0}
    matched = _match_candidate_to_swing(
        candidate, external, Direction.BULLISH, scope="external", timeframe="15m"
    )
    assert matched is None


def test_cross_timeframe_substitution_is_refused():
    external = _swing_at(95.0, scale="external", bars=5)
    assert external
    candidate = {"candidate_id": external[0].object_id, "pivot_price": 95.0}
    matched = _match_candidate_to_swing(
        candidate, external, Direction.BULLISH, scope="external", timeframe="4h"
    )
    assert matched is None, "a 15m swing cannot protect a 4h break"


def test_cluster_origin_still_resolves_by_price_within_scope():
    """Non-swing origins legitimately have no id and may match on geometry."""
    external = _swing_at(95.0, scale="external", bars=5)
    assert external
    candidate = {"extreme_price": 95.0}      # cluster origin: no candidate_id
    matched = _match_candidate_to_swing(
        candidate, external, Direction.BULLISH, scope="external", timeframe="15m"
    )
    assert matched is not None


def test_no_confirmed_break_adopts_an_out_of_scope_protected_point():
    """End-to-end: every applied override stays inside its own scope."""
    from smc_desk.perception.structure import _scope_for_swing

    vals = _flat(6, 100.0)
    vals += [(100, 100.2, 92, 93)]
    vals += _flat(5, 94.0)
    vals += [(94, 105, 93.8, 104)]
    vals += _flat(5, 103.0)
    vals += [(103, 103.2, 96, 96.5)]
    vals += _flat(4, 97.0)
    vals += [(97, 108, 96.9, 107.5)]
    vals += _flat(6, 107.0)
    candles = _series(vals)
    now = candles[-1].close_time
    scales = MultiScaleSwingDetector().detect(candles, now)
    every = scales["external"] + scales["internal"] + scales["local"]
    scope_of = {s.object_id: _scope_for_swing(s) for s in every}

    _, breaks = StructureDetector().detect(candles, every, now)
    for brk in breaks:
        selection = (brk.metadata or {}).get("protected_point_selection") or {}
        if not selection.get("applied_override"):
            continue
        matched_id = selection.get("matched_swing_id")
        assert scope_of.get(matched_id) == str(brk.structure_scope), (
            f"{brk.object_id} adopted a {scope_of.get(matched_id)} swing as "
            f"{brk.structure_scope} protected structure"
        )


# -- F2: break-candle lineage -------------------------------------------------


def _delayed_confirmation_series():
    """Wick probe on one candle, strong body close two candles later."""
    vals = _flat(6, 100.0)
    vals += [(100, 110, 99.9, 101)]        # 6: swing high at 110
    vals += _flat(6, 101.0)                # confirms at 11
    vals += [(101, 110.4, 100.6, 100.8)]   # 13: WICK probe over 110, bearish body
    vals += _flat(3, 100.5)
    vals += [(100.6, 112.0, 100.5, 111.6)] # 17: strong bullish body close above 110
    vals += _flat(6, 111.0)
    return _series(vals)


def test_probe_and_confirmation_candles_are_recorded_separately():
    candles = _delayed_confirmation_series()
    now = candles[-1].close_time
    swings = SwingDetector(bars_left=5, bars_right=5, scale_name="external").detect(candles, now)
    _, breaks = StructureDetector().detect(candles, swings, now)
    confirmed = [b for b in breaks if _dv(b.confirmation_status) == "confirmed"]
    assert confirmed, "fixture must confirm a break"
    brk = confirmed[0]
    ev = brk.evidence
    assert ev.probe_candle_id and ev.body_close_candle_id
    assert ev.probe_candle_id != ev.body_close_candle_id
    assert ev.is_delayed_confirmation is True
    assert ev.confirmation_candle_body_ratio is not None


def test_confirmation_body_ratio_reflects_the_confirming_candle():
    """The probe was bearish-bodied; the confirmation was a strong bull candle."""
    candles = _delayed_confirmation_series()
    now = candles[-1].close_time
    swings = SwingDetector(bars_left=5, bars_right=5, scale_name="external").detect(candles, now)
    _, breaks = StructureDetector().detect(candles, swings, now)
    brk = [b for b in breaks if _dv(b.confirmation_status) == "confirmed"][0]
    assert brk.evidence.candle_body_ratio < 0, "probe candle closed against the break"
    assert brk.evidence.confirmation_candle_body_ratio > 0.5, "confirming candle was a strong body"


def test_same_candle_confirmation_is_not_flagged_delayed():
    vals = _flat(6, 100.0)
    vals += [(100, 110, 99.9, 101)]
    vals += _flat(6, 101.0)
    vals += [(101, 112, 100.9, 111.5)]     # wick and body close on one candle
    vals += _flat(6, 111.0)
    candles = _series(vals)
    now = candles[-1].close_time
    swings = SwingDetector(bars_left=5, bars_right=5, scale_name="external").detect(candles, now)
    _, breaks = StructureDetector().detect(candles, swings, now)
    brk = [b for b in breaks if _dv(b.confirmation_status) == "confirmed"][0]
    assert brk.evidence.is_delayed_confirmation is False
    assert brk.evidence.probe_candle_id == brk.evidence.body_close_candle_id


def test_displacement_scores_the_confirming_candle_when_available():
    """The scorer must prefer confirmation geometry over probe geometry."""
    payload = {
        "direction": "bullish",
        "price_low": 100.0, "price_high": 110.4,        # PROBE candle geometry
        "evidence": {
            "candle_body_ratio": -0.17,                  # probe: closed against
            "confirmation_candle_body_ratio": 0.82,      # confirmation: strong
            "confirmation_candle_range": 11.5,
            "body_close_penetration": 1.6,
            "broken_price": 110.0,
            "wick_penetration": 2.0,
        },
    }
    profile = score_break_displacement(payload)
    assert profile.body_to_range_ratio == pytest.approx(0.82)


def test_displacement_falls_back_to_probe_geometry_for_legacy_objects():
    """Objects recorded before this repair must still score, not crash."""
    payload = {
        "direction": "bullish",
        "price_low": 100.0, "price_high": 110.4,
        "evidence": {
            "candle_body_ratio": 0.55,
            "body_close_penetration": 1.6,
            "broken_price": 110.0,
            "wick_penetration": 2.0,
        },
    }
    profile = score_break_displacement(payload)
    assert profile.body_to_range_ratio == pytest.approx(0.55)
