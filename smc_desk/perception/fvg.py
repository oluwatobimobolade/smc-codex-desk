import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from smc_desk.data.schemas import Candle
from smc_desk.perception.ontology import Direction, SMCObjectBase, FairValueGapEvidence, MitigationStatus
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event


class FairValueGapObject(SMCObjectBase):
    evidence: FairValueGapEvidence


class FVGDetector:
    def __init__(self, detector_version: str = "2.0", minimum_gap_bps: float = 5.0):
        self.detector_version = detector_version
        self.minimum_gap_bps = minimum_gap_bps
        self.configuration_hash = hashlib.sha256(b"fvg_v2").hexdigest()[:8]
        
    def detect(self, candles: List[Candle], current_time: datetime) -> List[FairValueGapObject]:
        fvgs = []
        n = len(candles)
        
        for i in range(1, n - 1):
            c1 = candles[i - 1]
            c2 = candles[i]
            c3 = candles[i + 1]
            
            # The FVG is confirmed at the close of c3
            if c3.close_time > current_time:
                continue
                
            is_bullish = c1.high < c3.low
            is_bearish = c1.low > c3.high
            
            if is_bullish or is_bearish:
                direction = Direction.BULLISH if is_bullish else Direction.BEARISH
                
                lower_bound = c1.high if is_bullish else c3.high
                upper_bound = c3.low if is_bullish else c1.low
                
                gap_size = upper_bound - lower_bound
                gap_bps = float(gap_size / c2.close * 10000)

                # Enforce minimum gap threshold from ontology.
                if gap_bps < self.minimum_gap_bps:
                    continue
                
                evidence = FairValueGapEvidence(
                    gap_size_ticks=int(gap_size / Decimal("0.01")) if gap_size > 0 else 0,
                    gap_size_bps=round(gap_bps, 2),
                    atr_ratio=0.0,
                    is_mitigated_on_creation=False
                )
                
                obj_id = f"fvg_{direction.value}_{c2.open_time.timestamp()}"
                
                fvg = FairValueGapObject(
                    object_id=obj_id,
                    venue=c2.venue,
                    instrument=c2.instrument,
                    timeframe=c2.timeframe,
                    pivot_time=c2.open_time,
                    candidate_at=c3.open_time,
                    confirmed_at=c3.close_time,
                    current_as_of=current_time,
                    schema_version="1.0.0",
                    detector_version=self.detector_version,
                    configuration_hash=self.configuration_hash,
                    source_candle_ids=[f"c_{c.open_time.timestamp()}" for c in (c1, c2, c3)],
                    last_updated_at=current_time,
                    confidence=0.0,  # not calibrated; use evidence quality metrics instead
                    direction=direction,
                    price_low=lower_bound,
                    price_high=upper_bound,
                    evidence=evidence
                )
                
                creation_event = SMCEvent(
                    event_type=EventType.OBJECT_CREATED,
                    timestamp=c3.open_time,
                    trigger_candle_id=f"c_{c3.open_time.timestamp()}",
                    details="Gap formed"
                )
                apply_event(fvg, creation_event)
                
                confirmation_event = SMCEvent(
                    event_type=EventType.OBJECT_CONFIRMED,
                    timestamp=c3.close_time,
                    trigger_candle_id=f"c_{c3.open_time.timestamp()}",
                    details="Gap confirmed on candle close"
                )
                apply_event(fvg, confirmation_event)

                activation_event = SMCEvent(
                    event_type=EventType.OBJECT_ACTIVATED,
                    timestamp=c3.close_time,
                    trigger_candle_id=f"c_{c3.open_time.timestamp()}",
                    details="Gap became active after confirmation"
                )
                apply_event(fvg, activation_event)
                
                fvgs.append(fvg)
                
        # Process mitigation lifecycle + first-touch detection
        for fvg in fvgs:
            first_touch_recorded = False
            for c in candles:
                if c.close_time <= fvg.confirmed_at:
                    continue
                if c.close_time > current_time:
                    break
                
                if fvg.mitigation_status == MitigationStatus.FULL:
                    continue

                if fvg.direction == Direction.BULLISH:
                    touched = c.low <= fvg.price_high
                    if touched:
                        # First-touch event (recorded once, before any mitigation)
                        if not first_touch_recorded:
                            first_touch_recorded = True
                            apply_event(
                                fvg,
                                SMCEvent(
                                    event_type=EventType.OBJECT_FIRST_TOUCHED,
                                    timestamp=c.close_time,
                                    trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                    details=f"Bullish FVG first touched by low {c.low} at {c.close_time}",
                                ),
                            )
                            # Compute mitigation percentage
                            gap_size = float(fvg.price_high - fvg.price_low)
                            penetration = float(fvg.price_high - c.low)
                            fvg.mitigation_percent = min(100.0, max(0.0, (penetration / gap_size * 100) if gap_size > 0 else 100.0))
                            fvg.mitigated_price = c.low

                    if touched and c.low <= fvg.price_low:
                        apply_event(
                            fvg,
                            SMCEvent(
                                event_type=EventType.OBJECT_FULLY_MITIGATED,
                                timestamp=c.close_time,
                                trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                details="Bullish FVG fully mitigated",
                            ),
                        )
                        fvg.mitigation_percent = 100.0
                    elif touched:
                        apply_event(
                            fvg,
                            SMCEvent(
                                event_type=EventType.OBJECT_PARTIALLY_MITIGATED,
                                timestamp=c.close_time,
                                trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                details=f"Bullish FVG partially mitigated ({fvg.mitigation_percent:.1f}%)",
                            ),
                        )

                    # Invalidation: body closes below the entire FVG
                    if c.close < fvg.price_low:
                        apply_event(
                            fvg,
                            SMCEvent(
                                event_type=EventType.OBJECT_INVALIDATED,
                                timestamp=c.close_time,
                                trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                details=f"Bullish FVG invalidated by body close {c.close} below {fvg.price_low}",
                            ),
                        )
                        fvg.mitigation_percent = 100.0

                elif fvg.direction == Direction.BEARISH:
                    touched = c.high >= fvg.price_low
                    if touched:
                        if not first_touch_recorded:
                            first_touch_recorded = True
                            apply_event(
                                fvg,
                                SMCEvent(
                                    event_type=EventType.OBJECT_FIRST_TOUCHED,
                                    timestamp=c.close_time,
                                    trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                    details=f"Bearish FVG first touched by high {c.high} at {c.close_time}",
                                ),
                            )
                            gap_size = float(fvg.price_low - fvg.price_high)
                            penetration = float(c.high - fvg.price_low)
                            fvg.mitigation_percent = min(100.0, max(0.0, (penetration / gap_size * 100) if gap_size > 0 else 100.0))
                            fvg.mitigated_price = c.high

                    if touched and c.high >= fvg.price_high:
                        apply_event(
                            fvg,
                            SMCEvent(
                                event_type=EventType.OBJECT_FULLY_MITIGATED,
                                timestamp=c.close_time,
                                trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                details="Bearish FVG fully mitigated",
                            ),
                        )
                        fvg.mitigation_percent = 100.0
                    elif touched:
                        apply_event(
                            fvg,
                            SMCEvent(
                                event_type=EventType.OBJECT_PARTIALLY_MITIGATED,
                                timestamp=c.close_time,
                                trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                details=f"Bearish FVG partially mitigated ({fvg.mitigation_percent:.1f}%)",
                            ),
                        )

                    # Invalidation: body closes above the entire FVG
                    if c.close > fvg.price_high:
                        apply_event(
                            fvg,
                            SMCEvent(
                                event_type=EventType.OBJECT_INVALIDATED,
                                timestamp=c.close_time,
                                trigger_candle_id=f"c_{c.open_time.timestamp()}",
                                details=f"Bearish FVG invalidated by body close {c.close} above {fvg.price_high}",
                            ),
                        )
                        fvg.mitigation_percent = 100.0
                            )
                            
        return fvgs
