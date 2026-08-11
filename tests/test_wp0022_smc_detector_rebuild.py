from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smc_desk.data.schemas import Candle
from smc_desk.perception.fvg import FairValueGapObject
from smc_desk.perception.inducement import InducementDetector
from smc_desk.perception.liquidity import LiquidityLevelDetector, SweepDetector
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    FairValueGapEvidence,
    InducementObject,
    OrderBlockObject,
    StructureBreakEvidence,
    StructureBreakObject,
    SweepEvidence,
    SweepObject,
    SwingEvidence,
    SwingObject,
)
from smc_desk.perception.order_blocks import OrderBlockDetector, mark_poi_grade_fvgs
from smc_desk.perception.structure import StructureDetector
from smc_desk.perception.structure_hierarchy import build_structure_hierarchy
from smc_desk.perception.swings import SwingDetector


def _candle(t: datetime, o: str, h: str, l: str, c: str) -> Candle:
    return Candle(
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        open_time=t,
        close_time=t + timedelta(minutes=15),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal("100"),
        trade_count=100,
        is_closed=True,
        is_complete=True,
        contains_gap=False,
    )


def _swing(
    object_id: str,
    direction: Direction,
    *,
    low: str,
    high: str,
    pivot: datetime,
    confirmed: datetime,
    scale: str,
) -> SwingObject:
    return SwingObject(
        object_id=object_id,
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=pivot,
        candidate_at=pivot + timedelta(minutes=15),
        confirmed_at=confirmed,
        current_as_of=confirmed,
        schema_version="1.0.0",
        detector_version="test",
        configuration_hash="test",
        source_candle_ids=[f"c_{pivot.timestamp()}"],
        last_updated_at=confirmed,
        confidence=1.0,
        direction=direction,
        price_low=Decimal(low),
        price_high=Decimal(high),
        evidence=SwingEvidence(
            bars_left=3 if scale == "internal" else 5,
            bars_right=3 if scale == "internal" else 5,
            prominence_atr_pct=1.0,
            is_external=(scale == "external"),
            scale_name=scale,  # type: ignore[arg-type]
        ),
    )


def _break(
    object_id: str,
    direction: Direction,
    *,
    candle: Candle,
    broken_price: str,
    confirmed_at: datetime,
) -> StructureBreakObject:
    broken = Decimal(broken_price)
    body_pen = candle.close - broken if direction == Direction.BULLISH else broken - candle.close
    return StructureBreakObject(
        object_id=object_id,
        venue=candle.venue,
        instrument=candle.instrument,
        timeframe=candle.timeframe,
        pivot_time=candle.open_time,
        candidate_at=candle.open_time,
        confirmed_at=confirmed_at,
        current_as_of=confirmed_at,
        schema_version="1.0.0",
        detector_version="test",
        configuration_hash="test",
        source_candle_ids=[f"c_{candle.open_time.timestamp()}"],
        last_updated_at=confirmed_at,
        confidence=1.0,
        direction=direction,
        price_low=candle.low,
        price_high=candle.high,
        break_type="BOS",
        structure_scope="external",
        is_choch=False,
        confirmation_status=ConfirmationStatus.CONFIRMED,
        evidence=StructureBreakEvidence(
            broken_swing_id="swing",
            broken_price=broken,
            wick_penetration=abs(body_pen),
            body_close_penetration=body_pen,
            penetration_ticks=100,
            penetration_atr_pct=1.0,
            candle_body_ratio=0.8,
            displacement_strength=1.0,
            is_internal=False,
            is_unconfirmed_probe=False,
            structure_scope="external",
        ),
    )


def _fvg(object_id: str, direction: Direction, low: str, high: str, t: datetime) -> FairValueGapObject:
    return FairValueGapObject(
        object_id=object_id,
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=t,
        candidate_at=t,
        confirmed_at=t + timedelta(minutes=15),
        current_as_of=t + timedelta(minutes=15),
        schema_version="1.0.0",
        detector_version="test",
        configuration_hash="test",
        source_candle_ids=[f"c_{t.timestamp()}"],
        last_updated_at=t + timedelta(minutes=15),
        confidence=1.0,
        direction=direction,
        price_low=Decimal(low),
        price_high=Decimal(high),
        evidence=FairValueGapEvidence(
            gap_size_ticks=100,
            gap_size_bps=20.0,
            atr_ratio=1.0,
            is_mitigated_on_creation=False,
        ),
    )


