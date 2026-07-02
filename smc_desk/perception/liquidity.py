"""Liquidity pools and sweep/reclaim events for PerceptionEngineV2."""
from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List

from smc_desk.data.schemas import Candle
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    LiquidityLevelEvidence,
    LiquidityLevelObject,
    SweepEvidence,
    SweepObject,
    SwingObject,
)


class LiquidityLevelDetector:
    def __init__(
        self,
        detector_version: str = "2.0",
        tolerance_bps: float = 15.0,
        min_touches: int = 2,
        max_recent_swings: int = 120,
    ):
        self.detector_version = detector_version
        self.tolerance_bps = tolerance_bps
        self.min_touches = min_touches
        self.max_recent_swings = max_recent_swings
        self.configuration_hash = hashlib.sha256(b"liquidity_v2_wp0022").hexdigest()[:8]

    def detect(self, swings: Iterable[SwingObject], current_time: datetime) -> list[LiquidityLevelObject]:
        known = sorted(
            [s for s in swings if s.confirmed_at and s.confirmed_at <= current_time],
            key=lambda swing: swing.confirmed_at or swing.candidate_at,
        )
        if self.max_recent_swings > 0:
            known = known[-self.max_recent_swings :]
        levels: list[LiquidityLevelObject] = []
        for swing in known:
            levels.append(self._single_swing_level(swing, current_time))
        levels.extend(self._equal_level_clusters(known, current_time, high_side=True))
        levels.extend(self._equal_level_clusters(known, current_time, high_side=False))
        return levels

    def _single_swing_level(self, swing: SwingObject, current_time: datetime) -> LiquidityLevelObject:
        is_high = _direction(swing.direction) == "bearish"
        price = swing.price_high if is_high else swing.price_low
        kind = "swing_high" if is_high else "swing_low"
        side = "buy_side" if is_high else "sell_side"
        evidence = LiquidityLevelEvidence(
            constituent_swing_ids=[swing.object_id],
            max_deviation_ticks=0,
            level_kind=kind,  # type: ignore[arg-type]
            side=side,  # type: ignore[arg-type]
            touch_count=1,
            tolerance_bps=self.tolerance_bps,
        )
        return LiquidityLevelObject(
            object_id=f"liq_{kind}_{swing.object_id}",
            venue=swing.venue,
            instrument=swing.instrument,
            timeframe=swing.timeframe,
            pivot_time=swing.pivot_time,
            candidate_at=swing.confirmed_at or swing.candidate_at,
            confirmed_at=swing.confirmed_at,
            current_as_of=current_time,
            schema_version="1.0.0",
            detector_version=self.detector_version,
            configuration_hash=self.configuration_hash,
            source_candle_ids=list(swing.source_candle_ids),
            last_updated_at=current_time,
            confidence=0.55,
            direction=Direction.BEARISH if is_high else Direction.BULLISH,
            price_low=price,
            price_high=price,
            evidence=evidence,
            confirmation_status=ConfirmationStatus.CONFIRMED,
        )

    def _equal_level_clusters(
        self,
        swings: list[SwingObject],
        current_time: datetime,
        *,
        high_side: bool,
    ) -> list[LiquidityLevelObject]:
        selected = [s for s in swings if (_direction(s.direction) == "bearish") == high_side]
        selected.sort(key=lambda s: s.price_high if high_side else s.price_low)
        clusters: list[list[SwingObject]] = []
        for swing in selected:
            price = swing.price_high if high_side else swing.price_low
            placed = False
            for cluster in clusters:
                anchor = _cluster_price(cluster, high_side)
                tolerance = max(anchor, Decimal("1")) * Decimal(str(self.tolerance_bps / 10000.0))
                if abs(price - anchor) <= tolerance:
                    cluster.append(swing)
                    placed = True
                    break
            if not placed:
                clusters.append([swing])

        levels: list[LiquidityLevelObject] = []
        for cluster in clusters:
            if len(cluster) < self.min_touches:
                continue
            prices = [s.price_high if high_side else s.price_low for s in cluster]
            level = sum(prices, Decimal("0")) / Decimal(len(prices))
            max_dev = max(abs(p - level) for p in prices)
            tick_dev = int(max_dev / Decimal("0.01")) if max_dev > 0 else 0
            first = cluster[0]
            kind = "equal_highs" if high_side else "equal_lows"
            side = "buy_side" if high_side else "sell_side"
            evidence = LiquidityLevelEvidence(
                constituent_swing_ids=[s.object_id for s in cluster],
                max_deviation_ticks=tick_dev,
                level_kind=kind,  # type: ignore[arg-type]
                side=side,  # type: ignore[arg-type]
                touch_count=len(cluster),
                tolerance_bps=self.tolerance_bps,
            )
            obj = LiquidityLevelObject(
                object_id=f"liq_{kind}_{first.pivot_time.timestamp()}_{len(cluster)}",
                venue=first.venue,
                instrument=first.instrument,
                timeframe=first.timeframe,
                pivot_time=first.pivot_time,
                candidate_at=max(s.confirmed_at or s.candidate_at for s in cluster),
                confirmed_at=max(s.confirmed_at or s.candidate_at for s in cluster),
                current_as_of=current_time,
                schema_version="1.0.0",
                detector_version=self.detector_version,
                configuration_hash=self.configuration_hash,
                source_candle_ids=[cid for s in cluster for cid in s.source_candle_ids],
                last_updated_at=current_time,
                confidence=min(0.95, 0.60 + 0.08 * len(cluster)),
                direction=Direction.BEARISH if high_side else Direction.BULLISH,
                price_low=min(prices),
                price_high=max(prices),
                evidence=evidence,
                confirmation_status=ConfirmationStatus.CONFIRMED,
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CREATED,
                    timestamp=first.pivot_time,
                    trigger_candle_id=obj.source_candle_ids[0] if obj.source_candle_ids else "",
                    details=f"{kind} liquidity pool candidate created",
                ),
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CONFIRMED,
                    timestamp=obj.confirmed_at,
                    trigger_candle_id=obj.source_candle_ids[-1] if obj.source_candle_ids else "",
                    details=f"{kind} liquidity pool confirmed from {len(cluster)} swings",
                ),
            )
            levels.append(obj)
        return levels


