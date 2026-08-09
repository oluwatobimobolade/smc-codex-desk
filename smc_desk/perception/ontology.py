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
    scale_name: Optional[Literal["local", "internal", "external"]] = None
    pivot_index: Optional[int] = None
    prominence_price: Optional[Decimal] = None


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
    structure_scope: Literal["internal", "external"] = "external"
    protected_swing_id: Optional[str] = None
    last_bos_swing_id: Optional[str] = None
    broke_protected_swing: bool = False
    valid_choch: bool = False

    # -- break-candle lineage (WP-SMC-11, audit F2) --------------------------
    # A break can be probed by one candle and confirmed by a later one. The
    # fields above (candle_body_ratio, price_low/high on the object) describe
    # the PROBE candle, because that is when the object is created. Scoring
    # displacement from those while reading body_close_penetration from the
    # confirming candle mixes two different candles into one measurement --
    # 35 of 178 BTCUSDT breaks and 41 of 144 SOLUSDT breaks take that path.
    # These fields keep the two candles distinct so a consumer can score the
    # confirming impulse on its own geometry.
    probe_candle_id: Optional[str] = None
    body_close_candle_id: Optional[str] = None
    is_delayed_confirmation: bool = False
    confirmation_candle_body_ratio: Optional[float] = None
    confirmation_candle_range: Optional[Decimal] = None
    confirmation_body_size: Optional[Decimal] = None
    # How many confirmed structural levels this candle closed through. A
    # decisive collapse takes out several at once; recording the count keeps
    # that magnitude visible without emitting one break object per level.
    levels_broken_by_candle: int = 0


class FairValueGapEvidence(SMCObjectEvidence):
    gap_size_ticks: int
    gap_size_bps: float
    atr_ratio: float
    is_mitigated_on_creation: bool
    origin_break_id: Optional[str] = None
    poi_grade: bool = False
    location_context: Optional[str] = None


class LiquidityLevelEvidence(SMCObjectEvidence):
    constituent_swing_ids: List[str]
    max_deviation_ticks: int
    level_kind: Literal["swing_high", "swing_low", "equal_highs", "equal_lows"] = "swing_high"
    side: Literal["buy_side", "sell_side"] = "buy_side"
    touch_count: int = 1
    tolerance_bps: float = 0.0


class SweepEvidence(SMCObjectEvidence):
    swept_level_id: str
    sweep_candle_id: str
    penetration_ticks: int
    subsequent_displacement: Optional[float] = None
    swept_price: Optional[Decimal] = None
    reclaim_close: Optional[Decimal] = None
    reclaim_confirmed: bool = True


class OrderBlockEvidence(SMCObjectEvidence):
    originating_fvg_id: Optional[str] = None
    volume_ratio: float
    structure_break_id: Optional[str] = None
    source_candle_id: Optional[str] = None
    body_ratio: float = 0.0
    poi_grade: bool = True


class InducementEvidence(SMCObjectEvidence):
    source_swing_id: str
    related_order_block_id: Optional[str] = None
    related_break_id: Optional[str] = None
    liquidity_side: Literal["buy_side", "sell_side"]
    inducement_taken: bool = False
    sweep_id: Optional[str] = None


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
    metadata: dict[str, Any] = Field(default_factory=dict)
    
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
    break_type: Literal["BOS", "CHOCH"]
    structure_scope: Literal["internal", "external"] = "external"
    
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


class InducementObject(SMCObjectBase):
    object_type: Literal["inducement"] = "inducement"
    evidence: InducementEvidence


SMCObject = Annotated[
    Union[
        SwingObject,
        StructureBreakObject,
        FairValueGapObject,
        LiquidityLevelObject,
        SweepObject,
        OrderBlockObject,
        InducementObject,
    ],
    Field(discriminator="object_type")
]
