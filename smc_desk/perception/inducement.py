"""Inducement detection for SMC POI validation."""
from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    InducementEvidence,
    InducementObject,
    OrderBlockObject,
    StructureBreakObject,
    SweepObject,
    SwingObject,
)


class InducementDetector:
    def __init__(self, detector_version: str = "2.0"):
        self.detector_version = detector_version
        self.configuration_hash = hashlib.sha256(b"inducement_v2_wp0022").hexdigest()[:8]

    def detect(
        self,
        swings: Iterable[SwingObject],
        order_blocks: Iterable[OrderBlockObject],
        structure_breaks: Iterable[StructureBreakObject],
        sweeps: Iterable[SweepObject],
        current_time: datetime,
    ) -> list[InducementObject]:
        swing_list = [
            s for s in swings
            if s.confirmed_at
            and s.confirmed_at <= current_time
            and _scope(s) == "internal"
        ]
        break_by_id = {b.object_id: b for b in structure_breaks}
        sweeps_list = list(sweeps)
        inducements: list[InducementObject] = []
        for ob in order_blocks:
            brk = break_by_id.get(ob.evidence.structure_break_id or "")
            if brk is None or brk.confirmed_at is None:
                continue
            candidate = self._select_candidate(swing_list, ob, brk)
            if candidate is None:
                continue
            liquidity_side = "buy_side" if _direction(candidate.direction) == "bearish" else "sell_side"
            taken_sweep = _matching_sweep(candidate, sweeps_list)
            evidence = InducementEvidence(
                source_swing_id=candidate.object_id,
                related_order_block_id=ob.object_id,
                related_break_id=brk.object_id,
                liquidity_side=liquidity_side,  # type: ignore[arg-type]
                inducement_taken=taken_sweep is not None,
                sweep_id=None if taken_sweep is None else taken_sweep.object_id,
            )
            price = candidate.price_high if _direction(candidate.direction) == "bearish" else candidate.price_low
            obj = InducementObject(
                object_id=f"idm_{ob.object_id}_{candidate.object_id}",
                venue=ob.venue,
                instrument=ob.instrument,
                timeframe=ob.timeframe,
                pivot_time=candidate.pivot_time,
                candidate_at=candidate.confirmed_at or candidate.candidate_at,
                confirmed_at=brk.confirmed_at,
                current_as_of=current_time,
                schema_version="1.0.0",
                detector_version=self.detector_version,
                configuration_hash=self.configuration_hash,
                source_candle_ids=list(candidate.source_candle_ids),
                last_updated_at=current_time,
                confidence=0.78 if taken_sweep else 0.58,
                direction=ob.direction,
                price_low=price,
                price_high=price,
                evidence=evidence,
                confirmation_status=ConfirmationStatus.CONFIRMED,
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CREATED,
                    timestamp=candidate.pivot_time,
                    trigger_candle_id=obj.source_candle_ids[0] if obj.source_candle_ids else "",
                    details="Inducement candidate created from internal liquidity",
                ),
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CONFIRMED,
                    timestamp=brk.confirmed_at,
                    trigger_candle_id=brk.source_candle_ids[-1] if brk.source_candle_ids else "",
                    details="Internal liquidity before POI/break identified as inducement",
                ),
            )
            inducements.append(obj)
        return inducements

    def _select_candidate(
        self,
        swings: list[SwingObject],
        ob: OrderBlockObject,
        brk: StructureBreakObject,
    ) -> SwingObject | None:
        direction = _direction(brk.direction)
        desired_swing_direction = "bearish" if direction == "bearish" else "bullish"
        start = ob.pivot_time
        end = brk.confirmed_at or brk.candidate_at
        candidates = [
            s for s in swings
            if _direction(s.direction) == desired_swing_direction
            and s.pivot_time >= start
            and s.pivot_time <= end
        ]
        if not candidates:
            # Fallback: the last internal opposing liquidity before the break.
            candidates = [
                s for s in swings
                if _direction(s.direction) == desired_swing_direction
                and s.pivot_time <= end
            ][-6:]
        if not candidates:
            return None
        if direction == "bearish":
            return max(candidates, key=lambda s: s.price_high)
        return min(candidates, key=lambda s: s.price_low)


def _matching_sweep(swing: SwingObject, sweeps: list[SweepObject]) -> SweepObject | None:
    price = swing.price_high if _direction(swing.direction) == "bearish" else swing.price_low
    for sweep in sweeps:
        swept = sweep.evidence.swept_price
        if swept is None:
            continue
        if abs(Decimal(str(swept)) - price) <= max(price * Decimal("0.0015"), Decimal("0.01")):
            return sweep
    return None


def _scope(swing: SwingObject) -> str:
    scale = getattr(swing.evidence, "scale_name", None)
    if scale in {"external", "internal", "local"}:
        return str(scale)
    return "external" if swing.evidence.is_external else "internal"


def _direction(value: object) -> str:
    return str(getattr(value, "value", value)).lower()
