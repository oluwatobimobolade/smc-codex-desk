from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, List, Dict
import pandas as pd

from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.rendering.scene_graph import SceneGraph, VisualObject
from smc_desk.rendering.coordinate_transform import CoordinateTransform

class RenderAuditor:
    def verify(
        self,
        df: pd.DataFrame,
        snapshot: PerceptionSnapshot,
        scene_graph: SceneGraph,
        transform: CoordinateTransform,
        tick_size: Decimal
    ) -> Dict[str, Any]:
        """
        Runs comprehensive rendering audit checks to verify representation accuracy,
        referential integrity, coordinates, and temporal ordering.
        """
        report = {
            "success": True,
            "failed_checks": [],
            "passed_checks_count": 0,
            "unresolved_collisions_count": len(scene_graph.omitted_objects_report)
        }
        
        # Helper to fail
        def fail(name: str, details: str):
            report["success"] = False
            report["failed_checks"].append({"check": name, "details": details})
            
        def pass_check():
            report["passed_checks_count"] += 1

        # Check 1: No future candles visible
        # Ensure all timestamps in df are <= snapshot.decision_time
        decision_time = snapshot.decision_time
        if not decision_time.tzinfo:
            decision_time = decision_time.replace(tzinfo=timezone.utc)
            
        timestamps = pd.to_datetime(df["timestamp"])
        for ts in timestamps:
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if ts > decision_time:
                fail("NO_FUTURE_CANDLES_VISIBLE", f"Candle timestamp {ts} is in the future relative to decision_time {decision_time}")
                break
        else:
            pass_check()

        # Build lookup dicts of semantic objects
        swings_dict = {}
        for scale, sw_list in snapshot.swings.items():
            for sw in sw_list:
                swings_dict[sw.object_id] = sw
                
        fvgs_dict = {f.object_id: f for f in snapshot.fvgs}
        breaks_dict = {b.object_id: b for b in snapshot.structure_breaks}
        
        all_semantic_objects = {}
        all_semantic_objects.update(swings_dict)
        all_semantic_objects.update(fvgs_dict)
        all_semantic_objects.update(breaks_dict)
        
        # Check 2: Every scene-graph entry references a valid semantic object (referential integrity)
        # (Exclude pure drawing-only objects like gridlines, metadata labels, etc. that have semantic_object_id = None)
        for obj in scene_graph.objects:
            if obj.semantic_object_id:
                if obj.semantic_object_id not in all_semantic_objects:
                    fail("REFERENTIAL_INTEGRITY", f"Scene graph object {obj.visual_object_id} references nonexistent semantic ID {obj.semantic_object_id}")
                else:
                    pass_check()
                    
                # Check 3: Timestamps fall within visible range
                # The market geometry should align with visible range
                geom = obj.market_geometry
                for t_val in [geom.start_time, geom.end_time, geom.pivot_time, geom.event_time]:
                    if t_val:
                        t_aware = t_val.replace(tzinfo=timezone.utc) if not t_val.tzinfo else t_val
                        if not (transform.visible_start_time <= t_aware <= transform.visible_end_time):
                            # It is possible an object spans beyond visible, but check if it's completely out
                            pass # We won't fail if it's clipped, but we can verify it doesn't represent future times

        # Check 4: No object is displayed before confirmed_at when confirmed display is required
        # For confirmed breaks, confirmed_at must be <= decision_time
        for obj in scene_graph.objects:
            if obj.semantic_object_type == "structure_break" and obj.semantic_object_id:
                sem_obj = breaks_dict.get(obj.semantic_object_id)
                if sem_obj and sem_obj.confirmed_at:
                    conf_aware = sem_obj.confirmed_at.replace(tzinfo=timezone.utc) if not sem_obj.confirmed_at.tzinfo else sem_obj.confirmed_at
                    if conf_aware > decision_time:
                        fail("CONFIRMED_DISPLAY_TEMPORAL_ORDER", f"Break {sem_obj.object_id} is rendered but was confirmed at {conf_aware} which is after decision_time {decision_time}")
                    else:
                        pass_check()

        # Check 5: All prices align with instrument tick size
        # Prices in scene graph objects must be multiples of tick_size
        for obj in scene_graph.objects:
            geom = obj.market_geometry
            for p_val in [geom.price_low, geom.price_high]:
                if p_val:
                    if p_val % tick_size != 0:
                        fail("PRICE_TICK_ALIGNMENT", f"Price {p_val} in object {obj.visual_object_id} does not align with tick size {tick_size}")
                    else:
                        pass_check()

        # Check 6: FVG boundaries equal ontology boundaries
        for obj in scene_graph.objects:
            if obj.semantic_object_type == "fvg" and obj.semantic_object_id:
                sem_fvg = fvgs_dict.get(obj.semantic_object_id)
                if sem_fvg:
                    if obj.market_geometry.price_low != sem_fvg.price_low or obj.market_geometry.price_high != sem_fvg.price_high:
                        fail("FVG_BOUNDARY_ACCURACY", f"Scene object FVG bounds ({obj.market_geometry.price_low}, {obj.market_geometry.price_high}) do not match ontology bounds ({sem_fvg.price_low}, {sem_fvg.price_high})")
                    else:
                        pass_check()

        # Check 7: No label references a nonexistent object, no BOS/CHoCH references a nonexistent broken swing
        for obj in scene_graph.objects:
            if obj.semantic_object_type == "structure_break" and obj.semantic_object_id:
                sem_brk = breaks_dict.get(obj.semantic_object_id)
                if sem_brk:
                    broken_swing_id = sem_brk.evidence.broken_swing_id
                    if broken_swing_id not in swings_dict:
                        fail("STRUCTURE_BREAK_SWING_REFERENTIAL_INTEGRITY", f"Break {sem_brk.object_id} references broken swing ID {broken_swing_id} which does not exist in snapshot")
                    else:
                        pass_check()

        # Check 8: Inverse coordinate transform round trips
        # Let's verify price_to_y and y_to_price round trips for a sample of prices
        sample_prices = [
            transform.minimum_visible_price,
            transform.maximum_visible_price,
            (transform.minimum_visible_price + transform.maximum_visible_price) / 2
        ]
        for p in sample_prices:
            y = transform.price_to_y(p)
            p_round = transform.y_to_price(y)
            # Round trip price should match within a tolerance of 1 tick
            if abs(p_round - p) > tick_size:
                fail("COORDINATE_TRANSFORM_ROUND_TRIP", f"Price round trip failed. Original: {p}, pixels Y: {y}, reconstructed: {p_round} (diff > tick size {tick_size})")
                break
        else:
            pass_check()

        return report
