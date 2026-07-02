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
                
                prominence_price, prominence_atr_pct = _swing_prominence(
                    pivot_index=i,
                    candles=candles,
                    is_high=is_high,
                    bars_left=self.bars_left,
                    bars_right=self.bars_right,
                )
                evidence = SwingEvidence(
                    bars_left=self.bars_left,
                    bars_right=self.bars_right,
                    prominence_atr_pct=prominence_atr_pct,
                    is_external=(self.scale_name == "external"),
                    scale_name=self.scale_name,  # type: ignore[arg-type]
                    pivot_index=i,
                    prominence_price=prominence_price,
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
    def __init__(self, config=None):
        if config is None:
            from smc_desk.rules import load_rule_config
            config = load_rule_config()
        scales = config.swing_scales
        self.detectors = [
            SwingDetector(bars_left=scales.local, bars_right=scales.local, scale_name="local"),
            SwingDetector(bars_left=scales.internal, bars_right=scales.internal, scale_name="internal"),
            SwingDetector(bars_left=scales.external, bars_right=scales.external, scale_name="external"),
        ]
        
    def detect(self, candles: List[Candle], current_time: datetime) -> Dict[str, List[SwingObject]]:
        return {d.scale_name: d.detect(candles, current_time) for d in self.detectors}


def _swing_prominence(
    *,
    pivot_index: int,
    candles: List[Candle],
    is_high: bool,
    bars_left: int,
    bars_right: int,
) -> tuple[Decimal, float]:
    pivot = candles[pivot_index]
    left = candles[pivot_index - bars_left : pivot_index]
    right = candles[pivot_index + 1 : pivot_index + bars_right + 1]
    window = left + [pivot] + right
    avg_range = _average_range(window)
    if is_high:
        neighbour = max((c.high for c in left + right), default=pivot.high)
        prominence = max(Decimal("0"), pivot.high - neighbour)
    else:
        neighbour = min((c.low for c in left + right), default=pivot.low)
        prominence = max(Decimal("0"), neighbour - pivot.low)
    if avg_range <= 0:
        return prominence, 0.0
    return prominence, float(prominence / avg_range)


def _average_range(candles: List[Candle]) -> Decimal:
    if not candles:
        return Decimal("0")
    total = sum((c.high - c.low for c in candles), Decimal("0"))
    return total / Decimal(len(candles))
