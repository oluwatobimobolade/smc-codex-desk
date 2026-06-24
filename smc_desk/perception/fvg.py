import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from smc_desk.data.schemas import Candle
from smc_desk.perception.ontology import Direction, SMCObjectBase, FairValueGapEvidence, ConfirmationStatus
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event

class FairValueGapObject(SMCObjectBase):
    evidence: FairValueGapEvidence


class FVGDetector:
    def __init__(self, detector_version: str = "2.0"):
        self.detector_version = detector_version
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
                
                evidence = FairValueGapEvidence(
                    gap_size_ticks=0, # To compute later with tick_size
                    gap_size_bps=float(gap_size / c2.close * 10000),
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
                    last_updated_at=datetime.utcnow().replace(tzinfo=timezone.utc),
                    confidence=1.0,
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
                
                fvgs.append(fvg)
                
        # Process mitigation lifecycle
        from smc_desk.perception.ontology import MitigationStatus
        for fvg in fvgs:
            for c in candles:
                if c.close_time <= fvg.confirmed_at:
                    continue
                if c.close_time > current_time:
                    break
                
                if fvg.mitigation_status == MitigationStatus.FULL:
                    continue
                    
                if fvg.direction == Direction.BULLISH:
                    if c.low <= fvg.price_high: # Touched the FVG top
                        if c.low <= fvg.price_low:
                            fvg.mitigation_status = MitigationStatus.FULL
                        else:
                            fvg.mitigation_status = MitigationStatus.PARTIAL
                elif fvg.direction == Direction.BEARISH:
                    if c.high >= fvg.price_low: # Touched the FVG bottom
                        if c.high >= fvg.price_high:
                            fvg.mitigation_status = MitigationStatus.FULL
                        else:
                            fvg.mitigation_status = MitigationStatus.PARTIAL
                            
        return fvgs
