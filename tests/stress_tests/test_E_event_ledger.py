import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smc_desk.data.schemas import Candle
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    ActivityStatus,
    MitigationStatus,
    TerminalReason,
    Direction,
    FairValueGapObject,
    FairValueGapEvidence
)
from smc_desk.perception.fvg import FVGDetector
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event, replay_events

@pytest.fixture
def base_fvg() -> FairValueGapObject:
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return FairValueGapObject(
        object_id="fvg_1",
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=dt,
        candidate_at=dt,
        current_as_of=dt,
        detector_version="1.0.0",
        configuration_hash="hash",
        source_candle_ids=["c1", "c2", "c3"],
        last_updated_at=dt,
        confidence=1.0,
        direction=Direction.BULLISH,
        price_low=Decimal("100"),
        price_high=Decimal("110"),
        evidence=FairValueGapEvidence(
            gap_size_ticks=10,
            gap_size_bps=1.0,
            atr_ratio=1.5,
            is_mitigated_on_creation=False
        )
    )

def test_e1_replay_idempotence(base_fvg):
    """
    E1: Replay Idempotence
    Feeding the exact same market events twice must yield no duplicate 
    lifecycle transitions and identical final state.
    """
    dt = datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc)
    events = [
        SMCEvent(event_type=EventType.OBJECT_CREATED, timestamp=dt, trigger_candle_id="c1"),
        SMCEvent(event_type=EventType.OBJECT_CONFIRMED, timestamp=dt, trigger_candle_id="c2"),
        SMCEvent(event_type=EventType.OBJECT_ACTIVATED, timestamp=dt, trigger_candle_id="c3"),
        SMCEvent(event_type=EventType.OBJECT_PARTIALLY_MITIGATED, timestamp=dt, trigger_candle_id="c4"),
    ]
    
    # Play once
    for ev in events:
        apply_event(base_fvg, ev)
        
    ledger_len_after_first_replay = len(base_fvg.events)
    state1 = {
        "conf": base_fvg.confirmation_status,
        "act": base_fvg.activity_status,
        "mit": base_fvg.mitigation_status
    }
    
    # Play exactly the same events again (idempotent replay)
    for ev in events:
        apply_event(base_fvg, ev)
        
    state2 = {
        "conf": base_fvg.confirmation_status,
        "act": base_fvg.activity_status,
        "mit": base_fvg.mitigation_status
    }
    
    assert state1 == state2
    assert len(base_fvg.events) == ledger_len_after_first_replay
    assert base_fvg.activity_status == ActivityStatus.ACTIVE
    assert base_fvg.mitigation_status == MitigationStatus.PARTIAL

def test_e2_out_of_order_lifecycle_events(base_fvg):
    """
    E2: Out-of-Order Lifecycle Events
    Assert the engine rejects impossible sequences (e.g., FULLY_MITIGATED before ACTIVATED).
    """
    dt = datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc)
    
    # Setup initial state to be CREATED but NOT ACTIVATED
    apply_event(base_fvg, SMCEvent(event_type=EventType.OBJECT_CREATED, timestamp=dt, trigger_candle_id="c1"))
    
    # Trying to apply FULLY_MITIGATED should fail if it was never ACTIVATED
    invalid_event = SMCEvent(event_type=EventType.OBJECT_FULLY_MITIGATED, timestamp=dt, trigger_candle_id="c2")
    
    with pytest.raises(ValueError, match="Cannot transition"):
        apply_event(base_fvg, invalid_event)

def test_e3_state_reconstruction(base_fvg):
    """
    E3: State Reconstruction
    Rebuilding purely from the append-only event ledger ensures an exact match to derived state.
    """
    dt = datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc)
    events = [
        SMCEvent(event_type=EventType.OBJECT_CREATED, timestamp=dt, trigger_candle_id="c1"),
        SMCEvent(event_type=EventType.OBJECT_CONFIRMED, timestamp=dt, trigger_candle_id="c2"),
        SMCEvent(event_type=EventType.OBJECT_ACTIVATED, timestamp=dt, trigger_candle_id="c3"),
        SMCEvent(event_type=EventType.OBJECT_FULLY_MITIGATED, timestamp=dt, trigger_candle_id="c4"),
    ]
    
    # Manually derive
    derived_obj = base_fvg.model_copy()
    replay_events(derived_obj, events)
    
    assert derived_obj.activity_status == ActivityStatus.TERMINAL
    assert derived_obj.mitigation_status == MitigationStatus.FULL
    assert derived_obj.terminal_reason == TerminalReason.CONSUMED

def test_e4_supersession_conflict(base_fvg):
    """
    E4: Supersession Conflict
    Verifying that superseded states remain isolated when newer events occur.
    """
    dt = datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc)
    apply_event(base_fvg, SMCEvent(event_type=EventType.OBJECT_CREATED, timestamp=dt, trigger_candle_id="c1"))
    apply_event(base_fvg, SMCEvent(event_type=EventType.OBJECT_SUPERSEDED, timestamp=dt, trigger_candle_id="c2"))
    
    assert base_fvg.activity_status == ActivityStatus.TERMINAL
    assert base_fvg.terminal_reason == TerminalReason.SUPERSEDED
    
    # If a stray event tries to activate it after supersession, it should fail
    with pytest.raises(ValueError, match="Cannot transition"):
        apply_event(base_fvg, SMCEvent(event_type=EventType.OBJECT_ACTIVATED, timestamp=dt, trigger_candle_id="c3"))


def _candle(dt: datetime, minutes: int, o: str, h: str, l: str, c: str) -> Candle:
    open_time = dt + timedelta(minutes=minutes)
    return Candle(
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=15),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal("1000"),
        trade_count=100,
        is_complete=True,
        is_closed=True,
        contains_gap=False,
    )


def test_e5_detector_mitigation_events_are_recorded():
    """
    E5: Detector lifecycle integration
    FVG detection must not mutate mitigation status without ledger events.
    """
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = [
        _candle(dt, 0, "100", "100", "95", "96"),
        _candle(dt, 15, "96", "112", "96", "110"),
        _candle(dt, 30, "110", "115", "105", "113"),
        _candle(dt, 45, "113", "114", "103", "104"),
        _candle(dt, 60, "104", "106", "99", "100"),
    ]

    fvgs = FVGDetector().detect(candles, candles[-1].close_time)

    assert len(fvgs) == 1
    fvg = fvgs[0]
    event_types = [event.event_type for event in fvg.events]
    assert EventType.OBJECT_ACTIVATED in event_types
    assert EventType.OBJECT_PARTIALLY_MITIGATED in event_types
    assert EventType.OBJECT_FULLY_MITIGATED in event_types
    assert fvg.mitigation_status == MitigationStatus.FULL
    assert fvg.activity_status == ActivityStatus.TERMINAL
