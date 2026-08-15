from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional, List
from enum import Enum
from pydantic import BaseModel, Field, field_validator

def enforce_tz_aware(cls, v):
    if isinstance(v, datetime) and v.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return v

class IncidentType(str, Enum):
    MISMATCH = "mismatch"
    GAP = "gap"
    DUPLICATE = "duplicate"
    INCOMPLETE = "incomplete"

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntegrityState(str, Enum):
    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"

class Instrument(BaseModel):
    venue: str
    symbol: str
    market_type: str  # spot, perpetual, futures, cfd
    base_asset: str
    quote_asset: str
    tick_size: Decimal
    lot_size: Decimal

class RawTrade(BaseModel):
    venue: str
    instrument: str
    market_type: str
    symbol: str
    base_asset: str
    quote_asset: str
    event_time: datetime
    receive_time: datetime
    sequence_id: int
    price: Decimal
    quantity: Decimal
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    trade_side: str  # buyer_maker, seller_maker
    data_source: str
    connection_id: str
    event_kind: Literal["trade"] = "trade"
    trade_id: Optional[str] = None
    buyer_order_id: Optional[str] = None
    seller_order_id: Optional[str] = None
    is_buyer_maker: Optional[bool] = None
    source_payload_hash: Optional[str] = None

    @field_validator("event_time", "receive_time", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)


class BookLevel(BaseModel):
    price: Decimal
    quantity: Decimal = Field(ge=0)


class OrderBookDelta(BaseModel):
    """Venue-native L2 delta with explicit sequence boundaries."""

    event_kind: Literal["order_book_delta"] = "order_book_delta"
    venue: str
    instrument: str
    event_time: datetime
    receive_time: datetime
    first_update_id: int
    final_update_id: int
    previous_final_update_id: Optional[int] = None
    bids: List[BookLevel]
    asks: List[BookLevel]
    data_source: str
    connection_id: str
    source_payload_hash: Optional[str] = None

    @field_validator("event_time", "receive_time", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)


class OrderBookSnapshot(BaseModel):
    event_kind: Literal["order_book_snapshot"] = "order_book_snapshot"
    venue: str
    instrument: str
    captured_at: datetime
    last_update_id: int
    bids: List[BookLevel]
    asks: List[BookLevel]
    data_source: str
    source_payload_hash: Optional[str] = None

    @field_validator("captured_at", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)


class DerivativesMarketEvent(BaseModel):
    """Observed derivatives event; interpretation remains downstream."""

    event_kind: Literal["funding", "open_interest", "liquidation"]
    venue: str
    instrument: str
    event_time: datetime
    receive_time: datetime
    sequence_id: Optional[int] = None
    value: Optional[Decimal] = None
    price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    side: Optional[str] = None
    interval: Optional[str] = None
    data_source: str
    connection_id: str
    source_payload_hash: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_time", "receive_time", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)


class SequenceIntegrityCertificate(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    venue: str
    instrument: str
    stream_kind: str
    state: IntegrityState
    checked_at: datetime
    snapshot_sequence: Optional[int] = None
    first_sequence: Optional[int] = None
    last_sequence: Optional[int] = None
    event_count: int = 0
    gap_count: int = 0
    duplicate_count: int = 0
    out_of_order_count: int = 0
    resynchronization_required: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    source_batch_sha256: Optional[str] = None

    @field_validator("checked_at", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)

class Candle(BaseModel):
    venue: str
    instrument: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int
    is_closed: bool
    is_complete: bool
    contains_gap: bool
    source_event_start: Optional[datetime] = None
    source_event_end: Optional[datetime] = None

    @field_validator("open_time", "close_time", "source_event_start", "source_event_end", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)

class DataQualityIncident(BaseModel):
    incident_id: str
    instrument: str
    timeframe: str
    incident_type: IncidentType
    severity: Severity
    details: str
    detected_at: datetime
    
    @field_validator("detected_at", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)

class CandleReconciliation(BaseModel):
    open_time: datetime
    status: str  # exact, mismatch, missing
    internal_candle: Optional[Candle] = None
    venue_candle: Optional[Candle] = None
    discrepancy_details: Optional[str] = None
    
    @field_validator("open_time", mode="after")
    @classmethod
    def check_tz(cls, v): return enforce_tz_aware(cls, v)
