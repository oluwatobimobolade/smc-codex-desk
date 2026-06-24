from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Optional, List, Union, Any

from pydantic import BaseModel, Field, ConfigDict, field_validator

def enforce_tz_aware(cls, v):
    if isinstance(v, datetime) and v.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return v

class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ConfirmationStatus(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ActivityStatus(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    TERMINAL = "terminal"


class MitigationStatus(str, Enum):
    UNTOUCHED = "untouched"
    PARTIAL = "partial"
    FULL = "full"


class TerminalReason(str, Enum):
    NONE = "none"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    CONSUMED = "consumed"


class SMCObjectEvidence(BaseModel):
    """Base class for object-specific evidence."""
    pass


class SwingEvidence(SMCObjectEvidence):
    bars_left: int
    bars_right: int
    prominence_atr_pct: float
    is_external: bool
    # Will add displacement tracking metrics here later, as updates


class StructureBreakEvidence(SMCObjectEvidence):
    broken_swing_id: str
    broken_price: Decimal
    wick_penetration: Decimal
    body_close_penetration: Decimal
    penetration_ticks: int
    penetration_atr_pct: float
    candle_body_ratio: float
    displacement_strength: float
    is_internal: bool
    is_unconfirmed_probe: bool


class FairValueGapEvidence(SMCObjectEvidence):
    gap_size_ticks: int
    gap_size_bps: float
    atr_ratio: float
    is_mitigated_on_creation: bool


class LiquidityLevelEvidence(SMCObjectEvidence):
    constituent_swing_ids: List[str]
    max_deviation_ticks: int


class SweepEvidence(SMCObjectEvidence):
    swept_level_id: str
    sweep_candle_id: str
    penetration_ticks: int
    subsequent_displacement: Optional[float] = None


class OrderBlockEvidence(SMCObjectEvidence):
    originating_fvg_id: str
    volume_ratio: float


class SMCObjectBase(BaseModel):
    """Base class for all SMC Objects enforcing common causality and provenance."""
    model_config = ConfigDict(use_enum_values=True)
    object_id: str
    venue: str
    instrument: str
    timeframe: str
    
    # As-of Causality Timestamps
    # The actual market time this object refers to (e.g., the swing high time)
    pivot_time: datetime
    # The time this object was first proposed as a candidate
    candidate_at: datetime
    # The time this object was confirmed based on rules (e.g., pivot_window closed)
    confirmed_at: Optional[datetime] = None
    # The latest market time for which this object's state has been updated
    current_as_of: datetime
    
    # Status Lifecycle
    confirmation_status: ConfirmationStatus = ConfirmationStatus.CANDIDATE
    activity_status: ActivityStatus = ActivityStatus.INACTIVE
    mitigation_status: MitigationStatus = MitigationStatus.UNTOUCHED
    terminal_reason: TerminalReason = TerminalReason.NONE
    
    # Optional parent linking (e.g., HTF graph)
    parent_structure_id: Optional[str] = None
    
    # System Metadata
    schema_version: str = "1.0.0"
    detector_version: str
    configuration_hash: str
    source_candle_ids: List[str]
    last_updated_at: datetime  # System clock time when the object was last modified
    events: List[Any] = Field(default_factory=list) # SMCEvent objects
    
    confidence: float
    direction: Direction
    price_low: Decimal
    price_high: Decimal
    
    @field_validator("pivot_time", "candidate_at", "confirmed_at", "current_as_of", "last_updated_at", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)


class SwingObject(SMCObjectBase):
    object_type: Literal["swing"] = "swing"
    evidence: SwingEvidence


class StructureBreakObject(SMCObjectBase):
    object_type: Literal["structure_break"] = "structure_break"
    evidence: StructureBreakEvidence
    
    # CHoCH vs BOS can be inferred or explicitly flagged
    is_choch: bool


class FairValueGapObject(SMCObjectBase):
    object_type: Literal["fvg"] = "fvg"
    evidence: FairValueGapEvidence
    mitigated_price: Optional[Decimal] = None
    mitigation_percent: float = 0.0


class LiquidityLevelObject(SMCObjectBase):
    object_type: Literal["liquidity_level"] = "liquidity_level"
    evidence: LiquidityLevelEvidence


class SweepObject(SMCObjectBase):
    object_type: Literal["sweep"] = "sweep"
    evidence: SweepEvidence


class OrderBlockObject(SMCObjectBase):
    object_type: Literal["order_block"] = "order_block"
    evidence: OrderBlockEvidence


SMCObject = Annotated[
    Union[
        SwingObject,
        StructureBreakObject,
        FairValueGapObject,
        LiquidityLevelObject,
        SweepObject,
        OrderBlockObject
    ],
    Field(discriminator="object_type")
]
