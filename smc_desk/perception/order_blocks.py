"""Order-block and POI-grade FVG detection for PerceptionEngineV2."""
from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional

from smc_desk.data.schemas import Candle
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    FairValueGapObject,
    OrderBlockEvidence,
    OrderBlockObject,
    StructureBreakObject,
)


class OrderBlockDetector:
    def __init__(self, detector_version: str = "2.0", lookback: int = 8, min_body_ratio: float = 0.25):
        self.detector_version = detector_version
        self.lookback = lookback
        self.min_body_ratio = min_body_ratio
        self.configuration_hash = hashlib.sha256(b"order_block_v2_wp0022").hexdigest()[:8]

    def detect(
        self,
        candles: List[Candle],
        structure_breaks: Iterable[StructureBreakObject],
        fvgs: Iterable[FairValueGapObject],
        current_time: datetime,
    ) -> list[OrderBlockObject]:
        by_open = {c.open_time: idx for idx, c in enumerate(candles)}
        fvg_list = list(fvgs)
        order_blocks: list[OrderBlockObject] = []
        for brk in structure_breaks:
            if not brk.confirmed_at or brk.confirmed_at > current_time:
                continue
            if brk.confirmation_status != ConfirmationStatus.CONFIRMED:
                continue
            break_index = by_open.get(brk.candidate_at)
            if break_index is None:
                break_index = _first_candle_at_or_after(candles, brk.candidate_at)
            if break_index is None:
                continue
            source_index = self._find_source_candle(candles, break_index, brk.direction)
            if source_index is None:
                continue
            source = candles[source_index]
            body_ratio = _body_ratio(source)
            if body_ratio < self.min_body_ratio:
                continue
            origin_fvg = _nearby_origin_fvg(brk, fvg_list)
            evidence = OrderBlockEvidence(
                originating_fvg_id=None if origin_fvg is None else origin_fvg.object_id,
                volume_ratio=1.0,
                structure_break_id=brk.object_id,
                source_candle_id=f"c_{source.open_time.timestamp()}",
                body_ratio=body_ratio,
                poi_grade=True,
            )
            obj = OrderBlockObject(
                object_id=f"ob_{brk.direction.value if hasattr(brk.direction, 'value') else brk.direction}_{source.open_time.timestamp()}",
                venue=source.venue,
                instrument=source.instrument,
                timeframe=source.timeframe,
                pivot_time=source.open_time,
                candidate_at=brk.candidate_at,
                confirmed_at=brk.confirmed_at,
                current_as_of=current_time,
                schema_version="1.0.0",
                detector_version=self.detector_version,
                configuration_hash=self.configuration_hash,
                source_candle_ids=[f"c_{source.open_time.timestamp()}", *brk.source_candle_ids],
                last_updated_at=current_time,
                confidence=min(0.92, 0.58 + body_ratio * 0.34 + (0.08 if origin_fvg else 0.0)),
                direction=brk.direction,
                price_low=min(source.low, source.high),
                price_high=max(source.low, source.high),
                evidence=evidence,
                confirmation_status=ConfirmationStatus.CONFIRMED,
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CREATED,
                    timestamp=source.open_time,
                    trigger_candle_id=f"c_{source.open_time.timestamp()}",
                    details="Order-block source candle candidate created",
                ),
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CONFIRMED,
                    timestamp=brk.confirmed_at,
                    trigger_candle_id=f"c_{source.open_time.timestamp()}",
                    details="Last opposing candle before structure-breaking displacement",
                ),
            )
            order_blocks.append(obj)
        return order_blocks

    def _find_source_candle(self, candles: List[Candle], break_index: int, direction: Direction) -> Optional[int]:
        direction_value = getattr(direction, "value", direction)
        start = max(0, break_index - self.lookback)
        for idx in range(break_index - 1, start - 1, -1):
            candle = candles[idx]
            if direction_value == "bullish" and candle.close < candle.open:
                return idx
            if direction_value == "bearish" and candle.close > candle.open:
                return idx
        return None


def mark_poi_grade_fvgs(
    fvgs: Iterable[FairValueGapObject],
    structure_breaks: Iterable[StructureBreakObject],
    *,
    max_seconds: int = 8 * 60 * 60,
) -> list[FairValueGapObject]:
    """Mark the subset of raw FVGs that are close enough to a structure break origin."""
    fvg_list = list(fvgs)
    confirmed_breaks = [b for b in structure_breaks if b.confirmed_at and b.confirmation_status == ConfirmationStatus.CONFIRMED]
    for fvg in fvg_list:
        fvg.evidence.poi_grade = False
        fvg.evidence.origin_break_id = None
        fvg.evidence.location_context = None
        for brk in confirmed_breaks:
            if _direction(brk.direction) != _direction(fvg.direction):
                continue
            if fvg.confirmed_at is None or brk.confirmed_at is None:
                continue
            if abs((fvg.confirmed_at - brk.confirmed_at).total_seconds()) > max_seconds:
                continue
            fvg.evidence.poi_grade = True
            fvg.evidence.origin_break_id = brk.object_id
            fvg.evidence.location_context = "structure_break_displacement_origin"
            break
    return fvg_list


def _nearby_origin_fvg(brk: StructureBreakObject, fvgs: list[FairValueGapObject]) -> FairValueGapObject | None:
    candidates = []
    for fvg in fvgs:
        if not fvg.confirmed_at or not brk.confirmed_at:
            continue
        if _direction(fvg.direction) != _direction(brk.direction):
            continue
        delta = abs((fvg.confirmed_at - brk.confirmed_at).total_seconds())
        if delta <= 8 * 60 * 60:
            candidates.append((delta, fvg))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _first_candle_at_or_after(candles: list[Candle], when: datetime) -> int | None:
    for idx, candle in enumerate(candles):
        if candle.open_time >= when:
            return idx
    return None


def _body_ratio(candle: Candle) -> float:
    rng = candle.high - candle.low
    if rng <= 0:
        return 0.0
    return float(abs(candle.close - candle.open) / rng)


def _direction(value: object) -> str:
    return str(getattr(value, "value", value)).lower()
