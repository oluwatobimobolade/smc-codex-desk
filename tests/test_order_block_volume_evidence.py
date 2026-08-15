from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smc_desk.data.schemas import Candle
from smc_desk.perception.order_blocks import _relative_volume_evidence


def _candles(volumes: list[int]) -> list[Candle]:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return [
        Candle(
            venue="test", instrument="ETHUSDT", timeframe="15m",
            open_time=start + timedelta(minutes=15 * index),
            close_time=start + timedelta(minutes=15 * (index + 1)),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
            volume=Decimal(volume), trade_count=10, is_closed=True, is_complete=True, contains_gap=False,
        )
        for index, volume in enumerate(volumes)
    ]


def test_relative_volume_uses_pre_origin_median_baseline():
    values = [100] * 20 + [150, 200, 200, 200]
    evidence = _relative_volume_evidence(
        _candles(values), cluster_start=20, cluster_end=20, break_index=23
    )
    assert evidence["volume_evidence_status"] == "AVAILABLE"
    assert evidence["baseline_volume"] == 100.0
    assert evidence["origin_volume_ratio"] == 1.5
    assert evidence["departure_volume_ratio"] == 2.0
    assert evidence["volume_ratio"] == 2.0


def test_zero_filled_volume_is_unknown_not_neutral():
    evidence = _relative_volume_evidence(
        _candles([0] * 24), cluster_start=20, cluster_end=20, break_index=23
    )
    assert evidence["volume_evidence_status"] == "UNAVAILABLE"
    assert evidence["volume_ratio"] is None
    assert evidence["origin_volume_ratio"] is None
    assert evidence["departure_volume_ratio"] is None


def test_short_history_is_explicitly_insufficient():
    evidence = _relative_volume_evidence(
        _candles([100, 100, 100, 150, 200]), cluster_start=3, cluster_end=3, break_index=4
    )
    assert evidence["volume_evidence_status"] == "INSUFFICIENT_BASELINE"
    assert evidence["volume_ratio"] is None
    assert evidence["origin_volume"] == 150.0
    assert evidence["departure_volume"] == 200.0
