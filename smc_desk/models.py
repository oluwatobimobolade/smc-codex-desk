from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["bullish", "bearish", "neutral"]
ZoneKind = Literal["fvg", "order_block", "liquidity", "range", "entry", "target", "invalidation", "other"]
EventLabel = Literal["BOS", "CHoCH", "Liquidity Sweep", "Range Break", "Inducement"]
ZoneStatus = Literal["fresh", "partial", "mitigated", "unknown"]
EntryType = Literal["aggressive_limit", "confirmation", "no_trade"]
SetupGrade = Literal["A+", "A", "B", "C"]
Verdict = Literal["Execute", "Watch", "Watch Retrace", "Watch HTF POI", "Pass"]
EventStrength = Literal["weak", "valid", "strong"]
StructureScope = Literal["internal", "swing", "external", "unknown"]


class SwingPoint(BaseModel):
    kind: Literal["high", "low"]
    index: int
    timestamp: str
    price: float


class Zone(BaseModel):
    label: str
    kind: ZoneKind
    direction: Direction
    low: float
    high: float
    start_index: int | None = None
    end_index: int | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    status: ZoneStatus = "unknown"
    touched_count: int | None = None
    mitigation_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    source_event_index: int | None = None
    reason: str


class HigherTimeframePoi(BaseModel):
    """A higher-timeframe area to monitor, never an executable order by itself."""

    timeframe: Literal["1h", "4h"]
    zone: Zone
    state: Literal["mapped", "approaching", "at_poi"]
    distance_atr: float = Field(ge=0.0)
    age_bars: int = Field(ge=0)
    rank: float = Field(ge=0.0, le=1.0)
    approach_confirmed: bool = False


class StructureEvent(BaseModel):
    label: EventLabel
    direction: Direction
    index: int
    timestamp: str
    price: float
    reason: str
    structure_scope: StructureScope = "swing"
    broken_level: float | None = None
    swept_level: float | None = None
    displacement_score: float = Field(default=0.0, ge=0.0)
    strength: EventStrength = "valid"


class TradePlan(BaseModel):
    direction: Direction
    entry_type: EntryType = "no_trade"
    setup_grade: SetupGrade = "C"
    verdict: Verdict = "Pass"
    risk_pct: float = Field(default=0.0, ge=0.0, le=2.0)
    entry_low: float | None = None
    entry_high: float | None = None
    structural_invalidation: float | None = None
    execution_invalidation: float | None = None
    invalidation: float | None = None
    stop_buffer: float | None = None
    stop_buffer_atr: float | None = None
    stop_quality: str = "unknown"
    targets: list[float] = Field(default_factory=list)
    risk_reward: float | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    confluence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    liquidity_target: float | None = None
    selected_poi: Zone | None = None
    selected_htf_poi: HigherTimeframePoi | None = None
    checklist: dict[str, bool] = Field(default_factory=dict)
    thesis: str
    conditions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    symbol: str
    timeframe: str
    input_type: Literal["ohlcv", "screenshot", "hybrid"]
    generated_at: str
    bias_hint: str | None = None
    notes: str | None = None
    metrics: dict[str, float | int | str | None]
    session_context: dict[str, float | int | str | None]
    swings: list[SwingPoint] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    events: list[StructureEvent] = Field(default_factory=list)
    trade_plan: TradePlan
    bullish_plan: TradePlan | None = None
    bearish_plan: TradePlan | None = None
    limitations: list[str] = Field(default_factory=list)
