import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple, Dict

from smc_desk.data.schemas import Candle
from smc_desk.perception.ontology import Direction, SwingObject, SwingEvidence, ConfirmationStatus, ActivityStatus, TerminalReason, MitigationStatus
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event

class SwingDetector:
    def __init__(self, bars_left: int, bars_right: int, scale_name: str, detector_version: str = "2.0"):
        self.bars_left = bars_left
        self.bars_right = bars_right
        self.scale_name = scale_name
        self.detector_version = detector_version
        
        # Determine config hash for provenance
        config_str = f"swings_{scale_name}_{bars_left}_{bars_right}_{detector_version}"
        self.configuration_hash = hashlib.sha256(config_str.encode()).hexdigest()[:8]
        
    def detect(self, candles: List[Candle], current_time: datetime) -> List[SwingObject]:
        """Detects swings strictly up to current_time (as-of causality)."""
        swings = []
        n = len(candles)
        
        for i in range(self.bars_left, n - self.bars_right):
            pivot = candles[i]
            
            # Check if pivot confirmation window has closed by current_time
            confirmation_candle = candles[i + self.bars_right]
            
            # If the confirmation candle hasn't closed by the decision time, we cannot know about this swing!
            if confirmation_candle.close_time > current_time:
                continue
                
            left_window = candles[i - self.bars_left : i]
            right_window = candles[i + 1 : i + self.bars_right + 1]
            
            is_high = all(pivot.high > c.high for c in left_window) and all(pivot.high > c.high for c in right_window)
            is_low = all(pivot.low < c.low for c in left_window) and all(pivot.low < c.low for c in right_window)
            
            if is_high or is_low:
                direction = Direction.BULLISH if is_low else Direction.BEARISH
                
                # To calculate prominence_atr_pct we would need ATR.
                # For now, we will pass a placeholder of 0.0, we can inject an ATR array later if needed.
                evidence = SwingEvidence(
                    bars_left=self.bars_left,
                    bars_right=self.bars_right,
                    prominence_atr_pct=0.0,
                    is_external=(self.scale_name == "external")
                )
                
                # We record the candidate time as the close of the pivot candle.
                # The confirmed time is the close of the confirmation candle.
                # Wait, "candidate time" is when it could first be observed as a peak.
                # Let's say candidate_at is the close of pivot.
                
                obj_id = f"swing_{self.scale_name}_{pivot.open_time.timestamp()}"
                
                swing = SwingObject(
                    object_id=obj_id,
                    venue=pivot.venue,
                    instrument=pivot.instrument,
                    timeframe=pivot.timeframe,
                    pivot_time=pivot.open_time,
                    candidate_at=pivot.close_time,
                    confirmed_at=confirmation_candle.close_time,
                    current_as_of=current_time,
                    schema_version="1.0.0",
                    detector_version=self.detector_version,
                    configuration_hash=self.configuration_hash,
                    source_candle_ids=[f"c_{c.open_time.timestamp()}" for c in candles[i - self.bars_left : i + self.bars_right + 1]],
                    last_updated_at=current_time,
                    confidence=1.0,
                    direction=direction,
                    price_low=pivot.low,
                    price_high=pivot.high,
                    evidence=evidence
                )
                
                # Event Ledger
                creation_event = SMCEvent(
                    event_type=EventType.OBJECT_CREATED,
                    timestamp=pivot.close_time,
                    trigger_candle_id=f"c_{pivot.open_time.timestamp()}",
                    details="Pivot candidate created"
                )
                apply_event(swing, creation_event)
                
                confirmation_event = SMCEvent(
                    event_type=EventType.OBJECT_CONFIRMED,
                    timestamp=confirmation_candle.close_time,
                    trigger_candle_id=f"c_{confirmation_candle.open_time.timestamp()}",
                    details="Pivot window closed"
                )
                apply_event(swing, confirmation_event)
                
                swings.append(swing)
                
        return swings

class MultiScaleSwingDetector:
    def __init__(self):
        self.detectors = [
            SwingDetector(bars_left=1, bars_right=1, scale_name="local"),
            SwingDetector(bars_left=3, bars_right=3, scale_name="internal"),
            SwingDetector(bars_left=5, bars_right=5, scale_name="external")
        ]
        
    def detect(self, candles: List[Candle], current_time: datetime) -> Dict[str, List[SwingObject]]:
        return {d.scale_name: d.detect(candles, current_time) for d in self.detectors}
