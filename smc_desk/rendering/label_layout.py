from typing import List, Tuple, Optional, Dict
from pydantic import BaseModel

class LabelLayoutItem(BaseModel):
    semantic_id: str
    text: str
    anchor_x: float
    anchor_y: float
    width: float
    height: float
    placed_x: Optional[float] = None
    placed_y: Optional[float] = None
    offset_y: float = 0.0
    has_leader_line: bool = False
    omitted: bool = False
    omission_reason: Optional[str] = None

class LabelLayoutEngine:
    def __init__(self, plot_left: float, plot_right: float, plot_top: float, plot_bottom: float, final_candle_x: Optional[float] = None):
        self.plot_left = plot_left
        self.plot_right = plot_right
        self.plot_top = plot_top
        self.plot_bottom = plot_bottom
        self.final_candle_x = final_candle_x
        self.placed_boxes: List[Tuple[float, float, float, float, str]] = [] # (x1, y1, x2, y2, id)
        self.unresolved_collisions: List[dict] = []

    def _overlaps(self, box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> bool:
        x1_a, y1_a, x2_a, y2_a = box1
        x1_b, y1_b, x2_b, y2_b = box2
        # overlapping conditions
        return not (x2_a < x1_b or x2_b < x1_a or y2_a < y1_b or y2_b < y1_a)

    def layout_labels(self, labels: List[LabelLayoutItem], step_size: float = 15.0, max_attempts: int = 15) -> List[LabelLayoutItem]:
        results = []
        for item in labels:
            # We want to place item. Try placing at anchor first.
            w = item.width
            h = item.height
            
            placed = False
            collision_list = []
            
            # Anchor coordinate (x is typically fixed, we nudge vertically)
            x_pos = item.anchor_x
            # Ensure label doesn't go off plot right edge
            if x_pos + w > self.plot_right:
                x_pos = self.plot_right - w
            if x_pos < self.plot_left:
                x_pos = self.plot_left

            # Nudge attempts
            # We try 0, then +step, -step, +2*step, -2*step, etc.
            nudges = [0]
            for i in range(1, max_attempts + 1):
                nudges.append(i * step_size)
                nudges.append(-i * step_size)
                
            for offset in nudges:
                y_pos = item.anchor_y + offset
                # Keep within plot bounds vertically
                if y_pos < self.plot_top or y_pos + h > self.plot_bottom:
                    continue
                    
                # Bounding box candidate: x1, y1, x2, y2
                cand_box = (x_pos, y_pos, x_pos + w, y_pos + h)
                
                # Check collision with other placed labels
                collision = False
                current_collisions = []
                for px1, py1, px2, py2, pid in self.placed_boxes:
                    if self._overlaps(cand_box, (px1, py1, px2, py2)):
                        collision = True
                        current_collisions.append(pid)
                        
                # Check collision with final candle area to prevent covering it
                if self.final_candle_x is not None:
                    # Final candle buffer: let's say 20px around final_candle_x
                    final_box = (self.final_candle_x - 15, self.plot_top, self.final_candle_x + 15, self.plot_bottom)
                    if self._overlaps(cand_box, final_box):
                        collision = True
                        current_collisions.append("FINAL_CANDLE_PROTECTION")

                if not collision:
                    # Found a spot!
                    item.placed_x = x_pos
                    item.placed_y = y_pos
                    item.offset_y = offset
                    item.has_leader_line = abs(offset) > step_size * 1.5
                    self.placed_boxes.append((x_pos, y_pos, x_pos + w, y_pos + h, item.semantic_id))
                    placed = True
                    break
                else:
                    collision_list.extend(current_collisions)

            if not placed:
                # Omit if it absolutely cannot be placed
                item.omitted = True
                item.omission_reason = f"Label collision could not be resolved. Collided with: {list(set(collision_list))}"
                self.unresolved_collisions.append({
                    "semantic_object_id": item.semantic_id,
                    "attempted_anchor": (item.anchor_x, item.anchor_y),
                    "collision_objects": list(set(collision_list)),
                    "decision": "OMITTED"
                })
            results.append(item)
        return results
