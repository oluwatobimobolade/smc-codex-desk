from datetime import datetime
from typing import List, Sequence, Dict
from pydantic import BaseModel, ConfigDict, Field

from smc_desk.data.schemas import Candle
from smc_desk.perception.swings import MultiScaleSwingDetector
from smc_desk.perception.structure import StructureDetector, ProtectedStructureState, StructureBreakObject
from smc_desk.perception.fvg import FVGDetector, FairValueGapObject
from smc_desk.perception.inducement import InducementDetector
from smc_desk.perception.liquidity import LiquidityLevelDetector, SweepDetector
from smc_desk.perception.order_blocks import OrderBlockDetector, mark_poi_grade_fvgs
from smc_desk.perception.ontology import (
    InducementObject,
    LiquidityLevelObject,
    OrderBlockObject,
    SweepObject,
    SwingObject,
)
from smc_desk.rules import RuleConfig, load_rule_config


class PerceptionSnapshot(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    decision_time: datetime
    swings: Dict[str, List[SwingObject]]
    structure_state: dict # Simplifying serialization for now
    structure_breaks: List[StructureBreakObject]
    fvgs: List[FairValueGapObject]
    liquidity_levels: List[LiquidityLevelObject] = Field(default_factory=list)
    sweeps: List[SweepObject] = Field(default_factory=list)
    order_blocks: List[OrderBlockObject] = Field(default_factory=list)
    inducements: List[InducementObject] = Field(default_factory=list)
    poi_grade_fvgs: List[FairValueGapObject] = Field(default_factory=list)


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
        self.liquidity_detector = LiquidityLevelDetector(
            tolerance_bps=config.equal_level_tolerance_bps,
            min_touches=config.equal_level_min_touches,
            max_recent_swings=config.liquidity_sweep_lookback,
        )
        self.sweep_detector = SweepDetector(
            min_penetration_bps=max(config.structure_break_min_bps / 2.0, 1.0),
        )
        self.order_block_detector = OrderBlockDetector(
            lookback=config.ob_lookback,
            min_body_ratio=min(max(config.ob_min_body_factor / 2.0, 0.20), 0.90),
        )
        self.inducement_detector = InducementDetector()
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

        # 4. Stage B trader primitives. These are still observe-only perception
        # objects; they do not authorize a trade.
        fvgs = mark_poi_grade_fvgs(fvgs, breaks)
        liquidity_levels = self.liquidity_detector.detect(all_swings, decision_time)
        sweeps = self.sweep_detector.detect(valid_candles, liquidity_levels, decision_time)
        # Order blocks should only be mapped to qualified FVGs (system quality filter)
        qualified_fvgs = [f for f in fvgs if f.metadata.get("is_qualified", True)]
        order_blocks = self.order_block_detector.detect(valid_candles, breaks, qualified_fvgs, decision_time)
        inducements = self.inducement_detector.detect(all_swings, order_blocks, breaks, sweeps, decision_time)
        poi_grade_fvgs = [fvg for fvg in fvgs if fvg.evidence.poi_grade and fvg.metadata.get("is_qualified", True)]
        
        # Serialize structure state safely
        state_dict = {
            "current_direction": structure_state.current_direction,
            "protected_high_id": structure_state.protected_high_id,
            "protected_low_id": structure_state.protected_low_id,
            "last_confirmed_external_high": structure_state.last_confirmed_external_high,
            "last_confirmed_external_low": structure_state.last_confirmed_external_low,
            "last_confirmed_internal_high": structure_state.last_confirmed_internal_high,
            "last_confirmed_internal_low": structure_state.last_confirmed_internal_low,
            "last_external_break_id": structure_state.last_external_break.object_id if structure_state.last_external_break else None,
            "last_internal_break_id": structure_state.last_internal_break.object_id if structure_state.last_internal_break else None,
            "internal_direction": structure_state.internal_direction,
            "protected_internal_high_id": structure_state.protected_internal_high_id,
            "protected_internal_low_id": structure_state.protected_internal_low_id,
            "current_as_of": structure_state.current_as_of
        }
        
        return PerceptionSnapshot(
            decision_time=decision_time,
            swings=swings_by_scale,
            structure_state=state_dict,
            structure_breaks=breaks,
            fvgs=fvgs,
            liquidity_levels=liquidity_levels,
            sweeps=sweeps,
            order_blocks=order_blocks,
            inducements=inducements,
            poi_grade_fvgs=poi_grade_fvgs,
        )
