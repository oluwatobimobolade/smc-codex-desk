from typing import List, Dict, Any, Tuple
from datetime import datetime

from smc_desk.vision.schemas import VisionResponse, VisionObject
from smc_desk.perception.engine_v2 import PerceptionSnapshot

class VisionReconciler:
    def reconcile(
        self,
        vision_res: VisionResponse,
        engine_snap: PerceptionSnapshot
    ) -> Dict[str, Any]:
        """
        Reconciles vision-detected objects against deterministic engine snapshot objects.
        """
        report = {
            "reconciliation_id": f"recon_{datetime.now().timestamp()}",
            "vision_response_id": vision_res.response_id,
            "decision_time": vision_res.created_at.isoformat(),
            "matches": [],
            "engine_only": [],
            "vision_only": [],
            "abstained": [],
            "disagreements": []
        }
        
        if vision_res.abstain:
            report["abstained"].append({
                "reason": vision_res.abstention_reason,
                "scope": "full_response"
            })
            return report

        # Extract all engine objects flat
        engine_objs = []
        for scale, sw_list in engine_snap.swings.items():
            for sw in sw_list:
                engine_objs.append(("swing", sw))
        for fvg in engine_snap.fvgs:
            engine_objs.append(("fvg", fvg))
        for brk in engine_snap.structure_breaks:
            engine_objs.append(("structure_break", brk))

        matched_engine_ids = set()
        
        for v_obj in vision_res.detected_objects:
            if v_obj.ambiguous:
                report["abstained"].append({
                    "object_id": v_obj.vision_object_id,
                    "reason": v_obj.ambiguity_reason,
                    "scope": "object_level"
                })
                continue
                
            matched = False
            for eng_type, eng_obj in engine_objs:
                if eng_obj.object_id in matched_engine_ids:
                    continue
                    
                # Match type
                type_match = (v_obj.object_type == "swing_high" and eng_type == "swing" and eng_obj.direction == "bearish") or \
                             (v_obj.object_type == "swing_low" and eng_type == "swing" and eng_obj.direction == "bullish") or \
                             (v_obj.object_type == "bullish_fvg" and eng_type == "fvg" and eng_obj.direction == "bullish") or \
                             (v_obj.object_type == "bearish_fvg" and eng_type == "fvg" and eng_obj.direction == "bearish") or \
                             (v_obj.object_type in ["bos", "choch"] and eng_type == "structure_break")
                             
                if type_match:
                    # Match timing/price proximity
                    # Let's say FVG or Swing matches if temporal region overlaps
                    # or if pivot time is close.
                    time_diff = abs((v_obj.created_at - eng_obj.pivot_time).total_seconds()) if hasattr(v_obj, "created_at") else 0
                    # Standard fallback overlap
                    overlap_match = True # simplified matching in Phase 4 dry-runs
                    
                    if overlap_match:
                        # Check direction & scope
                        dir_mismatch = (v_obj.direction != eng_obj.direction.value)
                        scope_mismatch = (v_obj.scope != eng_obj.evidence.is_external) if (v_obj.scope and hasattr(eng_obj.evidence, "is_external")) else False
                        
                        status = "exact_match"
                        if dir_mismatch:
                            status = "direction_mismatch"
                            report["disagreements"].append({
                                "vision_object_id": v_obj.vision_object_id,
                                "engine_object_id": eng_obj.object_id,
                                "type": "direction_mismatch"
                            })
                        elif scope_mismatch:
                            status = "scope_mismatch"
                            report["disagreements"].append({
                                "vision_object_id": v_obj.vision_object_id,
                                "engine_object_id": eng_obj.object_id,
                                "type": "scope_mismatch"
                            })
                            
                        report["matches"].append({
                            "vision_object_id": v_obj.vision_object_id,
                            "engine_object_id": eng_obj.object_id,
                            "status": status
                        })
                        matched_engine_ids.add(eng_obj.object_id)
                        matched = True
                        break
                        
            if not matched:
                report["vision_only"].append(v_obj.vision_object_id)
                
        for eng_type, eng_obj in engine_objs:
            if eng_obj.object_id not in matched_engine_ids:
                report["engine_only"].append(eng_obj.object_id)
                
        return report