class SweepDetector:
    def __init__(self, detector_version: str = "2.0", min_penetration_bps: float = 2.0):
        self.detector_version = detector_version
        self.min_penetration_bps = min_penetration_bps
        self.configuration_hash = hashlib.sha256(b"sweep_v2_wp0022").hexdigest()[:8]

    def detect(
        self,
        candles: List[Candle],
        liquidity_levels: List[LiquidityLevelObject],
        current_time: datetime,
    ) -> list[SweepObject]:
        sweeps: list[SweepObject] = []
        seen: set[tuple[str, datetime]] = set()
        for candle in candles:
            if candle.close_time > current_time:
                break
            for level in liquidity_levels:
                if level.confirmed_at and level.confirmed_at >= candle.close_time:
                    continue
                side = level.evidence.side
                reference = level.price_high if side == "buy_side" else level.price_low
                min_pen = reference * Decimal(str(self.min_penetration_bps / 10000.0))
                if side == "buy_side":
                    penetrated = candle.high - reference
                    reclaimed = candle.high > reference and candle.close < reference
                    direction = Direction.BEARISH
                else:
                    penetrated = reference - candle.low
                    reclaimed = candle.low < reference and candle.close > reference
                    direction = Direction.BULLISH
                if not reclaimed or penetrated < min_pen:
                    continue
                key = (level.object_id, candle.open_time)
                if key in seen:
                    continue
                seen.add(key)
                sweeps.append(self._make_sweep(candle, level, direction, reference, penetrated, current_time))
        return sweeps

    def _make_sweep(
        self,
        candle: Candle,
        level: LiquidityLevelObject,
        direction: Direction,
        reference: Decimal,
        penetration: Decimal,
        current_time: datetime,
    ) -> SweepObject:
        evidence = SweepEvidence(
            swept_level_id=level.object_id,
            sweep_candle_id=f"c_{candle.open_time.timestamp()}",
            penetration_ticks=int(penetration / Decimal("0.01")) if penetration > 0 else 0,
            swept_price=reference,
            reclaim_close=candle.close,
            reclaim_confirmed=True,
        )
        obj = SweepObject(
            object_id=f"sweep_{direction.value}_{level.object_id}_{candle.open_time.timestamp()}",
            venue=candle.venue,
            instrument=candle.instrument,
            timeframe=candle.timeframe,
            pivot_time=candle.open_time,
            candidate_at=candle.open_time,
            confirmed_at=candle.close_time,
            current_as_of=current_time,
            schema_version="1.0.0",
            detector_version=self.detector_version,
            configuration_hash=self.configuration_hash,
            source_candle_ids=[f"c_{candle.open_time.timestamp()}"],
            last_updated_at=current_time,
            confidence=0.75,
            direction=direction,
            price_low=candle.low,
            price_high=candle.high,
            evidence=evidence,
            confirmation_status=ConfirmationStatus.CONFIRMED,
        )
        apply_event(
            obj,
            SMCEvent(
                event_type=EventType.OBJECT_CREATED,
                timestamp=candle.open_time,
                trigger_candle_id=f"c_{candle.open_time.timestamp()}",
                details="Sweep/reclaim candidate created",
            ),
        )
        apply_event(
            obj,
            SMCEvent(
                event_type=EventType.OBJECT_CONFIRMED,
                timestamp=candle.close_time,
                trigger_candle_id=f"c_{candle.open_time.timestamp()}",
                details=f"Wick swept {level.evidence.side} liquidity and reclaimed the level",
            ),
        )
        return obj


def _cluster_price(cluster: list[SwingObject], high_side: bool) -> Decimal:
    prices = [s.price_high if high_side else s.price_low for s in cluster]
    return sum(prices, Decimal("0")) / Decimal(len(prices))


def _direction(value: object) -> str:
    return getattr(value, "value", value)