def test_swing_detector_records_scale_and_atr_prominence() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        _candle(t0, "100", "101", "99", "100"),
        _candle(t0 + timedelta(minutes=15), "100", "110", "99", "108"),
        _candle(t0 + timedelta(minutes=30), "108", "109", "100", "101"),
    ]

    swings = SwingDetector(1, 1, "internal").detect(candles, candles[-1].close_time)

    assert len(swings) == 1
    assert swings[0].evidence.scale_name == "internal"
    assert swings[0].evidence.prominence_price == Decimal("1")
    assert swings[0].evidence.prominence_atr_pct > 0


def test_structure_detector_separates_internal_choch_from_external_protected_bias() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        _candle(t0, "100", "105", "99", "101"),
        _candle(t0 + timedelta(minutes=15), "101", "102", "95.2", "96"),
        _candle(t0 + timedelta(minutes=30), "96", "97", "89", "90"),
        _candle(t0 + timedelta(minutes=45), "90", "101", "90", "99"),
        _candle(t0 + timedelta(minutes=60), "99", "104", "95", "101"),
    ]
    swings = [
        _swing("external_high_110", Direction.BEARISH, low="108", high="110", pivot=t0, confirmed=candles[0].close_time, scale="external"),
        _swing("external_low_95", Direction.BULLISH, low="95", high="97", pivot=t0 + timedelta(minutes=15), confirmed=candles[1].close_time, scale="external"),
        _swing("internal_low_95", Direction.BULLISH, low="95", high="97", pivot=t0 + timedelta(minutes=15), confirmed=candles[1].close_time, scale="internal"),
        _swing("internal_high_100", Direction.BEARISH, low="98", high="100", pivot=t0 + timedelta(minutes=45), confirmed=candles[3].close_time, scale="internal"),
    ]

    state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
    confirmed = [b for b in breaks if b.confirmation_status == ConfirmationStatus.CONFIRMED]
    external_bullish = [b for b in confirmed if b.direction == Direction.BULLISH and b.structure_scope == "external"]
    internal_bullish = [b for b in confirmed if b.direction == Direction.BULLISH and b.structure_scope == "internal"]

    assert state.current_direction == Direction.BEARISH
    assert state.protected_high_id == "external_high_110"
    assert not external_bullish
    assert len(internal_bullish) == 1
    assert internal_bullish[0].break_type == "CHOCH"
    assert internal_bullish[0].evidence.is_internal is True


def test_external_choch_requires_body_close_through_protected_swing() -> None:
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
        _swing("external_high_110", Direction.BEARISH, low="108", high="110", pivot=t0, confirmed=candles[0].close_time, scale="external"),
        _swing("external_low_95", Direction.BULLISH, low="95", high="97", pivot=t0 + timedelta(minutes=15), confirmed=candles[1].close_time, scale="external"),
    ]

    state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
    bullish_external = [
        b for b in breaks
        if b.confirmation_status == ConfirmationStatus.CONFIRMED
        and b.direction == Direction.BULLISH
        and b.structure_scope == "external"
    ]

    assert state.current_direction == Direction.BULLISH
    assert len(bullish_external) == 1
    assert bullish_external[0].break_type == "CHOCH"
    assert bullish_external[0].evidence.broke_protected_swing is True
    assert bullish_external[0].evidence.valid_choch is True


