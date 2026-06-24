from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Any

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

    @model_validator(mode="after")
    def validate_normalized_bounds(self) -> "BoundingBox":
        for val, name in [(self.x1, "x1"), (self.y1, "y1"), (self.x2, "x2"), (self.y2, "y2")]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be between 0.0 and 1.0 (normalized), got {val}")
        return self

class VisionObject(BaseModel):
    vision_object_id: str
    object_type: str  # swing_high, swing_low, protected_high, protected_low, bos, choch, wick_probe, bullish_fvg, bearish_fvg
    direction: str  # bullish, bearish
    scope: Optional[str] = None  # local, internal, external
    confidence: float
    approximate_pixel_region: Optional[BoundingBox] = None
    approximate_candle_region: Optional[Tuple[int, int]] = None
    approximate_price_region: Optional[Tuple[float, float]] = None
    evidence_description: str
    ambiguous: bool
    ambiguity_reason: Optional[str] = None
    
    # Store dimensions, raw box, normalised box, and transformation history
    original_image_width: Optional[int] = None
    original_image_height: Optional[int] = None
    raw_pixel_box: Optional[Tuple[int, int, int, int]] = None
    normalised_box: Optional[BoundingBox] = None
    transformation_history: List[Dict[str, Any]] = Field(default_factory=list)


class MetadataRead(BaseModel):
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    venue: Optional[str] = None
    latest_visible_timestamp: Optional[str] = None
    scale_type: Optional[str] = None  # linear, log
    price_labels_legible: bool = True
    time_labels_legible: bool = True
    is_cropped: bool = False
    indicators_obscure_price: bool = False

class AmbiguityInfo(BaseModel):
    type: str
    reason: str

class VisionResponse(BaseModel):
    response_id: str
    case_id: Optional[str] = None
    provider: str
    model: str
    prompt_version: str
    schema_version: str = "1.0.0"
    chart_valid: bool
    metadata_read: MetadataRead
    visible_context: Dict[str, Any] = Field(default_factory=dict)
    structure_read: str  # bullish, bearish, ranging, transitional, ambiguous, insufficient_context
    detected_objects: List[VisionObject] = Field(default_factory=list)
    ambiguities: List[AmbiguityInfo] = Field(default_factory=list)
    missing_context: List[str] = Field(default_factory=list)
    abstain: bool = False
    abstention_reason: Optional[str] = None
    overall_confidence: float
    created_at: datetime
