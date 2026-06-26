"""
Annotation Schema for Human Adjudication (Phase 2).

All human and AI annotations must conform to this schema.
This ensures type-safe ingestion and prevents malformed labels.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class StructuralAnnotation(BaseModel):
    """A single annotation of a structural object on a chart."""
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., description="Unique identifier for the case being annotated")
    reviewer_id: str = Field(..., description="Unique reviewer identifier (blinded during evaluation)")
    primitive: str = Field(
        ...,
        description="The structural primitive type",
        examples=["swing_high", "swing_low", "bos", "choch", "fvg_bullish", "fvg_bearish", "sweep"]
    )
    direction: str = Field(
        ...,
        description="Structural direction",
        examples=["bullish", "bearish"]
    )
    scope: str = Field(
        default="unspecified",
        description="Structural scope",
        examples=["local", "internal", "external", "unspecified"]
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of the structural event (pivot candle open_time)"
    )
    price: float = Field(..., description="Price level of the structural event", gt=0)
    confidence: float = Field(
        default=1.0,
        description="Reviewer confidence in this annotation (0.0 to 1.0)",
        ge=0.0,
        le=1.0
    )
    notes: str = Field(default="", description="Optional reviewer notes or justification")
    is_ambiguous: bool = Field(default=False, description="Whether the reviewer considers this ambiguous")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Ensure timestamp is valid ISO 8601."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")
        return v


class CaseAnnotationBundle(BaseModel):
    """All annotations from a single reviewer for a single case."""
    model_config = ConfigDict(extra="forbid")

    case_id: str
    reviewer_id: str
    annotations: List[StructuralAnnotation]
    completed_at: Optional[str] = None
    reviewer_notes: str = ""


def load_annotations_from_directory(directory: str | Path) -> List[CaseAnnotationBundle]:
    """Load all annotation JSON files from a directory.
    
    Each file should contain a JSON object conforming to CaseAnnotationBundle.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        raise FileNotFoundError(f"Annotation directory not found: {directory}")

    bundles = []
    for json_file in sorted(dir_path.glob("*.json")):
        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        bundle = CaseAnnotationBundle(**data)
        bundles.append(bundle)
    return bundles