def test_hierarchy_ignores_v2_internal_breaks_for_external_bias() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        _candle(t0, "100", "105", "99", "101"),
        _candle(t0 + timedelta(minutes=15), "101", "102", "95.2", "96"),
        _candle(t0 + timedelta(minutes=30), "96", "97", "89", "90"),
        _candle(t0 + timedelta(minutes=45), "90", "101", "90", "99"),
        _candle(t0 + timedelta(minutes=60), "99", "104", "95", "101"),
    ]
    swings = [
        _swing("external_high_110", Direction.BEARISH, low="108", high="110", pivot=t0, confirmed=candles[0].close_time, scale="external"),
        _swing("external_low_95", Direction.BULLISH, low="95", high="97", pivot=t0 + timedelta(minutes=15), confirmed=candles[1].close_time, scale="external"),
        _swing("internal_low_95", Direction.BULLISH, low="95", high="97", pivot=t0 + timedelta(minutes=15), confirmed=candles[1].close_time, scale="internal"),
        _swing("internal_high_100", Direction.BEARISH, low="98", high="100", pivot=t0 + timedelta(minutes=45), confirmed=candles[3].close_time, scale="internal"),
    ]
    state, breaks = StructureDetector().detect(candles, swings, candles[-1].close_time)
    snapshot = {
        "structure_state": {
            "current_direction": state.current_direction,
            "last_confirmed_external_high": state.last_confirmed_external_high,
            "last_confirmed_external_low": state.last_confirmed_external_low,
            "last_external_break_id": state.last_external_break.object_id if state.last_external_break else None,
            "last_internal_break_id": state.last_internal_break.object_id if state.last_internal_break else None,
        },
        "structure_breaks": [b.model_dump(mode="json") for b in breaks],
        "swings": {
            "external": [s.model_dump(mode="json") for s in swings if s.evidence.is_external],
            "internal": [s.model_dump(mode="json") for s in swings if s.evidence.scale_name == "internal"],
        },
        "fvgs": [],
        "candle_count": len(candles),
    }

    hierarchy = build_structure_hierarchy(timeframe="15m", snapshot=snapshot, current_price="101").to_dict()

    assert hierarchy["external_bias"] == "bearish"
    assert hierarchy["internal_state"] == "bullish_retracement"
    assert hierarchy["latest_internal_break_id"] == state.last_internal_break.object_id


def test_equal_highs_and_sweep_reclaim_are_first_class_objects() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    swings = [
        _swing("h1", Direction.BEARISH, low="99", high="100.00", pivot=t0, confirmed=t0 + timedelta(minutes=15), scale="internal"),
        _swing("h2", Direction.BEARISH, low="99", high="100.05", pivot=t0 + timedelta(minutes=30), confirmed=t0 + timedelta(minutes=45), scale="internal"),
    ]
    liquidity = LiquidityLevelDetector(tolerance_bps=15.0, min_touches=2).detect(swings, t0 + timedelta(hours=2))
    equal_high = [level for level in liquidity if level.evidence.level_kind == "equal_highs"][0]
    sweep_candle = _candle(t0 + timedelta(hours=3), "99", "101", "98", "99.5")

    sweeps = SweepDetector(min_penetration_bps=1.0).detect([sweep_candle], [equal_high], sweep_candle.close_time)

    assert equal_high.evidence.touch_count == 2
    assert equal_high.evidence.side == "buy_side"
    assert len(sweeps) == 1
    assert sweeps[0].direction == Direction.BEARISH
    assert sweeps[0].evidence.reclaim_confirmed is True


def test_order_block_and_poi_grade_fvg_link_to_structure_break() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = _candle(t0, "100", "101", "95", "96")
    displacement = _candle(t0 + timedelta(minutes=15), "96", "111", "96", "110")
    brk = _break("bos_bull", Direction.BULLISH, candle=displacement, broken_price="105", confirmed_at=displacement.close_time)
    # WP-SMC-10/3: the causal OB-origin gate requires a displacement profile on
    # the break (populated by engine_v2._enrich_breaks_with_displacement on the
    # canonical path). These detector-unit tests bypass engine_v2, so we supply
    # the profile the engine would have produced for this fat-body, close-beyond
    # break (moderate quality: score >= 0.45, bps >= 4.0).
    brk.metadata["displacement"] = {
        "score": 0.85, "break_quality": "strong",
        "close_beyond_structure_bps": 47.6,
        "scored_by": "score_break_displacement",
        "scoring_version": "wp_smc10_canonical_v1",
    }
    fvg = _fvg("fvg_bull", Direction.BULLISH, "101", "104", displacement.open_time)

    marked = mark_poi_grade_fvgs([fvg], [brk])
    obs = OrderBlockDetector(lookback=3, min_body_ratio=0.2).detect([source, displacement], [brk], marked, displacement.close_time)

    assert marked[0].evidence.poi_grade is True
    assert marked[0].evidence.origin_break_id == "bos_bull"
    assert len(obs) == 1
    assert obs[0].evidence.structure_break_id == "bos_bull"
    assert obs[0].evidence.originating_fvg_id == "fvg_bull"
    assert obs[0].price_low == source.low
    assert obs[0].price_high == source.high


