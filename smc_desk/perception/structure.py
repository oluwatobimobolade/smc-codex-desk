import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple, Dict

from smc_desk.data.schemas import Candle
from smc_desk.perception.ontology import Direction, SwingObject, StructureBreakEvidence, SMCObjectBase, ConfirmationStatus
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event

class StructureBreakObject(SMCObjectBase):
    break_type: str  # "BOS" or "CHOCH"
    evidence: StructureBreakEvidence


class ProtectedStructureState:
    def __init__(self):
        self.current_direction: Optional[Direction] = None
        self.protected_high_id: Optional[str] = None
        self.protected_low_id: Optional[str] = None
        self.last_confirmed_external_high: Optional[str] = None
        self.last_confirmed_external_low: Optional[str] = None
        self.last_external_break: Optional[StructureBreakObject] = None
        self.last_internal_break: Optional[StructureBreakObject] = None
        self.current_as_of: Optional[datetime] = None


class StructureDetector:
    def __init__(self, detector_version: str = "2.0"):
        self.detector_version = detector_version
        self.configuration_hash = hashlib.sha256(b"structure_v2").hexdigest()[:8]
        
    def detect(self, candles: List[Candle], swings: List[SwingObject], current_time: datetime) -> Tuple[ProtectedStructureState, List[StructureBreakObject]]:
        state = ProtectedStructureState()
        breaks = []
        
        # Sort swings by chronological order of pivot time
        swings = sorted(swings, key=lambda s: s.pivot_time)
        
        # Dictionary for quick lookup
        swing_dict = {s.object_id: s for s in swings}
        
        # We need to process candles chronologically alongside the confirmed swings.
        # However, a swing is only "known" at its `confirmed_at`.
        # So we process events strictly in time order.
        
        # For simplicity in Phase 2, let's track the latest external swings
        # and check each candle to see if it breaks them.
        
        active_external_high = None
        active_external_low = None
        
        pending_upward_break = None
        pending_downward_break = None
        
        for c in candles:
            if c.close_time > current_time:
                break
                
            state.current_as_of = c.close_time
            
            # 1. Update our known swings. Did any swing get confirmed ON this candle close?
            newly_confirmed = [s for s in swings if s.confirmed_at == c.close_time and s.evidence.is_external]
            for s in newly_confirmed:
                if s.direction == Direction.BEARISH: # Bearish swing means a High
                    active_external_high = s
                    state.last_confirmed_external_high = s.object_id
                    pending_upward_break = None # Reset pending break for new high
                else: # Bullish swing means a Low
                    active_external_low = s
                    state.last_confirmed_external_low = s.object_id
                    pending_downward_break = None # Reset pending break for new low
                    
            # 2. Check for breaks of the active external swings
            if active_external_high:
                if c.high > active_external_high.price_high:
                    if not pending_upward_break:
                        # First penetration creates the break object
                        pending_upward_break = self._create_break(c, active_external_high, Direction.BULLISH, state, current_time)
                        breaks.append(pending_upward_break)
                    
                    # If the body closes above, it confirms the break
                    if c.close > active_external_high.price_high and pending_upward_break.confirmation_status == ConfirmationStatus.CANDIDATE:
                        self._confirm_break(pending_upward_break, c, state)
                        active_external_high = None # Consumed
                        pending_upward_break = None
                        
            if active_external_low:
                if c.low < active_external_low.price_low:
                    if not pending_downward_break:
                        # First penetration creates the break object
                        pending_downward_break = self._create_break(c, active_external_low, Direction.BEARISH, state, current_time)
                        breaks.append(pending_downward_break)
                        
                    # If the body closes below, it confirms the break
                    if c.close < active_external_low.price_low and pending_downward_break.confirmation_status == ConfirmationStatus.CANDIDATE:
                        self._confirm_break(pending_downward_break, c, state)
                        active_external_low = None # Consumed
                        pending_downward_break = None
                    
        return state, breaks
        
    def _create_break(self, candle: Candle, broken_swing: SwingObject, direction: Direction, state: ProtectedStructureState, current_time: datetime) -> StructureBreakObject:
        is_continuation = state.current_direction == direction
        break_type = "BOS" if is_continuation or state.current_direction is None else "CHOCH"
        
        # Calculate penetration metrics
        wick_pen = candle.high - broken_swing.price_high if direction == Direction.BULLISH else broken_swing.price_low - candle.low
        body_pen = candle.close - broken_swing.price_high if direction == Direction.BULLISH else broken_swing.price_low - candle.close
        
        evidence = StructureBreakEvidence(
            broken_swing_id=broken_swing.object_id,
            broken_price=broken_swing.price_high if direction == Direction.BULLISH else broken_swing.price_low,
            wick_penetration=wick_pen,
            body_close_penetration=body_pen,
            penetration_ticks=0,
            penetration_atr_pct=0.0,
            candle_body_ratio=float((candle.close - candle.open) / (candle.high - candle.low)) if candle.high != candle.low else 0,
            displacement_strength=0.0,
            is_internal=False,
            is_unconfirmed_probe=True # Initially a probe
        )
        
        obj_id = f"{break_type}_{direction.value}_{candle.open_time.timestamp()}"
        
        brk = StructureBreakObject(
            object_id=obj_id,
            venue=candle.venue,
            instrument=candle.instrument,
            timeframe=candle.timeframe,
            pivot_time=broken_swing.pivot_time,
            candidate_at=candle.open_time,
            confirmed_at=None, # Not confirmed yet
            current_as_of=current_time,
            schema_version="1.0.0",
            detector_version=self.detector_version,
            configuration_hash=self.configuration_hash,
            source_candle_ids=[f"c_{candle.open_time.timestamp()}"],
            last_updated_at=current_time,
            confidence=1.0,
            direction=direction,
            price_low=candle.low,
            price_high=candle.high,
            break_type=break_type,
            evidence=evidence,
            confirmation_status=ConfirmationStatus.CANDIDATE,
            is_choch=(break_type == "CHOCH")
        )
        
        creation_event = SMCEvent(
            event_type=EventType.OBJECT_CREATED,
            timestamp=candle.open_time,
            trigger_candle_id=f"c_{candle.open_time.timestamp()}",
            details="Wick penetration recorded as probe"
        )
        apply_event(brk, creation_event)
        
        return brk

    def _confirm_break(self, brk: StructureBreakObject, candle: Candle, state: ProtectedStructureState):
        brk.evidence.is_unconfirmed_probe = False
        brk.evidence.body_close_penetration = candle.close - brk.evidence.broken_price if brk.direction == Direction.BULLISH else brk.evidence.broken_price - candle.close
        brk.source_candle_ids.append(f"c_{candle.open_time.timestamp()}")
        
        brk.confirmation_status = ConfirmationStatus.CONFIRMED
        brk.confirmed_at = candle.close_time
        
        confirmation_event = SMCEvent(
            event_type=EventType.OBJECT_CONFIRMED,
            timestamp=candle.close_time,
            trigger_candle_id=f"c_{candle.open_time.timestamp()}",
            details="Body close confirmed structural break"
        )
        apply_event(brk, confirmation_event)
        
        # State transitions only happen on confirmation
        state.current_direction = brk.direction
        
        if brk.break_type == "BOS":
            if brk.direction == Direction.BULLISH:
                state.protected_low_id = state.last_confirmed_external_low
            else:
                state.protected_high_id = state.last_confirmed_external_high
            state.last_external_break = brk
        else:
            state.last_external_break = brk
