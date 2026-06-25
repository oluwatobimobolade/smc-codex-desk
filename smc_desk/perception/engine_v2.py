from datetime import datetime
from typing import List, Sequence, Dict
from pydantic import BaseModel, ConfigDict

from smc_desk.data.schemas import Candle
from smc_desk.perception.swings import MultiScaleSwingDetector
from smc_desk.perception.structure import StructureDetector, ProtectedStructureState, StructureBreakObject
from smc_desk.perception.fvg import FVGDetector, FairValueGapObject
from smc_desk.perception.ontology import SwingObject
from smc_desk.rules import RuleConfig, load_rule_config


class PerceptionSnapshot(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    decision_time: datetime
    swings: Dict[str, List[SwingObject]]
    structure_state: dict # Simplifying serialization for now
    structure_breaks: List[StructureBreakObject]
    fvgs: List[FairValueGapObject]


class PerceptionEngineV2:
    def __init__(self, expected_instrument: str = None, expected_timeframe: str = None, config: RuleConfig = None):
        if config is None:
            config = load_rule_config()
        self.config = config
        self.swing_detector = MultiScaleSwingDetector(config=config)
        self.structure_detector = StructureDetector(
            structure_break_min_bps=config.structure_break_min_bps,
        )
        self.fvg_detector = FVGDetector(
            minimum_gap_bps=config.fvg.minimum_gap_bps,
        )
        self.expected_instrument = expected_instrument
        self.expected_timeframe = expected_timeframe
        
    def analyze(
        self,
        candles: Sequence[Candle],
        decision_time: datetime,
    ) -> PerceptionSnapshot:
        """
        Analyzes the market environment strictly up to the given decision_time.
        Performs structural detection without strategic or trade-grading bias.
        """
        
        # 0. Data Integrity Guards (Gauntlet Stage 1)
        if not candles:
            raise ValueError("Empty candle sequence")
            
        valid_candles = []
        last_time = None
        for c in candles:
            # OOD Detection
            if self.expected_instrument and c.instrument != self.expected_instrument:
                raise ValueError(f"OOD mismatch: expected instrument {self.expected_instrument}, got {c.instrument}")
            if self.expected_timeframe and c.timeframe != self.expected_timeframe:
                raise ValueError(f"OOD mismatch: expected timeframe {self.expected_timeframe}, got {c.timeframe}")
                
            if c.open_time > decision_time:
                break # We can stop here assuming chronological order
            if c.close_time > decision_time:
                # This candle is not fully closed by decision time. Ignore it.
                break
                
            if c.contains_gap or not c.is_complete:
                raise ValueError("Cannot analyze sequence containing gaps or incomplete data")
            if not c.is_closed:
                raise ValueError("Cannot process unclosed candles in historical context")
            
            if last_time is not None:
                if c.open_time == last_time:
                    raise ValueError("Duplicate timestamps detected in candle sequence")
                if c.open_time < last_time:
                    raise ValueError("Candle sequence is not strictly chronologically ordered")
            last_time = c.open_time
            valid_candles.append(c)
        
        # 1. Detect Swings at all scales
        swings_by_scale = self.swing_detector.detect(valid_candles, decision_time)
        
        # Merge all confirmed swings for structure parsing
        all_swings = []
        for scale, scale_swings in swings_by_scale.items():
            all_swings.extend(scale_swings)
            
        # 2. Detect Protected Structure and Breaks
        structure_state, breaks = self.structure_detector.detect(valid_candles, all_swings, decision_time)
        
        # 3. Detect Fair Value Gaps
        fvgs = self.fvg_detector.detect(valid_candles, decision_time)
        
        # Serialize structure state safely
        state_dict = {
            "current_direction": structure_state.current_direction,
            "protected_high_id": structure_state.protected_high_id,
            "protected_low_id": structure_state.protected_low_id,
            "last_confirmed_external_high": structure_state.last_confirmed_external_high,
            "last_confirmed_external_low": structure_state.last_confirmed_external_low,
            "last_external_break_id": structure_state.last_external_break.object_id if structure_state.last_external_break else None,
            "last_internal_break_id": structure_state.last_internal_break.object_id if structure_state.last_internal_break else None,
            "current_as_of": structure_state.current_as_of
        }
        
        return PerceptionSnapshot(
            decision_time=decision_time,
            swings=swings_by_scale,
            structure_state=state_dict,
            structure_breaks=breaks,
            fvgs=fvgs
        )
