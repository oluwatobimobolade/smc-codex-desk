from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, field_validator

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

    @field_validator("event_time", "receive_time", mode="after")
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

