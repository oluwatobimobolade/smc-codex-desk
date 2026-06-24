from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple, Union

class PixelGeometry(BaseModel):
    x1: Optional[float] = None
    x2: Optional[float] = None
    y1: Optional[float] = None
    y2: Optional[float] = None
    anchor_x: Optional[float] = None
    anchor_y: Optional[float] = None
    polygon_points: Optional[List[Tuple[float, float]]] = None

class MarketGeometry(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    price_low: Optional[Decimal] = None
    price_high: Optional[Decimal] = None
    pivot_time: Optional[datetime] = None
    event_time: Optional[datetime] = None
    source_candle_ids: List[str] = Field(default_factory=list)

class LeaderLineGeometry(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

class VisualObject(BaseModel):
    visual_object_id: str
    semantic_object_id: Optional[str] = None
    semantic_object_type: Optional[str] = None
    shape_type: str  # candlestick, horizontal_line, vertical_line, polyline, rectangle, marker, text_label, leader_line, shaded_region
    z_index: int
    visibility_status: str  # visible, hidden, omitted
    omission_reason: Optional[str] = None
    pixel_geometry: PixelGeometry
    market_geometry: MarketGeometry
    style_token: str
    label_text: Optional[str] = None
    label_anchor: Optional[str] = None
    leader_line_geometry: Optional[LeaderLineGeometry] = None
    renderer_version: str = "2.0.0"
    semantic_schema_version: str = "1.0.0"
    source_object_hash: Optional[str] = None

class SceneGraph(BaseModel):
    scene_graph_id: str
    renderer_version: str = "2.0.0"
    generated_at: datetime
    objects: List[VisualObject] = Field(default_factory=list)
    omitted_objects_report: List[dict] = Field(default_factory=list)
