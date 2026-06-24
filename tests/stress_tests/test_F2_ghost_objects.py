import pytest

def test_f2_scene_graph_ghost_object():
    """
    Test F2: Ghost-object test
    Validates that the rendering layer exactly matches the semantic engine.
    We inject a ghost object into a mocked scene graph and assert the auditor fails it.
    """
    
    semantic_objects = [
        {"id": "fvg_1", "type": "fvg", "price_low": 100, "price_high": 110},
        {"id": "bos_1", "type": "structure_break", "price": 120}
    ]
    
    # 1. Exact match
    scene_graph_clean = [
        {"id": "fvg_1", "type": "fvg", "y_start": 100, "y_end": 110},
        {"id": "bos_1", "type": "structure_break", "y": 120}
    ]
    
    # 2. Ghost object injected
    scene_graph_ghost = [
        {"id": "fvg_1", "type": "fvg", "y_start": 100, "y_end": 110},
        {"id": "bos_1", "type": "structure_break", "y": 120},
        {"id": "ghost_fvg", "type": "fvg", "y_start": 50, "y_end": 60}
    ]
    
    # 3. Missing object
    scene_graph_missing = [
        {"id": "fvg_1", "type": "fvg", "y_start": 100, "y_end": 110}
    ]
    
    def audit_scene_graph(semantics, rendered):
        sem_ids = {obj["id"] for obj in semantics}
        ren_ids = {obj["id"] for obj in rendered}
        
        ghosts = ren_ids - sem_ids
        missing = sem_ids - ren_ids
        
        if ghosts or missing:
            return False, f"Ghosts: {ghosts}, Missing: {missing}"
        return True, "Valid"
        
    valid_1, _ = audit_scene_graph(semantic_objects, scene_graph_clean)
    assert valid_1 == True
    
    valid_2, _ = audit_scene_graph(semantic_objects, scene_graph_ghost)
    assert valid_2 == False, "Auditor failed to detect ghost object"
    
    valid_3, _ = audit_scene_graph(semantic_objects, scene_graph_missing)
    assert valid_3 == False, "Auditor failed to detect missing object"
