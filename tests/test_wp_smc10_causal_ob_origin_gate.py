"""WP-SMC-10 Commit 3: causal OB-origin gate (flag-gated; default ON after cutover).

The order-block detector's origin definition is a geometric color+body-ratio
heuristic. The WP-SMC-10 repair adds a displacement admission gate: an origin
cluster is admitted as an OB only when its departure produced measured
displacement into the accepted break (smc_desk.perception.displacement score
>= moderate quality). When the gate rejects a cluster, the OB is NOT emitted;
the admission record (``metadata['causal_origin_admission']``) is always
attached for audit, even on emitted OBs.

When SMC_CAUSAL_OB_ORIGIN_GATE is OFF, every geometric candidate is admitted
(legacy). When ON, only displacing clusters are admitted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from smc_desk.perception.causal_repair_flags import (
    causal_ob_origin_gate_enabled,
)
from smc_desk.perception.order_blocks import _admit_origin_cluster
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    StructureBreakEvidence,
    StructureBreakObject,
)


def _confirmed_break(*, displacement_meta: dict | None) -> StructureBreakObject:
    t = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    brk = StructureBreakObject(
        object_id=f"bos_bullish_{int(t.timestamp())}",
        venue="BINANCE", market="usdm-perp",
        instrument="BTCUSDT", timeframe="15m",
        pivot_time=t, candidate_at=t, confirmed_at=t, current_as_of=t,
        schema_version="1.0.0", detector_version="test",
        configuration_hash="wp_smc10_test",
        source_candle_ids=[f"c_{int(t.timestamp())}"],
        last_updated_at=t,
        confidence=1.0, direction=Direction.BULLISH,
        price_low=Decimal("104"), price_high=Decimal("110"),
        break_type="BOS", structure_scope="external",
        is_choch=False, confirmation_status=ConfirmationStatus.CONFIRMED,
        evidence=StructureBreakEvidence(
            broken_swing_id="swing",
            broken_price=Decimal("110"),
            wick_penetration=Decimal("2.0"),
            body_close_penetration=Decimal("2.0"),
            penetration_ticks=200,
            penetration_atr_pct=1.0,
            candle_body_ratio=0.85,
            displacement_strength=0.85 if displacement_meta else 0.0,
            is_internal=False, is_unconfirmed_probe=False,
            structure_scope="external",
        ),
    )
    if displacement_meta is not None:
        brk.metadata["displacement"] = displacement_meta
    return brk


def test_gate_flag_default_on_after_cutover(monkeypatch):
    """After cutover the origin-gate flag defaults ON; legacy OFF is opt-in."""
    monkeypatch.delenv("SMC_CAUSAL_OB_ORIGIN_GATE", raising=False)
    assert causal_ob_origin_gate_enabled() is True


def test_admit_disabled_gate_admits_anything(monkeypatch):
    """Gate OFF -> admitted with reason 'gate_disabled' regardless of displacement."""
    monkeypatch.setenv("SMC_CAUSAL_OB_ORIGIN_GATE", "0")
    # No displacement metadata at all; gate-off must still admit.
    brk = _confirmed_break(displacement_meta=None)
    out = _admit_origin_cluster(brk, departure_ids=["c_x"])
    assert out["admitted"] is True
    assert out["gate"] == "disabled"


def test_admit_enabled_requires_displacement_metadata(monkeypatch):
    """Gate ON + no displacement metadata on break -> admitted=False."""
    monkeypatch.setenv("SMC_CAUSAL_OB_ORIGIN_GATE", "1")
    brk = _confirmed_break(displacement_meta=None)
    out = _admit_origin_cluster(brk, departure_ids=["c_x"])
    assert out["admitted"] is False
    assert out["reason"] == "no_displacement_profile_on_break"


def test_admit_enabled_requires_departure(monkeypatch):
    """Gate ON + no departure -> admitted=False with reason 'no_departure_trace'."""
    monkeypatch.setenv("SMC_CAUSAL_OB_ORIGIN_GATE", "1")
    brk = _confirmed_break(displacement_meta={"score": 0.85, "break_quality": "strong",
                                              "close_beyond_structure_bps": 100.0})
    out = _admit_origin_cluster(brk, departure_ids=[])
    assert out["admitted"] is False
    assert out["reason"] == "no_departure_trace"


def test_admit_enabled_rejects_weak_displacement(monkeypatch):
    """Gate ON + low score/bps -> admitted=False with departure_lacks_displacement."""
    monkeypatch.setenv("SMC_CAUSAL_OB_ORIGIN_GATE", "1")
    brk = _confirmed_break(displacement_meta={
        "score": 0.20, "break_quality": "weak",
        "close_beyond_structure_bps": 2.0,
    })
    out = _admit_origin_cluster(brk, departure_ids=["c_x", "c_y"])
    assert out["admitted"] is False
    assert out["reason"] == "departure_lacks_displacement"
    assert out["thresholds"]["min_score"] == 0.45
    assert out["thresholds"]["min_bps"] == 4.0


def test_admit_enabled_accepts_moderate_displacement(monkeypatch):
    """Gate ON + moderate quality (score >= 0.45, bps >= 4.0) -> admitted=True."""
    monkeypatch.setenv("SMC_CAUSAL_OB_ORIGIN_GATE", "1")
    brk = _confirmed_break(displacement_meta={
        "score": 0.60, "break_quality": "moderate",
        "close_beyond_structure_bps": 15.0,
    })
    out = _admit_origin_cluster(brk, departure_ids=["c_x", "c_y", "c_z"])
    assert out["admitted"] is True
    assert out["gate"] == "enabled"
    assert out["break_quality"] == "moderate"
    assert out["score"] == pytest.approx(0.60)


def test_admit_enabled_accepts_strong_displacement(monkeypatch):
    """Gate ON + strong quality -> admitted=True."""
    monkeypatch.setenv("SMC_CAUSAL_OB_ORIGIN_GATE", "1")
    brk = _confirmed_break(displacement_meta={
        "score": 0.92, "break_quality": "strong",
        "close_beyond_structure_bps": 50.0,
    })
    out = _admit_origin_cluster(brk, departure_ids=["c_x"])
    assert out["admitted"] is True
    assert out["break_quality"] == "strong"