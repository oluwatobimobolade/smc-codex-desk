from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class ScreenshotManifest(BaseModel):
    case_id: Optional[str] = None
    venue: str
    instrument: str
    market_type: str
    timeframe: str
    decision_time: str
    latest_completed_candle: str
    timezone: str
    visible_start_time: str
    visible_end_time: str
    visible_bar_count: int
    price_scale: str
    price_minimum: float
    price_maximum: float
    tick_size: float
    chart_width: float
    chart_height: float
    plot_bounds: Dict[str, float]
    device_pixel_ratio: float
    theme: str
    indicators: List[str] = Field(default_factory=list)
    render_mode: str  # clean, live, audit, review
    renderer_version: str = "2.0.0"
    semantic_schema_version: str = "1.0.0"
    detector_versions: Dict[str, str] = Field(default_factory=dict)
    configuration_hash: str
    git_commit: str
    dataset_hash: str
    perception_snapshot_hash: str
    scene_graph_hash: str
    image_hash: str
    generation_timestamp: str
