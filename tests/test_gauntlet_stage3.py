from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

from smc_desk.data.schemas import Candle
from smc_desk.perception.fvg import FVGDetector
from smc_desk.perception.structure import StructureDetector, ProtectedStructureState
from smc_desk.perception.ontology import Direction, SwingObject, SwingEvidence, ConfirmationStatus

def make_candle(open_time: datetime, open_price: str, high: str, low: str, close: str) -> Candle:
    return Candle(
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=15),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        quote_asset_volume=Decimal("10000"),
        trade_count=100,
        taker_buy_base=Decimal("50"),
        taker_buy_quote=Decimal("5000"),
        contains_gap=False,
        is_complete=True,
        is_closed=True
    )

def test_objective_fvg_geometry():
    detector = FVGDetector()
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    decision_time = t0 + timedelta(hours=10)

    # 1. Normal Bullish FVG
    # c1 high is 100, c3 low is 110. Gap is 10.
    c1 = make_candle(t0, "90", "100", "80", "95")
    c2 = make_candle(t0 + timedelta(minutes=15), "95", "120", "90", "115")
    c3 = make_candle(t0 + timedelta(minutes=30), "115", "130", "110", "125")
    
    fvgs = detector.detect([c1, c2, c3], decision_time)
    assert len(fvgs) == 1
    assert fvgs[0].direction == Direction.BULLISH
    assert fvgs[0].price_low == Decimal("100")
    assert fvgs[0].price_high == Decimal("110")

    # 2. Touching candles with zero gap
    # c1 high is 100, c3 low is 100. Gap is 0.
    c1 = make_candle(t0, "90", "100", "80", "95")
    c2 = make_candle(t0 + timedelta(minutes=15), "95", "120", "90", "115")
    c3 = make_candle(t0 + timedelta(minutes=30), "115", "130", "100", "125")
    
    fvgs = detector.detect([c1, c2, c3], decision_time)
    assert len(fvgs) == 0 # Must be strictly less than for bullish

    # 3. Wick overlap
    # c1 high is 100, c3 low is 99. Gap is -1.
    c3 = make_candle(t0 + timedelta(minutes=30), "115", "130", "99", "125")
    fvgs = detector.detect([c1, c2, c3], decision_time)
    assert len(fvgs) == 0

    # 4. One-tick FVG
    # c1 high is 100.0, c3 low is 100.1
    c1 = make_candle(t0, "90", "100.0", "80", "95")
    c2 = make_candle(t0 + timedelta(minutes=15), "95", "120", "90", "115")
    c3 = make_candle(t0 + timedelta(minutes=30), "115", "130", "100.1", "125")
    fvgs = detector.detect([c1, c2, c3], decision_time)
    assert len(fvgs) == 1
    assert fvgs[0].price_high - fvgs[0].price_low == Decimal("0.1")

    # 5. Nested FVGs & Overlapping
    # An array of 4 candles creating 2 FVGs
    # c1 high 100
    # c2 high 110, low 90
    # c3 high 120, low 105 -> Bullish FVG gap [100, 105] from c1-c3
    # c4 high 130, low 115 -> Bullish FVG gap [110, 115] from c2-c4

    c1 = make_candle(t0, "90", "100", "80", "95")
    c2 = make_candle(t0 + timedelta(minutes=15), "95", "110", "90", "105")
    c3 = make_candle(t0 + timedelta(minutes=30), "105", "120", "105", "115")
    c4 = make_candle(t0 + timedelta(minutes=45), "115", "130", "115", "125")
    fvgs = detector.detect([c1, c2, c3, c4], decision_time)
    assert len(fvgs) == 2
    assert fvgs[0].price_low == Decimal("100")
    assert fvgs[0].price_high == Decimal("105")
    assert fvgs[1].price_low == Decimal("110")
    assert fvgs[1].price_high == Decimal("115")


def test_minimal_pair_wick_vs_body():
    detector = StructureDetector()
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    decision_time = t0 + timedelta(hours=10)

    # We need a protected high swing first.
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
        direction=Direction.BEARISH, # High
        price_low=Decimal("90"),
        price_high=Decimal("100"),
        evidence=SwingEvidence(
            bars_left=1, bars_right=1, prominence_atr_pct=0, is_external=True
        )
    )

    c_swing_confirm = make_candle(t0 - timedelta(minutes=15), "95", "99", "90", "95") # closes at t0

    # Chart A: Wick crosses 100, body remains below.
    c_probe = make_candle(t0, "95", "105", "90", "99") # opens at t0, closes at t0+15m
    state_a, breaks_a = detector.detect([c_swing_confirm, c_probe], [swing_high], decision_time)
    
    assert len(breaks_a) == 1
    assert breaks_a[0].confirmation_status == ConfirmationStatus.CANDIDATE
    assert breaks_a[0].evidence.is_unconfirmed_probe == True
    assert state_a.current_direction is None # State direction does not change on probe
    
    # Chart B: Body crosses 100 by ONE TICK
    c_break = make_candle(t0, "95", "105", "90", "100.1")
    state_b, breaks_b = detector.detect([c_swing_confirm, c_break], [swing_high], decision_time)

    assert len(breaks_b) == 1
    assert breaks_b[0].confirmation_status == ConfirmationStatus.CONFIRMED
    assert breaks_b[0].evidence.is_unconfirmed_probe == False
    assert state_b.current_direction == Direction.BULLISH
