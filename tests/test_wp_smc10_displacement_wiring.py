"""WP-SMC-10 Commit 1: canonical displacement scoring is wired behind a flag.

When the canonical-displacement-scoring flag is OFF, confirmed breaks keep the
legacy hardcoded ``displacement_strength=0.0``. When the flag is ON, each
confirmed break's evidence is enriched in-place by
``smc_desk.perception.engine_v2._enrich_breaks_with_displacement`` using
``smc_desk.perception.displacement.score_break_displacement``.

We exercise the enrichment helper directly and spy on it from
``engine_v2.analyze`` so the flag-gating contract is verified independently
of whether the synthetic candle fixture produces a real confirmed break.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from smc_desk.perception.causal_repair_flags import (
    canonical_displacement_scoring_enabled,
)
from smc_desk.perception.engine_v2 import _enrich_breaks_with_displacement
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    StructureBreakEvidence,
    StructureBreakObject,
)


def _build_break(*, body_ratio: float, body_pen: Decimal, broken_price: Decimal,
                 fvg_tick_gap: bool = False) -> StructureBreakObject:
    """Hand-build a confirmed external bullish break with controllable displacement."""
    t = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    candle_high = Decimal("105.50")
    return StructureBreakObject(
        object_id=f"bos_bullish_{int(t.timestamp())}",
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=t,
        candidate_at=t,
        confirmed_at=t,
        current_as_of=t,
        schema_version="1.0.0",
        detector_version="test",
        configuration_hash="wp_smc10_test",
        source_candle_ids=[f"c_{int(t.timestamp())}"],
        last_updated_at=t,
        confidence=1.0,
        direction=Direction.BULLISH,
        price_low=Decimal("104.50"),
        price_high=candle_high,
        break_type="BOS",
        structure_scope="external",
        is_choch=False,
        confirmation_status=ConfirmationStatus.CONFIRMED,
        evidence=StructureBreakEvidence(
            broken_swing_id="swing_test",
            broken_price=broken_price,
            wick_penetration=Decimal("0.50"),
            body_close_penetration=body_pen,
            penetration_ticks=50,
            penetration_atr_pct=1.0,
            candle_body_ratio=body_ratio,
            displacement_strength=0.0,
            is_internal=False,
            is_unconfirmed_probe=False,
            structure_scope="external",
            protected_swing_id=None,
            last_bos_swing_id=None,
            broke_protected_swing=False,
            valid_choch=False,
        ),
    )


def test_enrichment_flags_are_off_by_default(monkeypatch):
    """The flag must default OFF so this commit is a zero-behaviour-change addition."""
    monkeypatch.delenv("SMC_CANONICAL_DISPLACEMENT_SCORING", raising=False)
    assert canonical_displacement_scoring_enabled() is False


def test_enrichment_breaks_with_strong_displacement_get_positive_score():
    """A fat-body, close-beyond-12bps break should score > 0.75 (strong)."""
    brk = _build_break(
        body_ratio=0.80,
        body_pen=Decimal("2.0"),
        broken_price=Decimal("100.00"),
    )
    _enrich_breaks_with_displacement([brk], fvgs=[])

    assert brk.evidence.displacement_strength > 0.0
    meta = brk.metadata["displacement"]
    assert meta["break_quality"] in {"moderate", "strong"}
    assert meta["valid_for_bias_flip"] is (meta["break_quality"] == "strong")
    assert meta["scoring_version"] == "wp_smc10_canonical_v1"
    assert meta["body_to_range_ratio"] == pytest.approx(0.80, abs=1e-6)
    # close_beyond_structure_bps = 2.00 / 100.00 * 10_000 = 200 bps
    assert meta["close_beyond_structure_bps"] == pytest.approx(200.0, abs=1e-6)


def test_enrichment_skips_unconfirmed_probes():
    """Candidate/probe breaks (is_unconfirmed_probe=True) must not be enriched."""
    brk = _build_break(body_ratio=0.80, body_pen=Decimal("2.0"), broken_price=Decimal("100.00"))
    brk.confirmation_status = ConfirmationStatus.CANDIDATE
    brk.evidence.is_unconfirmed_probe = True
    brk.confirmed_at = None

    _enrich_breaks_with_displacement([brk], fvgs=[])

    assert brk.evidence.displacement_strength == 0.0
    assert "displacement" not in brk.metadata


def test_enrichment_swallows_scorer_errors_and_keeps_legacy_zero():
    """If score_break_displacement raises, legacy 0.0 is preserved -- never fails analyse()."""
    import smc_desk.perception.displacement as displacement_mod

    original = displacement_mod.score_break_displacement
    displacement_mod.score_break_displacement = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("synthetic scorer failure")
    )
    try:
        brk = _build_break(body_ratio=0.80, body_pen=Decimal("2.0"), broken_price=Decimal("100.00"))
        _enrich_breaks_with_displacement([brk], fvgs=[])
        assert brk.evidence.displacement_strength == 0.0
        assert "displacement" not in brk.metadata
    finally:
        displacement_mod.score_break_displacement = original


def test_engine_v2_analyze_does_not_enrich_when_flag_off(monkeypatch):
    """Flag OFF -> analyze must never call _enrich_breaks_with_displacement."""
    monkeypatch.delenv("SMC_CANONICAL_DISPLACEMENT_SCORING", raising=False)
    import smc_desk.perception.engine_v2 as engine_v2_module
    calls = {"n": 0}
    original = engine_v2_module._enrich_breaks_with_displacement
    def spy(*a, **k):
        calls["n"] += 1
        return original(*a, **k)
    monkeypatch.setattr(engine_v2_module, "_enrich_breaks_with_displacement", spy)

    engine = _build_engine()
    engine.analyze(_flat_candles(), decision_time=_flat_candles()[-1].close_time)
    assert calls["n"] == 0, "enrichment must not run when flag is OFF"


def test_engine_v2_analyze_enriches_when_flag_on(monkeypatch):
    """Flag ON -> analyze must call _enrich_breaks_with_displacement exactly once."""
    monkeypatch.setenv("SMC_CANONICAL_DISPLACEMENT_SCORING", "1")
    import smc_desk.perception.engine_v2 as engine_v2_module
    calls = {"n": 0}
    original = engine_v2_module._enrich_breaks_with_displacement
    def spy(*a, **k):
        calls["n"] += 1
        return original(*a, **k)
    monkeypatch.setattr(engine_v2_module, "_enrich_breaks_with_displacement", spy)

    engine = _build_engine()
    engine.analyze(_flat_candles(), decision_time=_flat_candles()[-1].close_time)
    assert calls["n"] == 1, "enrichment must run exactly once when flag is ON"


def _flat_candles():
    """Minimal candle sequence sufficient to clear engine_v2's OOD/duplicate guards."""
    from smc_desk.data.schemas import Candle

    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(6):
        open_t = base + timedelta(minutes=15 * i)
        candles.append(
            Candle(
                venue="binance",
                market="usdm-perp",
                instrument="BTCUSDT",
                timeframe="15m",
                open_time=open_t, close_time=open_t + timedelta(minutes=15),
                open=Decimal("100"), high=Decimal("105"), low=Decimal("95"), close=Decimal("100"),
                volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False,
            )
        )
    return candles


def _build_engine():
    from smc_desk.perception.engine_v2 import PerceptionEngineV2

    return PerceptionEngineV2(
        expected_instrument="BTCUSDT",
        expected_timeframe="15m",
    )