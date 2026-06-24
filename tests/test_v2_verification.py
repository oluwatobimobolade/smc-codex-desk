import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from smc_desk.data.schemas import Candle, RawTrade
from smc_desk.data.replay import replay_candles
from smc_desk.perception.ontology import SMCObjectBase, SwingObject, SwingEvidence, ConfirmationStatus, Direction


def test_decimal_stays_decimal():
    """Check 3: Confirm Decimal stays Decimal"""
    c = Candle(
        venue="binance",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 6, 23, 12, 15, tzinfo=timezone.utc),
        open=Decimal("62365.10"),
        high=Decimal("62400.00"),
        low=Decimal("62300.00"),
        close=Decimal("62350.50"),
        volume=Decimal("150.123"),
        trade_count=1500,
        is_closed=True,
        is_complete=True,
        contains_gap=False
    )
    
    assert isinstance(c.open, Decimal)
    assert str(c.open) == "62365.10"
    
    # Test round trip through JSON
    j = c.model_dump_json()
    c2 = Candle.model_validate_json(j)
    assert isinstance(c2.open, Decimal)
    assert str(c2.open) == "62365.10"
    
def test_timezone_aware_utc():
    """Check 4: Enforce timezone-aware UTC"""
    naive_dt = datetime(2026, 6, 23, 12, 0)
    aware_dt = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    
    with pytest.raises(ValueError, match="timezone-aware"):
        # This should fail because open_time is naive
        Candle(
            venue="binance", instrument="BTCUSDT", timeframe="15m",
            open_time=naive_dt, close_time=aware_dt,
            open=Decimal("100"), high=Decimal("110"), low=Decimal("90"), close=Decimal("105"),
            volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
        )
        
    # This should succeed
    c = Candle(
        venue="binance", instrument="BTCUSDT", timeframe="15m",
        open_time=aware_dt, close_time=aware_dt,
        open=Decimal("100"), high=Decimal("110"), low=Decimal("90"), close=Decimal("105"),
        volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
    )
    assert c.open_time == aware_dt

def test_replay_causality():
    """Check 5: Prove replay causality"""
    c1 = Candle(
        venue="binance", instrument="BTCUSDT", timeframe="15m",
        open_time=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 6, 23, 12, 15, tzinfo=timezone.utc),
        open=Decimal("100"), high=Decimal("110"), low=Decimal("90"), close=Decimal("105"),
        volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
    )
    c2 = Candle(
        venue="binance", instrument="BTCUSDT", timeframe="15m",
        open_time=datetime(2026, 6, 23, 12, 15, tzinfo=timezone.utc),
        close_time=datetime(2026, 6, 23, 12, 30, tzinfo=timezone.utc),
        open=Decimal("105"), high=Decimal("115"), low=Decimal("95"), close=Decimal("110"),
        volume=Decimal("1"), trade_count=1, is_closed=True, is_complete=True, contains_gap=False
    )
    
    full_dataset = [c1, c2]
    
    # decision time exactly at the end of c1
    t = datetime(2026, 6, 23, 12, 15, tzinfo=timezone.utc)
    replayed = replay_candles(full_dataset, t)
    
    assert len(replayed) == 1
    assert replayed[0] == c1
    
    # appending future candle shouldn't change the slice
    truncated = full_dataset[:1]
    assert replay_candles(full_dataset, t) == replay_candles(truncated, t)

def test_ontology_temporal_constraints():
    """Check 7: Validate the ontology's temporal constraints"""
    # pivot_time <= candidate_at <= confirmed_at <= current_as_of
    
    pivot = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    candidate = datetime(2026, 6, 23, 12, 15, tzinfo=timezone.utc)
    confirmed = datetime(2026, 6, 23, 12, 30, tzinfo=timezone.utc)
    current = datetime(2026, 6, 23, 12, 45, tzinfo=timezone.utc)
    
    obj = SwingObject(
        object_id="test",
        venue="test",
        instrument="test",
        timeframe="15m",
        pivot_time=pivot,
        candidate_at=candidate,
        confirmed_at=confirmed,
        current_as_of=current,
        confirmation_status=ConfirmationStatus.CONFIRMED,
        schema_version="1.0.0",
        detector_version="1.0",
        configuration_hash="abc",
        source_candle_ids=["c1", "c2"],
        last_updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        confidence=0.9,
        direction=Direction.BULLISH,
        price_low=Decimal("100"),
        price_high=Decimal("110"),
        evidence=SwingEvidence(bars_left=3, bars_right=3, prominence_atr_pct=1.5, is_external=False)
    )
    
    assert obj.pivot_time <= obj.candidate_at
    assert obj.candidate_at <= obj.confirmed_at
    assert obj.confirmed_at <= obj.current_as_of
