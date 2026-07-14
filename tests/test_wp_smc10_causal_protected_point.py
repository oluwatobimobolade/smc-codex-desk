"""WP-SMC-10 Commit 2: causal protected-point selection (flag-gated, abstain fallback).

When ``SMC_CAUSAL_PROTECTED_POINT`` is OFF, structure._confirm_break behaves
exactly as before: protected_low/high := last_confirmed_* (the VGM-006 / V1
forbidden_shortcuts recency assignment).

When the flag is ON, the causal-necessity algorithm
(smc_desk.structure.protected_point.select) runs against the confirmed break
+ the swing pool + the candles. The full ProtectedPointSelection is ALWAYS
recorded in ``brk.metadata['protected_point_selection']``. Override of
``track.protected_*`` happens only when the selected candidate maps to an
actual SwingObject (cluster/candle picks cannot replace SwingObject-typed
fields). Otherwise the legacy assignment is kept.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from smc_desk.perception.causal_repair_flags import causal_protected_point_enabled
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    StructureBreakEvidence,
    StructureBreakObject,
    SwingEvidence,
    SwingObject,
)
from smc_desk.perception.structure import (
    StructureDetector,
    _match_candidate_to_swing,
    _run_causal_protected_point_selection,
)


# -------- fixtures ----------------------------------------------------------

def _candle(t: datetime, o: str, h: str, l: str, c: str) -> object:
    from smc_desk.data.schemas import Candle
    return Candle(
        venue="BINANCE",
        market="usdm-perp",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=t, close_time=t + timedelta(minutes=15),
        open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c),
        volume=Decimal("100"), trade_count=100,
        is_closed=True, is_complete=True, contains_gap=False,
    )


def _swing(object_id: str, direction: Direction, *, low: str, high: str,
           pivot: datetime, confirmed: datetime, scale: str) -> SwingObject:
    return SwingObject(
        object_id=object_id,
        venue="BINANCE", market="usdm-perp",
        instrument="BTCUSDT", timeframe="15m",
        pivot_time=pivot, candidate_at=pivot + timedelta(minutes=15),
        confirmed_at=confirmed, current_as_of=confirmed,
        schema_version="1.0.0", detector_version="test",
        configuration_hash="wp_smc10_test",
        source_candle_ids=[f"c_{pivot.timestamp()}"],
        last_updated_at=confirmed,
        confidence=1.0, direction=direction,
        price_low=Decimal(low), price_high=Decimal(high),
        evidence=SwingEvidence(
            bars_left=3 if scale == "internal" else 5,
            bars_right=3 if scale == "internal" else 5,
            prominence_atr_pct=1.0,
            is_external=(scale == "external"),
            scale_name=scale,  # type: ignore[arg-type]
        ),
    )


def _confirmed_break_fixture():
    """Reuse the established confirming-bullish-external-break fixture from
    tests/test_wp0022_smc_detector_rebuild.py::test_external_choch_requires_body_close_through_protected_swing.
    It produces exactly one confirmed bullish external break via StructureDetector.detect.
    """
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        _candle(t0, "100", "105", "99", "101"),
        _candle(t0 + timedelta(minutes=15), "101", "102", "95.2", "96"),
        _candle(t0 + timedelta(minutes=30), "96", "97", "89", "90"),
        _candle(t0 + timedelta(minutes=45), "90", "101", "90", "99"),
        _candle(t0 + timedelta(minutes=60), "99", "104", "95", "101"),
        _candle(t0 + timedelta(minutes=75), "101", "113", "100", "112"),
    ]
    swings = [
        _swing("external_high_110", Direction.BEARISH, low="108", high="110",
               pivot=t0, confirmed=candles[0].close_time, scale="external"),
        _swing("external_low_95", Direction.BULLISH, low="95", high="97",
               pivot=t0 + timedelta(minutes=15), confirmed=candles[1].close_time,
               scale="external"),
    ]
    return candles, swings


# -------- flag default -----------------------------------------------------

def test_causal_protected_point_flag_default_off(monkeypatch):
    """Flag must default OFF -> zero behaviour change at this commit."""
    monkeypatch.delenv("SMC_CAUSAL_PROTECTED_POINT", raising=False)
    assert causal_protected_point_enabled() is False


# -------- adapter + match unit tests ---------------------------------------

def test_run_causal_protected_point_selection_produces_dict_or_none():
    """Adapter must return a mapping (or None when no candidates) without raising."""
    candles, swings = _confirmed_break_fixture()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Build a minimal confirmed bullish break referencing external_low_95.
    brk = StructureBreakObject(
        object_id="test_break",
        venue="BINANCE", market="usdm-perp", instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=t0 + timedelta(minutes=15),
        candidate_at=t0 + timedelta(minutes=15),
        confirmed_at=t0 + timedelta(minutes=75),
        current_as_of=t0 + timedelta(minutes=75),
        schema_version="1.0.0", detector_version="test",
        configuration_hash="wp_smc10_test",
        source_candle_ids=[f"c_{(t0 + timedelta(minutes=75)).timestamp()}"],
        last_updated_at=t0 + timedelta(minutes=75),
        confidence=1.0, direction=Direction.BULLISH,
        price_low=Decimal("101"), price_high=Decimal("113"),
        break_type="BOS", structure_scope="external",
        is_choch=False, confirmation_status=ConfirmationStatus.CONFIRMED,
        evidence=StructureBreakEvidence(
            broken_swing_id="external_high_110",
            broken_price=Decimal("110"),
            wick_penetration=Decimal("3.0"),
            body_close_penetration=Decimal("2.0"),
            penetration_ticks=200,
            penetration_atr_pct=1.0,
            candle_body_ratio=0.85,
            displacement_strength=0.0,
            is_internal=False, is_unconfirmed_probe=False,
            structure_scope="external",
        ),
    )

    out = _run_causal_protected_point_selection(
        brk=brk, swings=swings, candles=candles, current_time=t0 + timedelta(minutes=75),
    )
    # The fixture's only opposing pivot (external_low_95) has a pivot_price
    # within 1bp of the protected high (110) -- no, the algorithm wants a LOW
    # pivot for a bullish break (required_pivot_type='low'). external_low_95
    # at price 95-97 is the candidate. The algorithm may produce a mapping
    # with selected/abstained/rationale, OR None if it abstained at selection.
    if out is not None:
        assert "abstained" in out
        assert "rationale" in out
        assert "selected" in out
        assert "graph_relationships" in out


def test_match_candidate_to_swing_matches_within_tolerance():
    """A candidate whose pivot_price matches a registered swing (within 5bps)
    is matched; direction must agree (bullish break -> protect a low).
    external_low_95 has price_low=95; 5bps tol = 0.0475, so 95.02 matches."""
    candles, swings = _confirmed_break_fixture()
    cand = {"pivot_price": 95.02, "candidate_id": "external_low_95#internal"}
    matched = _match_candidate_to_swing(cand, swings, Direction.BULLISH)
    assert matched is not None
    assert matched.object_id == "external_low_95"


def test_match_candidate_to_swing_returns_none_outside_tolerance():
    """A candidate price far from any swing does NOT override."""
    candles, swings = _confirmed_break_fixture()
    cand = {"pivot_price": 200.0, "candidate_id": "far#away"}
    matched = _match_candidate_to_swing(cand, swings, Direction.BULLISH)
    assert matched is None


def test_match_candidate_to_swing_direction_mismatch_returns_none():
    """For a bullish break we protect a LOW; a HIGH swing is not a match."""
    candles, swings = _confirmed_break_fixture()
    cand = {"pivot_price": 109.0, "candidate_id": "external_high_110#internal"}
    matched = _match_candidate_to_swing(cand, swings, Direction.BULLISH)
    assert matched is None


def test_match_candidate_to_swing_handles_string_price():
    """The candidate mapping may carry price as Decimal/str/float; tolerance is robust."""
    candles, swings = _confirmed_break_fixture()
    cand = {"pivot_price": "95.0"}
    matched = _match_candidate_to_swing(cand, swings, Direction.BULLISH)
    assert matched is not None and matched.object_id == "external_low_95"


# -------- confirm-break flag gating ----------------------------------------

def test_confirm_break_does_not_record_selection_when_flag_off(monkeypatch):
    """Flag OFF -> no ``protected_point_selection`` key on confirmed breaks.
    Zero-behaviour-change contract for Commit 2."""
    monkeypatch.delenv("SMC_CAUSAL_PROTECTED_POINT", raising=False)
    candles, swings = _confirmed_break_fixture()
    state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
    confirmed = [b for b in breaks if b.confirmation_status == ConfirmationStatus.CONFIRMED]
    assert confirmed, "fixture must produce at least one confirmed break"
    for brk in confirmed:
        assert "protected_point_selection" not in brk.metadata


def test_confirm_break_records_selection_when_flag_on(monkeypatch):
    """Flag ON -> every confirmed break records ``protected_point_selection``
    in its metadata. Whether the algorithm abstained or applied an override
    is recorded inside the mapping."""
    monkeypatch.setenv("SMC_CAUSAL_PROTECTED_POINT", "1")
    candles, swings = _confirmed_break_fixture()
    state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
    confirmed = [b for b in breaks if b.confirmation_status == ConfirmationStatus.CONFIRMED]
    assert confirmed
    for brk in confirmed:
        assert "protected_point_selection" in brk.metadata
        sel = brk.metadata["protected_point_selection"]
        assert "abstained" in sel
        assert "rationale" in sel
        assert "selected" in sel
        # When abstained: override must be False (legacy kept)
        if sel["abstained"]:
            assert sel.get("applied_override") in (False, None)


def test_confirm_break_swallows_algorithm_errors_and_falls_back(monkeypatch):
    """If the causal algorithm raises mid-detect, detection must not fail.
    The break is still confirmed and metadata records the error fallback."""
    monkeypatch.setenv("SMC_CAUSAL_PROTECTED_POINT", "1")

    # Force _run_causal_protected_point_selection to raise.
    import smc_desk.perception.structure as struct_module
    original = struct_module._run_causal_protected_point_selection
    struct_module._run_causal_protected_point_selection = lambda *a, **k: (
        (_ for _ in ()).throw(RuntimeError("synthetic causal failure"))
    )
    try:
        candles, swings = _confirmed_break_fixture()
        state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
        confirmed = [b for b in breaks if b.confirmation_status == ConfirmationStatus.CONFIRMED]
        assert confirmed, "detection must survive algorithm errors"
        for brk in confirmed:
            sel = brk.metadata["protected_point_selection"]
            assert sel.get("abstained") is True
            assert sel.get("fallback_reason", "").startswith("causal_selection_error")
    finally:
        struct_module._run_causal_protected_point_selection = original


def test_confirm_break_keeps_legacy_assignment_when_flag_off(monkeypatch):
    """Flag OFF -> state.protected_high_id stays at the legacy recency swing
    (the VGM-006 forbidden_shortcut assignment), matching the pre-WP behaviour."""
    monkeypatch.delenv("SMC_CAUSAL_PROTECTED_POINT", raising=False)
    candles, swings = _confirmed_break_fixture()
    state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
    # The fixture ends with state.current_direction == Direction.BULLISH (the
    # break flipped the bias). The legacy protected_high assignment is
    # last_confirmed_external_high -- which is "external_high_110".
    # The protected_low assignment for a bullish break is last_confirmed_low.
    assert state.current_direction == Direction.BULLISH
    assert state.protected_high_id == "external_high_110"
    assert state.protected_low_id == "external_low_95"