def test_order_block_lifecycle_remembers_a_partial_touch_after_price_leaves() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = _candle(t0, "100", "101", "95", "96")
    displacement = _candle(t0 + timedelta(minutes=15), "96", "111", "96", "110")
    partial_touch = _candle(t0 + timedelta(minutes=30), "110", "110", "99", "105")
    left_zone = _candle(t0 + timedelta(minutes=45), "105", "114", "104", "113")
    brk = _break(
        "bos_bull",
        Direction.BULLISH,
        candle=displacement,
        broken_price="105",
        confirmed_at=displacement.close_time,
    )
    brk.metadata["displacement"] = {
        "score": 0.85,
        "break_quality": "strong",
        "close_beyond_structure_bps": 47.6,
    }

    ob = OrderBlockDetector(lookback=3, min_body_ratio=0.2).detect(
        [source, displacement, partial_touch, left_zone],
        [brk],
        [],
        left_zone.close_time,
    )[0]

    assert getattr(ob.mitigation_status, "value", ob.mitigation_status) == "partial"
    assert getattr(ob.activity_status, "value", ob.activity_status) == "active"
    event_types = [getattr(event.event_type, "value", event.event_type) for event in ob.events]
    assert "OBJECT_FIRST_TOUCHED" in event_types
    assert "OBJECT_PARTIALLY_MITIGATED" in event_types
    assert ob.current_as_of == left_zone.close_time


def test_order_block_body_close_through_distal_boundary_is_invalidated() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = _candle(t0, "100", "101", "95", "96")
    displacement = _candle(t0 + timedelta(minutes=15), "96", "111", "96", "110")
    invalidating = _candle(t0 + timedelta(minutes=30), "100", "100", "93", "94")
    brk = _break(
        "bos_bull",
        Direction.BULLISH,
        candle=displacement,
        broken_price="105",
        confirmed_at=displacement.close_time,
    )
    brk.metadata["displacement"] = {
        "score": 0.85,
        "break_quality": "strong",
        "close_beyond_structure_bps": 47.6,
    }

    ob = OrderBlockDetector(lookback=3, min_body_ratio=0.2).detect(
        [source, displacement, invalidating],
        [brk],
        [],
        invalidating.close_time,
    )[0]

    assert getattr(ob.activity_status, "value", ob.activity_status) == "terminal"
    assert getattr(ob.terminal_reason, "value", ob.terminal_reason) == "invalidated"


def test_order_block_detector_keeps_older_bases_visible_but_non_causal() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older_base = _candle(t0, "102", "103", "98", "99")
    separator = _candle(t0 + timedelta(minutes=15), "99", "101", "98", "100")
    nearest_base = _candle(t0 + timedelta(minutes=30), "100", "101", "97", "98")
    displacement = _candle(t0 + timedelta(minutes=45), "98", "111", "98", "110")
    brk = _break(
        "bos_bull", Direction.BULLISH, candle=displacement,
        broken_price="105", confirmed_at=displacement.close_time,
    )
    brk.metadata["displacement"] = {
        "score": 0.85, "break_quality": "strong", "close_beyond_structure_bps": 47.6,
    }

    obs = OrderBlockDetector(lookback=5, min_body_ratio=0.2).detect(
        [older_base, separator, nearest_base, displacement],
        [brk], [], displacement.close_time,
    )

    assert len(obs) == 2
    by_pivot = {ob.pivot_time: ob for ob in obs}
    assert by_pivot[nearest_base.open_time].evidence.poi_grade is True
    assert by_pivot[nearest_base.open_time].evidence.caused_structure_break is True
    assert by_pivot[older_base.open_time].evidence.poi_grade is False
    assert by_pivot[older_base.open_time].evidence.caused_structure_break is False
    assert (
        by_pivot[older_base.open_time].metadata["causal_origin_admission"]["reason"]
        == "not_nearest_traced_departure_origin"
    )


