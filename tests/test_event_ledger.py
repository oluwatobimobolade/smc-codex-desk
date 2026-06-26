"""Tests for the canonical event ledger."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.colleague.event_ledger import (
    CanonicalEvent,
    EventLedger,
    EventType,
)
from smc_desk.perception.engine_v2 import PerceptionEngineV2, PerceptionSnapshot
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    FairValueGapEvidence,
    FairValueGapObject,
    StructureBreakEvidence,
    StructureBreakObject,
    SwingEvidence,
    SwingObject,
)


def _make_swing(
    object_id: str,
    direction: str,
    pivot_time: datetime,
    confirmed_at: datetime,
    price_high: Decimal,
    price_low: Decimal,
) -> SwingObject:
    """Helper to create a SwingObject."""
    return SwingObject(
        object_id=object_id,
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=pivot_time,
        candidate_at=pivot_time,
        confirmed_at=confirmed_at,
        current_as_of=confirmed_at,
        schema_version="1.0.0",
        detector_version="2.0",
        configuration_hash="abc123",
        source_candle_ids=["c_1", "c_2", "c_3"],
        last_updated_at=confirmed_at,
        confidence=0.0,
        direction=direction,
        price_high=price_high,
        price_low=price_low,
        evidence=SwingEvidence(
            bars_left=2,
            bars_right=2,
            prominence_atr_pct=1.5,
            is_external=True,
        ),
    )


def _make_break(
    object_id: str,
    break_type: str,
    direction: str,
    candidate_at: datetime,
    confirmed_at: datetime | None,
    broken_price: Decimal,
) -> StructureBreakObject:
    """Helper to create a StructureBreakObject."""
    confirmation_status = ConfirmationStatus.CONFIRMED if confirmed_at else ConfirmationStatus.CANDIDATE
    # Infer is_choch from break_type
    is_choch = (break_type == "CHOCH")
    
    return StructureBreakObject(
        object_id=object_id,
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=candidate_at - timedelta(minutes=15),
        candidate_at=candidate_at,
        confirmed_at=confirmed_at,
        current_as_of=confirmed_at or candidate_at,
        schema_version="1.0.0",
        detector_version="2.0",
        configuration_hash="abc123",
        source_candle_ids=["c_10"],
        last_updated_at=confirmed_at or candidate_at,
        confidence=0.0,
        direction=direction,
        price_low=broken_price - Decimal("0.5"),
        price_high=broken_price + Decimal("0.5"),
        break_type=break_type,
        evidence=StructureBreakEvidence(
            broken_swing_id="swing_1",
            broken_price=broken_price,
            wick_penetration=Decimal("0.2"),
            body_close_penetration=Decimal("0.1") if confirmed_at else Decimal("0.0"),
            penetration_ticks=2,
            penetration_atr_pct=0.5,
            candle_body_ratio=0.8,
            displacement_strength=0.0,
            is_internal=False,
            is_unconfirmed_probe=confirmed_at is None,
        ),
        confirmation_status=confirmation_status,
        is_choch=is_choch,
        object_type="structure_break",
    )


def _make_fvg(
    object_id: str,
    direction: str,
    pivot_time: datetime,
    confirmed_at: datetime,
    price_high: Decimal,
    price_low: Decimal,
    is_mitigated: bool = False,
) -> FairValueGapObject:
    """Helper to create a FairValueGapObject."""
    return FairValueGapObject(
        object_id=object_id,
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=pivot_time,
        candidate_at=pivot_time,
        confirmed_at=confirmed_at,
        current_as_of=confirmed_at,
        schema_version="1.0.0",
        detector_version="2.0",
        configuration_hash="abc123",
        source_candle_ids=["c_5", "c_6", "c_7"],
        last_updated_at=confirmed_at,
        confidence=0.0,
        direction=direction,
        price_high=price_high,
        price_low=price_low,
        evidence=FairValueGapEvidence(
            gap_size_ticks=10,
            gap_size_bps=5.0,
            atr_ratio=0.8,
            is_mitigated_on_creation=is_mitigated,
        ),
        object_type="fvg",
        mitigated_price=price_low if is_mitigated else None,
        mitigation_percent=100.0 if is_mitigated else 0.0,
    )


def _make_snapshot(
    swings: dict[str, list[SwingObject]],
    breaks: list[StructureBreakObject],
    fvgs: list[FairValueGapObject],
    decision_time: datetime,
) -> PerceptionSnapshot:
    """Helper to create a PerceptionSnapshot."""
    # Convert model instances to dicts for Pydantic v2 validation
    swings_dict = {k: [s.model_dump() for s in v] for k, v in swings.items()}
    breaks_dicts = [b.model_dump() for b in breaks]
    fvgs_dicts = [f.model_dump() for f in fvgs]
    
    return PerceptionSnapshot(
        decision_time=decision_time,
        swings=swings_dict,
        structure_state={"current_direction": "bullish"},
        structure_breaks=breaks_dicts,
        fvgs=fvgs_dicts,
    )


class TestEventLedger:
    """Test the canonical event ledger."""

    def test_empty_snapshot_produces_empty_ledger(self):
        """An empty snapshot should produce an empty ledger."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        snapshot = _make_snapshot({}, [], [], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 0
        assert ledger.decision_time == dt
        assert ledger.ontology_version == "2.0.0"

    def test_swing_produces_confirmed_event(self):
        """A confirmed swing should produce a SWING_CONFIRMED event."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing = _make_swing(
            object_id="swing_high_1",
            direction="bearish",
            pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt,
            price_high=Decimal("100.5"),
            price_low=Decimal("99.5"),
        )
        snapshot = _make_snapshot({"external": [swing]}, [], [], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 1
        event = ledger.events[0]
        assert event.event_type == EventType.SWING_CONFIRMED
        assert event.timeframe == "15m"
        assert event.occurred_at == dt - timedelta(minutes=30)
        assert event.available_at == dt
        assert event.object_ids == ["swing_high_1"]
        assert event.provisional is False
        assert event.metadata["direction"] == "bearish"
        assert event.metadata["scale"] == "external"

    def test_break_candidate_produces_candidate_event(self):
        """A candidate break should produce a STRUCTURE_BREAK_CANDIDATE event."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        brk = _make_break(
            object_id="break_1",
            break_type="BOS",
            direction="bullish",
            candidate_at=dt,
            confirmed_at=None,
            broken_price=Decimal("100.0"),
        )
        snapshot = _make_snapshot({}, [brk], [], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 1
        event = ledger.events[0]
        assert event.event_type == EventType.STRUCTURE_BREAK_CANDIDATE
        assert event.provisional is True
        assert event.metadata["break_type"] == "BOS"
        assert event.metadata["direction"] == "bullish"

    def test_confirmed_break_produces_two_events(self):
        """A confirmed break should produce both CANDIDATE and CONFIRMED events."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        brk = _make_break(
            object_id="break_1",
            break_type="CHOCH",
            direction="bearish",
            candidate_at=dt - timedelta(minutes=15),
            confirmed_at=dt,
            broken_price=Decimal("100.0"),
        )
        snapshot = _make_snapshot({}, [brk], [], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 2
        candidate = ledger.events[0]
        confirmed = ledger.events[1]
        assert candidate.event_type == EventType.STRUCTURE_BREAK_CANDIDATE
        assert confirmed.event_type == EventType.STRUCTURE_BREAK_CONFIRMED
        assert candidate.provisional is True
        assert confirmed.provisional is False

    def test_fvg_produces_created_event(self):
        """An FVG should produce a FVG_CREATED event."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        fvg = _make_fvg(
            object_id="fvg_1",
            direction="bullish",
            pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt,
            price_high=Decimal("100.5"),
            price_low=Decimal("100.0"),
        )
        snapshot = _make_snapshot({}, [], [fvg], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 1
        event = ledger.events[0]
        assert event.event_type == EventType.FVG_CREATED
        assert event.metadata["direction"] == "bullish"
        assert event.metadata["gap_size_bps"] == "5.0"

    def test_mitigated_fvg_produces_two_events(self):
        """A mitigated FVG should produce both CREATED and MITIGATED events."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        fvg = _make_fvg(
            object_id="fvg_1",
            direction="bullish",
            pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt,
            price_high=Decimal("100.5"),
            price_low=Decimal("100.0"),
            is_mitigated=True,
        )
        snapshot = _make_snapshot({}, [], [fvg], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 2
        created = ledger.events[0]
        mitigated = ledger.events[1]
        assert created.event_type == EventType.FVG_CREATED
        assert mitigated.event_type == EventType.FVG_MITIGATED

    def test_events_sorted_by_available_at(self):
        """Events should be sorted by available_at, then event_type, then object_id."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing1 = _make_swing(
            object_id="swing_1",
            direction="bearish",
            pivot_time=dt - timedelta(minutes=60),
            confirmed_at=dt - timedelta(minutes=30),
            price_high=Decimal("100.5"),
            price_low=Decimal("99.5"),
        )
        swing2 = _make_swing(
            object_id="swing_2",
            direction="bullish",
            pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt,
            price_high=Decimal("101.5"),
            price_low=Decimal("100.5"),
        )
        fvg = _make_fvg(
            object_id="fvg_1",
            direction="bullish",
            pivot_time=dt - timedelta(minutes=45),
            confirmed_at=dt - timedelta(minutes=15),
            price_high=Decimal("100.5"),
            price_low=Decimal("100.0"),
        )
        snapshot = _make_snapshot({"external": [swing1, swing2]}, [], [fvg], dt)
        ledger = EventLedger.from_snapshot(snapshot)

        # Should be sorted: swing_1 (11:30), fvg_1 (11:45), swing_2 (12:00)
        assert len(ledger.events) == 3
        assert ledger.events[0].object_ids == ["swing_1"]
        assert ledger.events[1].object_ids == ["fvg_1"]
        assert ledger.events[2].object_ids == ["swing_2"]

    def test_deterministic_event_ids(self):
        """Same input should produce same event IDs."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing = _make_swing(
            object_id="swing_1",
            direction="bearish",
            pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt,
            price_high=Decimal("100.5"),
            price_low=Decimal("99.5"),
        )
        snapshot = _make_snapshot({"external": [swing]}, [], [], dt)

        ledger1 = EventLedger.from_snapshot(snapshot)
        ledger2 = EventLedger.from_snapshot(snapshot)

        assert ledger1.events[0].event_id == ledger2.events[0].event_id

    def test_deterministic_ledger_serialization(self):
        """Same input should produce same serialized ledger."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing = _make_swing(
            object_id="swing_1",
            direction="bearish",
            pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt,
            price_high=Decimal("100.5"),
            price_low=Decimal("99.5"),
        )
        brk = _make_break(
            object_id="break_1",
            break_type="BOS",
            direction="bullish",
            candidate_at=dt - timedelta(minutes=15),
            confirmed_at=dt,
            broken_price=Decimal("100.0"),
        )
        fvg = _make_fvg(
            object_id="fvg_1",
            direction="bullish",
            pivot_time=dt - timedelta(minutes=45),
            confirmed_at=dt - timedelta(minutes=30),
            price_high=Decimal("100.5"),
            price_low=Decimal("100.0"),
        )
        snapshot = _make_snapshot({"external": [swing]}, [brk], [fvg], dt)

        ledger1 = EventLedger.from_snapshot(snapshot)
        ledger2 = EventLedger.from_snapshot(snapshot)

        json1 = ledger1.model_dump_json()
        json2 = ledger2.model_dump_json()
        assert json1 == json2

    def test_multiple_scales_produce_multiple_events(self):
        """Swings at different scales should each produce an event."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        local_swing = _make_swing(
            object_id="swing_local",
            direction="bearish",
            pivot_time=dt - timedelta(minutes=15),
            confirmed_at=dt,
            price_high=Decimal("100.2"),
            price_low=Decimal("99.8"),
        )
        external_swing = _make_swing(
            object_id="swing_external",
            direction="bullish",
            pivot_time=dt - timedelta(minutes=60),
            confirmed_at=dt,
            price_high=Decimal("101.5"),
            price_low=Decimal("98.5"),
        )
        snapshot = _make_snapshot(
            {"local": [local_swing], "external": [external_swing]},
            [],
            [],
            dt,
        )
        ledger = EventLedger.from_snapshot(snapshot)

        assert len(ledger.events) == 2
        # Check that both scales are represented
        scales = {e.metadata["scale"] for e in ledger.events}
        assert scales == {"local", "external"}

    def test_duplicate_suppression(self):
        """Processing the same snapshot twice must not create duplicate events."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing = _make_swing(
            object_id="swing_dup",
            direction="bearish", pivot_time=dt - timedelta(minutes=30),
            confirmed_at=dt, price_high=Decimal("100.5"), price_low=Decimal("99.5"),
        )
        snapshot = _make_snapshot({"external": [swing]}, [], [], dt)
        ledger1 = EventLedger.from_snapshot(snapshot)
        ledger2 = EventLedger.from_snapshot(snapshot)
        assert len(ledger1.events) == len(ledger2.events)
        assert ledger1.replay_idempotent(ledger2)

    def test_replay_idempotence(self):
        """Two ledgers from the same snapshot must be byte-identical."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing = _make_swing(
            object_id="swing_replay",
            direction="bullish", pivot_time=dt - timedelta(hours=1),
            confirmed_at=dt, price_high=Decimal("101.0"), price_low=Decimal("99.0"),
        )
        brk = _make_break(
            object_id="break_replay", break_type="BOS", direction="bullish",
            candidate_at=dt - timedelta(minutes=15), confirmed_at=dt,
            broken_price=Decimal("100.5"),
        )
        snapshot = _make_snapshot({"external": [swing]}, [brk], [], dt)
        ledger1 = EventLedger.from_snapshot(snapshot)
        ledger2 = EventLedger.from_snapshot(snapshot)
        assert ledger1.replay_idempotent(ledger2)
        # Serializations must match
        assert ledger1.model_dump_json() == ledger2.model_dump_json()

    def test_event_schema_version_is_present(self):
        """Every event must carry an event_schema_version."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        swing = _make_swing(
            object_id="swing_version", direction="bearish",
            pivot_time=dt - timedelta(minutes=30), confirmed_at=dt,
            price_high=Decimal("100.5"), price_low=Decimal("99.5"),
        )
        snapshot = _make_snapshot({"external": [swing]}, [], [], dt)
        ledger = EventLedger.from_snapshot(snapshot)
        for event in ledger.events:
            assert event.event_schema_version == "1.0.0"
            assert event.detector_version == "2.0"

    def test_provisional_vs_confirmed_separation(self):
        """Candidate events are provisional; confirmed events are not."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        # Candidate break (not confirmed)
        brk = _make_break(
            object_id="break_prov", break_type="BOS", direction="bullish",
            candidate_at=dt, confirmed_at=None, broken_price=Decimal("100.0"),
        )
        snapshot = _make_snapshot({}, [brk], [], dt)
        ledger = EventLedger.from_snapshot(snapshot)
        assert ledger.provisional_count() >= 1
        assert ledger.confirmed_count() >= 0
