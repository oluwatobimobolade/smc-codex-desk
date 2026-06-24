from typing import Dict, Any, List
from smc_desk.rendering.scene_graph import SceneGraph

class MetamorphicTestRunner:
    def __init__(self):
        pass

    def verify_visual_invariance(self, scene_graphs: List[SceneGraph]) -> bool:
        """
        Asserts that changes to rendering parameters (theme, grid lines, size)
        do not change the semantic content of the scene graph.
        """
        if not scene_graphs:
            return True
            
        base = scene_graphs[0]
        # Helper to extract semantic items
        def extract_semantics(sg: SceneGraph) -> List[Dict[str, Any]]:
            items = []
            for obj in sg.objects:
                if obj.semantic_object_id:
                    items.append({
                        "id": obj.semantic_object_id,
                        "type": obj.semantic_object_type,
                        "low": float(obj.market_geometry.price_low) if obj.market_geometry.price_low else None,
                        "high": float(obj.market_geometry.price_high) if obj.market_geometry.price_high else None
                    })
            return sorted(items, key=lambda x: (x["id"] or "", x["type"] or ""))

        base_semantics = extract_semantics(base)
        for sg in scene_graphs[1:]:
            current_semantics = extract_semantics(sg)
            if current_semantics != base_semantics:
                return False
        return True