def test_order_block_origin_uses_delayed_confirmation_candle_not_wick_probe() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old_base = _candle(t0, "102", "103", "98", "99")
    separator = _candle(t0 + timedelta(minutes=15), "99", "102", "99", "101")
    probe = _candle(t0 + timedelta(minutes=30), "101", "106", "99", "100")
    confirmation = _candle(t0 + timedelta(minutes=45), "100", "111", "100", "110")
    brk = _break(
        "delayed_bos", Direction.BULLISH, candle=probe,
        broken_price="105", confirmed_at=confirmation.close_time,
    )
    brk.evidence.body_close_candle_id = f"c_{confirmation.open_time.timestamp()}"
    brk.evidence.is_delayed_confirmation = True
    brk.metadata["displacement"] = {
        "score": 0.85, "break_quality": "strong", "close_beyond_structure_bps": 47.6,
    }

    obs = OrderBlockDetector(lookback=4, min_body_ratio=0.2).detect(
        [old_base, separator, probe, confirmation], [brk], [], confirmation.close_time,
    )

    primary = next(ob for ob in obs if ob.evidence.poi_grade)
    assert primary.pivot_time == probe.open_time
    assert primary.metadata["departure_candle_ids"] == [f"c_{confirmation.open_time.timestamp()}"]


def test_delayed_break_confirmation_records_every_level_closed_through() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    activation = _candle(t0, "101", "102", "100.5", "101")
    probe = _candle(t0 + timedelta(minutes=15), "101", "101.5", "99.5", "100.5")
    confirmation = _candle(t0 + timedelta(minutes=30), "100.5", "101", "98.5", "98.7")
    low_99 = _swing(
        "low_99",
        Direction.BULLISH,
        low="99",
        high="99.5",
        pivot=t0 - timedelta(hours=2),
        confirmed=activation.close_time,
        scale="external",
    )
    low_100 = _swing(
        "low_100",
        Direction.BULLISH,
        low="100",
        high="100.5",
        pivot=t0 - timedelta(hours=1),
        confirmed=activation.close_time,
        scale="external",
    )

    _, breaks = StructureDetector(structure_break_min_bps=1.0).detect(
        [activation, probe, confirmation],
        [low_99, low_100],
        confirmation.close_time,
    )
    delayed = next(brk for brk in breaks if brk.confirmed_at == confirmation.close_time)

    assert delayed.evidence.is_delayed_confirmation is True
    assert delayed.evidence.levels_broken_by_candle == 2


def test_inducement_marks_internal_liquidity_and_taken_sweep() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = _candle(t0, "100", "101", "95", "96")
    displacement = _candle(t0 + timedelta(minutes=15), "96", "111", "96", "110")
    brk = _break("bos_bull", Direction.BULLISH, candle=displacement, broken_price="105", confirmed_at=displacement.close_time)
    # WP-SMC-10/3: supply the displacement profile the canonical engine would
    # have enriched onto this break (see test_order_block_... above).
    brk.metadata["displacement"] = {
        "score": 0.85, "break_quality": "strong",
        "close_beyond_structure_bps": 47.6,
        "scored_by": "score_break_displacement",
        "scoring_version": "wp_smc10_canonical_v1",
    }
    ob = OrderBlockDetector(lookback=3, min_body_ratio=0.2).detect([source, displacement], [brk], [], displacement.close_time)[0]
    internal_low = _swing(
        "idm_low",
        Direction.BULLISH,
        low="95",
        high="97",
        pivot=source.open_time,
        confirmed=source.close_time,
        scale="internal",
    )
    sweep = SweepObject(
        object_id="sweep_sell_side",
        venue="BINANCE",
        instrument="BTCUSDT",
        timeframe="15m",
        pivot_time=source.open_time,
        candidate_at=source.open_time,
        confirmed_at=source.close_time,
        current_as_of=displacement.close_time,
        schema_version="1.0.0",
        detector_version="test",
        configuration_hash="test",
        source_candle_ids=[f"c_{source.open_time.timestamp()}"],
        last_updated_at=displacement.close_time,
        confidence=1.0,
        direction=Direction.BULLISH,
        price_low=source.low,
        price_high=source.high,
        confirmation_status=ConfirmationStatus.CONFIRMED,
        evidence=SweepEvidence(
            swept_level_id="liq_idm_low",
            sweep_candle_id=f"c_{source.open_time.timestamp()}",
            penetration_ticks=10,
            swept_price=Decimal("95"),
            reclaim_close=Decimal("96"),
            reclaim_confirmed=True,
        ),
    )

    inducements = InducementDetector().detect([internal_low], [ob], [brk], [sweep], displacement.close_time)

    assert len(inducements) == 1
    assert inducements[0].evidence.source_swing_id == "idm_low"
    assert inducements[0].evidence.liquidity_side == "sell_side"
    assert inducements[0].evidence.inducement_taken is True
    assert inducements[0].evidence.sweep_id == "sweep_sell_side"
