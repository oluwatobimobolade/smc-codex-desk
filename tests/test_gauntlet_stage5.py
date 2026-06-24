import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from smc_desk.data.schemas import Candle
from smc_desk.perception.fvg import FVGDetector
from smc_desk.perception.structure import StructureDetector
from smc_desk.perception.ontology import Direction, SwingObject, SwingEvidence, ConfirmationStatus, MitigationStatus

def make_candle(t: datetime, open: str, high: str, low: str, close: str) -> Candle:
    return Candle(
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=t,
        close_time=t + timedelta(minutes=15),
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        trade_count=100,
        is_closed=True,
        is_complete=True,
        contains_gap=False
    )

def test_minimal_pair_fvg_mitigation():
    """Pair A and B differ by exactly 1 tick on the 4th candle's low.
    Pair A misses mitigation. Pair B touches and mitigates."""
    detector = FVGDetector()
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    decision_time = t0 + timedelta(hours=10)

    # Bullish FVG [100.0, 105.0]
    c1 = make_candle(t0, "90", "100.0", "80", "95")
    c2 = make_candle(t0 + timedelta(minutes=15), "95", "110", "90", "105")
    c3 = make_candle(t0 + timedelta(minutes=30), "105", "120", "105.0", "115")

    # Pair A: Low is 105.1 (Misses by 1 tick)
    c4_a = make_candle(t0 + timedelta(minutes=45), "115", "120", "105.1", "118")
    fvgs_a = detector.detect([c1, c2, c3, c4_a], decision_time)
    
    assert len(fvgs_a) == 1
    assert fvgs_a[0].mitigation_status == MitigationStatus.UNTOUCHED

    # Pair B: Low is 105.0 (Exact mitigation touch)
    c4_b = make_candle(t0 + timedelta(minutes=45), "115", "120", "105.0", "118")
    fvgs_b = detector.detect([c1, c2, c3, c4_b], decision_time)
    
    assert len(fvgs_b) == 1
    assert fvgs_b[0].mitigation_status == MitigationStatus.PARTIAL


def test_minimal_pair_fvg_existence():
    """Pair A and B differ by exactly 1 tick on the 3rd candle's low.
    Pair A: gap is 0 (No FVG). Pair B: gap is 0.1 (FVG exists)."""
    detector = FVGDetector()
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    decision_time = t0 + timedelta(hours=10)

    c1 = make_candle(t0, "90", "100.0", "80", "95")
    c2 = make_candle(t0 + timedelta(minutes=15), "95", "110", "90", "105")
    
    # Pair A: low is 100.0 (Gap = 0)
    c3_a = make_candle(t0 + timedelta(minutes=30), "105", "120", "100.0", "115")
    fvgs_a = detector.detect([c1, c2, c3_a], decision_time)
    assert len(fvgs_a) == 0

    # Pair B: low is 100.1 (Gap = 0.1)
    c3_b = make_candle(t0 + timedelta(minutes=30), "105", "120", "100.1", "115")
    fvgs_b = detector.detect([c1, c2, c3_b], decision_time)
    assert len(fvgs_b) == 1


def test_minimal_pair_bos_confirmation():
    """Pair A and B differ by exactly 1 tick on the close of the breaking candle.
    Pair A: close is 100.0 (Equal to high, no break).
    Pair B: close is 100.1 (Confirmed BOS)."""
    detector = StructureDetector()
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    decision_time = t0 + timedelta(hours=10)

    swing_high = SwingObject(
        object_id="test_swing",
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=t0 - timedelta(minutes=30),
        candidate_at=t0 - timedelta(minutes=15),
        confirmed_at=t0,
        current_as_of=decision_time,
        schema_version="1.0",
        detector_version="1",
        configuration_hash="1",
        source_candle_ids=[],
        last_updated_at=datetime.now(timezone.utc),
        confidence=1.0,
        direction=Direction.BEARISH,
        price_low=Decimal("90"),
        price_high=Decimal("100.0"),
        evidence=SwingEvidence(
            bars_left=1, bars_right=1, prominence_atr_pct=0, is_external=True
        )
    )

    c_swing_confirm = make_candle(t0 - timedelta(minutes=15), "95", "99", "90", "95")

    # Pair A: close is 100.0 (Unconfirmed probe)
    c_probe = make_candle(t0, "95", "105", "90", "100.0")
    state_a, breaks_a = detector.detect([c_swing_confirm, c_probe], [swing_high], decision_time)
    assert len(breaks_a) == 1
    assert breaks_a[0].confirmation_status == ConfirmationStatus.CANDIDATE

    # Pair B: close is 100.1 (Confirmed BOS)
    c_break = make_candle(t0, "95", "105", "90", "100.1")
    state_b, breaks_b = detector.detect([c_swing_confirm, c_break], [swing_high], decision_time)
    assert len(breaks_b) == 1
    assert breaks_b[0].confirmation_status == ConfirmationStatus.CONFIRMED

