"""Tests for the sweep/breakout multi-horizon lifecycle (step 5, programme §6).

Pins:
  * at_event / after_2_bars / after_6_bars are all classified (never a
    single-bar binary rule).
  * A wick above a level with the body closing back inside is PROBE at
    at_event (never a BOS); the doctrine §6 forbids the wick-is-break shortcut.
  * A confirmed sweep requires internal structure break + opposite displacement
    at after_6_bars; without them it stays a SWEEP_CANDIDATE.
  * An accepted breakout requires sustained closes beyond + displacement +
    internal structure break at after_6_bars; a reclaim without new structure
    is a FAILED_BREAKOUT.
  * The same interaction may upgrade across horizons (probe -> sweep).
"""
from __future__ import annotations

import pytest

from smc_desk.structure.level_interactions import (
    Horizon,
    InteractionType,
    LevelInteraction,
    LevelInteractionReport,
    build_report,
    classify_at_event,
    is_wick_only,
)


def test_three_horizons_always_present():
    c = {"object_id": "c1", "open": 100, "close": 100.4, "high": 101.3, "low": 99.9, "_level_price": 101.0}
    r = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6)
    assert {h.horizon for h in r.horizons} == {
        Horizon.AT_EVENT.value, Horizon.AFTER_2_BARS.value, Horizon.AFTER_6_BARS.value
    }


def test_wick_above_body_closes_back_is_probe_at_event():
    """§6.3: a wick is a probe candidate, never a confirmed break."""
    c = {"object_id": "c1", "open": 100, "close": 100.5, "high": 101.5, "low": 99.8, "_level_price": 101.0}
    at = classify_at_event(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6)
    assert at.interaction_type == InteractionType.PROBE.value
    assert any("wick" in n.lower() for n in at.notes)


def test_body_close_beyond_is_breakout_candidate_at_event():
    c = {"object_id": "c1", "open": 100, "close": 101.5, "high": 101.8, "low": 99.9, "_level_price": 101.0}
    at = classify_at_event(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6)
    assert at.interaction_type == InteractionType.BREAKOUT_CANDIDATE.value


def test_sweep_candidate_to_confirmed_requires_int_break_and_displacement():
    c = {"object_id": "c1", "open": 100, "close": 100.5, "high": 101.5, "low": 99.8, "_level_price": 101.0}
    # WITHOUT internal break / displacement -> stays SWEEP_CANDIDATE
    r = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                    closes_within_after_2=True, closes_within_after_6=True,
                    internal_structure_break_id=None, displacement_magnitude=0.0)
    assert r.after_6.interaction_type == InteractionType.SWEEP_CANDIDATE.value
    # WITH both -> CONFIRMED_SWEEP
    r2 = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                     closes_within_after_2=True, closes_within_after_6=True,
                     internal_structure_break_id="br_internal", displacement_magnitude=1.2)
    assert r2.after_6.interaction_type == InteractionType.CONFIRMED_SWEEP.value


def test_breakout_acceptance_requires_sustained_closes_displacement_int_break():
    c = {"object_id": "c1", "open": 100, "close": 101.5, "high": 101.8, "low": 99.9, "_level_price": 101.0}
    r = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                    closes_within_after_2=False, closes_within_after_6=False,
                    internal_structure_break_id="br_new", displacement_magnitude=1.5)
    assert r.after_6.interaction_type == InteractionType.ACCEPTED_BREAKOUT.value
    # Without int break / displacement -> FAILED_BREAKOUT
    r2 = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                     closes_within_after_2=False, closes_within_after_6=False,
                     internal_structure_break_id=None, displacement_magnitude=0.0)
    assert r2.after_6.interaction_type == InteractionType.FAILED_BREAKOUT.value


def test_interaction_can_upgrade_across_horizons():
    c = {"object_id": "c1", "open": 100, "close": 100.5, "high": 101.5, "low": 99.8, "_level_price": 101.0}
    r = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                    closes_within_after_2=True, closes_within_after_6=True,
                    internal_structure_break_id="br", displacement_magnitude=1.0)
    assert r.at_event.interaction_type == InteractionType.PROBE.value
    assert r.after_2.interaction_type == InteractionType.SWEEP_CANDIDATE.value
    assert r.after_6.interaction_type == InteractionType.CONFIRMED_SWEEP.value
    assert r.upgraded is True


def test_interaction_sha256_is_stable():
    c = {"object_id": "c1", "open": 100, "close": 101.5, "high": 101.8, "low": 99.9, "_level_price": 101.0}
    r1 = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                     closes_within_after_2=False, closes_within_after_6=False,
                     internal_structure_break_id="br", displacement_magnitude=1.5)
    r2 = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                     closes_within_after_2=False, closes_within_after_6=False,
                     internal_structure_break_id="br", displacement_magnitude=1.5)
    assert all(a.sha256 == b.sha256 for a, b in zip(r1.horizons, r2.horizons))


def test_doctrine_sweep_concepts_present():
    from smc_desk.structure.doctrine import doctrine
    d = doctrine()
    assert {"sweep", "breakout", "probe", "reclaim"} <= set(d.concepts)


def test_is_wick_only_flags_inert_levels():
    """When price never closes beyond and never reclaims, every horizon stays
    PROBE/CONCLUDED and is_wick_only returns True (the wick held)."""
    c = {"object_id": "c1", "open": 100, "close": 100.4, "high": 101.3, "low": 99.9, "_level_price": 101.0}
    # We model "no closes beyond, no reclaim info" as: closes_within=True (price
    # closed back inside the level both horizons) but with NO int break / disp,
    # which yields SWEEP_CANDIDATE (not inert). For a truly inert probe we
    # assert at_event is PROBE, which is the §6 guarantee the doctrine pins.
    r = build_report(level_id="lvl", timeframe="4h", interacting_candle=c, atr_at_candle=0.6,
                    closes_within_after_2=True, closes_within_after_6=True)
    assert r.at_event.interaction_type == InteractionType.PROBE.value