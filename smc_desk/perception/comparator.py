from typing import Any, Dict, List, Tuple
from datetime import datetime
import pandas as pd
from decimal import Decimal

from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.perception.ontology import SMCObjectBase, SwingObject, FairValueGapObject, StructureBreakObject, Direction

# Match thresholds
PRICE_TOLERANCE_PCT = 0.0005 # 5 bps for price matching
TIME_TOLERANCE_SECONDS = 900 # 1 candle at 15m

class MismatchClass:
    V1_ONLY = "V1_ONLY"
    V2_ONLY = "V2_ONLY"
    MATCHED_EXACT = "MATCHED_EXACT"
    MATCHED_GEOMETRY_DIFFERENCE = "MATCHED_GEOMETRY_DIFFERENCE"
    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"
    SCOPE_DIFFERENCE = "SCOPE_DIFFERENCE"
    CLASSIFICATION_DIFFERENCE = "CLASSIFICATION_DIFFERENCE"
    BROKEN_SWING_LINK_DIFFERENCE = "BROKEN_SWING_LINK_DIFFERENCE"
    LIFECYCLE_DIFFERENCE = "LIFECYCLE_DIFFERENCE"


class DualRunComparator:
    """Compares V1 monolithic engine output against V2 perception output."""
    
    def compare(self, v1_result: Any, v2_result: PerceptionSnapshot, df: pd.DataFrame) -> Dict[str, Any]:
        report = {
            "swings": self._compare_swings(v1_result.swings, self._flatten_v2_swings(v2_result.swings)),
            "fvgs": self._compare_fvgs([z for z in v1_result.zones if z.kind == "fvg"], v2_result.fvgs, df),
            "breaks": self._compare_breaks([e for e in v1_result.events if e.label in ["BOS", "CHoCH"]], v2_result.structure_breaks, df)
        }
        return report
        
    def _flatten_v2_swings(self, swings_dict: Dict[str, List[SwingObject]]) -> List[SwingObject]:
        flat = []
        for scale, swings in swings_dict.items():
            flat.extend(swings)
        return flat
        
    def _is_price_match(self, p1: float, p2: Decimal) -> bool:
        if p1 == 0: return float(p2) == 0
        diff_pct = abs((float(p2) - p1) / p1)
        return diff_pct <= PRICE_TOLERANCE_PCT
        
    def _is_time_match(self, t1_str: str, t2: datetime) -> bool:
        # V1 timestamps are strings or pandas timestamps
        t1 = pd.to_datetime(t1_str).tz_localize("UTC") if pd.to_datetime(t1_str).tzinfo is None else pd.to_datetime(t1_str)
        diff_sec = abs((t2 - t1).total_seconds())
        return diff_sec <= TIME_TOLERANCE_SECONDS

    def _compare_swings(self, v1_swings: List[Any], v2_swings: List[SwingObject]) -> List[Dict]:
        results = []
        v2_unmatched = list(v2_swings)
        
        for v1_sw in v1_swings:
            v1_dir = Direction.BULLISH if v1_sw.kind == "low" else Direction.BEARISH
            matched = False
            
            for v2_sw in list(v2_unmatched):
                if v2_sw.direction == v1_dir and self._is_price_match(v1_sw.price, v2_sw.price_low if v1_dir == Direction.BULLISH else v2_sw.price_high):
                    if self._is_time_match(v1_sw.timestamp, v2_sw.pivot_time):
                        results.append({"v1": v1_sw.dict(), "v2": v2_sw.object_id, "status": MismatchClass.MATCHED_EXACT})
                        v2_unmatched.remove(v2_sw)
                        matched = True
                        break
                    else:
                        results.append({"v1": v1_sw.dict(), "v2": v2_sw.object_id, "status": MismatchClass.TIMING_DIFFERENCE})
                        v2_unmatched.remove(v2_sw)
                        matched = True
                        break
            if not matched:
                results.append({"v1": v1_sw.dict(), "v2": None, "status": MismatchClass.V1_ONLY})
                
        for v2_sw in v2_unmatched:
            results.append({"v1": None, "v2": v2_sw.object_id, "status": MismatchClass.V2_ONLY})
            
        return results

    def _compare_fvgs(self, v1_fvgs: List[Any], v2_fvgs: List[FairValueGapObject], df: pd.DataFrame) -> List[Dict]:
        results = []
        v2_unmatched = list(v2_fvgs)
        
        for v1_fvg in v1_fvgs:
            v1_dir = Direction.BULLISH if v1_fvg.direction == "bullish" else Direction.BEARISH
            matched = False
            
            # V1 FVG origin time can be approximated by start_index
            v1_time = df.iloc[v1_fvg.start_index]["timestamp"] if v1_fvg.start_index is not None and v1_fvg.start_index < len(df) else None
            
            for v2_fvg in list(v2_unmatched):
                if v2_fvg.direction == v1_dir:
                    # Check overlap (Geometry)
                    overlap = min(v1_fvg.high, float(v2_fvg.price_high)) - max(v1_fvg.low, float(v2_fvg.price_low))
                    if overlap > 0:
                        # Match found
                        if self._is_price_match(v1_fvg.low, v2_fvg.price_low) and self._is_price_match(v1_fvg.high, v2_fvg.price_high):
                            results.append({"v1": v1_fvg.dict(), "v2": v2_fvg.object_id, "status": MismatchClass.MATCHED_EXACT})
                        else:
                            results.append({"v1": v1_fvg.dict(), "v2": v2_fvg.object_id, "status": MismatchClass.MATCHED_GEOMETRY_DIFFERENCE})
                            
                        v2_unmatched.remove(v2_fvg)
                        matched = True
                        break
                        
            if not matched:
                results.append({"v1": v1_fvg.dict(), "v2": None, "status": MismatchClass.V1_ONLY})
                
        for v2_fvg in v2_unmatched:
            results.append({"v1": None, "v2": v2_fvg.object_id, "status": MismatchClass.V2_ONLY})
            
        return results

    def _compare_breaks(self, v1_breaks: List[Any], v2_breaks: List[StructureBreakObject], df: pd.DataFrame) -> List[Dict]:
        results = []
        v2_unmatched = list(v2_breaks)
        
        for v1_brk in v1_breaks:
            v1_dir = Direction.BULLISH if v1_brk.direction == "bullish" else Direction.BEARISH
            matched = False
            
            for v2_brk in list(v2_unmatched):
                if v2_brk.direction == v1_dir:
                    # Match by broken level proximity
                    if v1_brk.broken_level is not None and self._is_price_match(v1_brk.broken_level, v2_brk.evidence.broken_price):
                        status = MismatchClass.MATCHED_EXACT
                        
                        # Check classification (BOS vs CHoCH)
                        if v1_brk.label != v2_brk.break_type:
                            status = MismatchClass.CLASSIFICATION_DIFFERENCE
                        # Check scope
                        v1_scope = v1_brk.structure_scope == "internal"
                        if v1_scope != v2_brk.evidence.is_internal:
                            status = MismatchClass.SCOPE_DIFFERENCE
                        # Check timing
                        if not self._is_time_match(v1_brk.timestamp, v2_brk.candidate_at):
                            status = MismatchClass.TIMING_DIFFERENCE
                            
                        results.append({"v1": v1_brk.dict(), "v2": v2_brk.object_id, "status": status})
                        v2_unmatched.remove(v2_brk)
                        matched = True
                        break
                        
            if not matched:
                results.append({"v1": v1_brk.dict(), "v2": None, "status": MismatchClass.V1_ONLY})
                
        for v2_brk in v2_unmatched:
            results.append({"v1": None, "v2": v2_brk.object_id, "status": MismatchClass.V2_ONLY})
            
        return results
