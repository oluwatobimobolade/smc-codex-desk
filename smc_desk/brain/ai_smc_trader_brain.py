"""Strict AI SMC trader brain schema.

This module does not call a model provider. It defines the prompt contract,
required reasoning order, and strict JSON schema for any model or human-AI
workspace that wants to act as the discretionary SMC reasoning step.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


REASONING_ORDER: list[str] = [
    "daily_context",
    "4h_context",
    "1h_context",
    "active_range",
    "premium_discount",
    "obvious_liquidity",
    "swept_liquidity",
    "displacement_quality",
    "active_poi",
    "entry_model",
    "entry_readiness",
    "structural_invalidation",
    "model_completion_liquidity_target",
    "rr_minimum_three",
    "final_state",
]

OFFICIAL_STATES = {
    "TRADE_PLAN_READY",
    "WAIT_FOR_POI",
    "WAIT_FOR_RETRACE_TO_SUPPLY",
    "WAIT_FOR_RETRACE_TO_DEMAND",
    "POI_TOUCHED_AWAIT_CONFIRMATION",
    "WATCH_ONLY",
    "REVIEW_REQUIRED",
    "MOVE_STARTED_NOT_CHASEABLE",
    "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY",
    "MISSED_TRADE_NO_CHASE",
    "INDUCEMENT_RISK",
    "INVALIDATED_REMAP",
    "NO_TRADE",
    "THESIS_ONLY",
}

MINIMUM_RR = 3.0


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BiasSummary(StrictModel):
    daily: str
    four_hour: str = Field(alias="4h")
    one_hour: str = Field(alias="1h")
    final_bias: Literal["bullish", "bearish", "neutral", "mixed"]
    evidence: list[str] = Field(default_factory=list)


class ActiveRange(StrictModel):
    timeframe: str
    high: float | None = None
    low: float | None = None
    equilibrium: float | None = None
    price_location: Literal["premium", "discount", "equilibrium", "unknown"] = "unknown"
    source: str | None = None
    range_id: str | None = None
    protected_high: float | None = None
    protected_low: float | None = None
    width_atr: float | None = None
    max_allowed_width_atr: float | None = None
    evidence_object_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class LiquidityReference(StrictModel):
    liquidity_id: str | None = None
    timeframe: str | None = None
    side: Literal["buy_side", "sell_side", "both", "unknown"] = "unknown"
    price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    label: str | None = None
    evidence_object_ids: list[str] = Field(default_factory=list)
    status: Literal[
        "fresh_untaken_liquidity",
        "prior_swept_liquidity",
        "re_sweep_objective",
        "range_low_reference",
        "range_high_reference",
        "below_low_external_liquidity",
        "above_high_external_liquidity",
        "model_completion_reference",
        "unknown"
    ] = "unknown"
    target_role: str | None = None
    true_fresh_liquidity_location: str | None = None


class LiquidityStory(StrictModel):
    obvious_liquidity: list[LiquidityReference] = Field(default_factory=list)
    swept_liquidity: list[LiquidityReference] = Field(default_factory=list)
    unswept_liquidity: list[LiquidityReference] = Field(default_factory=list)
    narrative: str


class DisplacementAssessment(StrictModel):
    direction: Literal["bullish", "bearish", "none", "mixed"]
    quality: Literal["none", "weak", "clean", "strong", "review"]
    structure_broken: bool = False
    evidence_object_ids: list[str] = Field(default_factory=list)
    summary: str


class ActivePOI(StrictModel):
    poi_id: str | None = None
    timeframe: str | None = None
    kind: str | None = None
    direction: Literal["bullish", "bearish", "neutral", "unknown"] = "unknown"
    price_low: float | None = None
    price_high: float | None = None
    freshness: str | None = None
    evidence_object_ids: list[str] = Field(default_factory=list)
    summary: str

    @model_validator(mode="after")
    def _ordered_zone(self) -> "ActivePOI":
        if self.price_low is not None and self.price_high is not None and self.price_low > self.price_high:
            raise ValueError("active_poi.price_low cannot be above price_high")
        return self


class EntryPlan(StrictModel):
    entry_ready: bool
    entry_timeframe: str | None = None
    refinement_timeframe: str | None = None
    entry_price: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    signal_type: str | None = None
    required_confirmation: list[str] = Field(default_factory=list)
    evidence_object_ids: list[str] = Field(default_factory=list)
    entry_anchor: str | None = None
    mapped_entry_price: float | None = None
    summary: str

    @model_validator(mode="after")
    def _ordered_entry_zone(self) -> "EntryPlan":
        if self.entry_zone_low is not None and self.entry_zone_high is not None and self.entry_zone_low > self.entry_zone_high:
            raise ValueError("entry_zone_low cannot be above entry_zone_high")
        return self


class StopLossPlan(StrictModel):
    stop_price: float | None = None
    structural_invalidation_price: float | None = None
    source: str | None = None
    buffer_notes: str | None = None
    evidence_object_ids: list[str] = Field(default_factory=list)
    stop_anchor: str | None = None
    mapped_stop_price: float | None = None
    summary: str


class TargetLevel(StrictModel):
    price: float | None = None
    label: str
    timeframe: str | None = None
    reason: str
    evidence_object_ids: list[str] = Field(default_factory=list)
    target_anchor: str | None = None
    mapped_target_price: float | None = None


class TargetPlan(StrictModel):
    targets: list[TargetLevel] = Field(default_factory=list)
    model_completion_liquidity_id: str | None = None
    summary: str


class RRStatus(StrictModel):
    rr: float | None = None
    minimum_rr: float = MINIMUM_RR
    pass_rr: bool = False
    notes: str

    @field_validator("minimum_rr")
    @classmethod
    def _minimum_is_locked(cls, value: float) -> float:
        if float(value) != MINIMUM_RR:
            raise ValueError("minimum_rr must be locked to 3.0")
        return value


class InvalidationPlan(StrictModel):
    invalidation_price: float | None = None
    condition: str
    source: str | None = None
    evidence_object_ids: list[str] = Field(default_factory=list)
    invalidation_anchor: str | None = None
    mapped_invalidation_price: float | None = None


class AnnotationLabel(StrictModel):
    text: str
    kind: Literal[
        "context",
        "liquidity",
        "sweep",
        "displacement",
        "poi",
        "entry",
        "stop",
        "target",
        "invalidation",
        "state",
        "structure",
        "bos",
        "choch",
        "idm",
        "fvg",
        "order_block",
    ]
    timeframe: str | None = None
    price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    importance: int = Field(default=2, ge=1, le=3)


class AnnotationLevel(StrictModel):
    label: str
    kind: Literal[
        "liquidity",
        "poi",
        "entry",
        "stop",
        "target",
        "invalidation",
        "structure",
        "bos",
        "choch",
        "idm",
        "fvg",
        "order_block",
    ]
    price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    timeframe: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    line_style: Literal["solid", "dashed", "dotted"] | None = None


class AnnotationPlan(StrictModel):
    chart_template: Literal["context_chart", "watch_chart", "trade_plan_chart", "review_chart", "debug_chart"]
    show_trade_box: bool = False
    labels: list[AnnotationLabel] = Field(default_factory=list)
    levels: list[AnnotationLevel] = Field(default_factory=list)
    reasoning_order: list[str]


class SelfReview(StrictModel):
    active_range_check: Literal["passed", "failed", "not_applicable"] = "not_applicable"
    poi_check: Literal["passed", "failed", "not_applicable"] = "not_applicable"
    annotation_check: Literal["passed", "failed", "not_applicable"] = "not_applicable"
    refusal_check: Literal["passed", "failed", "not_applicable"] = "not_applicable"
    corrections_made: list[str] = Field(default_factory=list)
    remaining_uncertainties: list[str] = Field(default_factory=list)


class AISMCDecision(StrictModel):
    schema_: Literal["ai_smc_trader_decision_v1"] = Field(default="ai_smc_trader_decision_v1", alias="schema")
    symbol: str
    official_state: str
    setup_grade: str
    direction: Literal["bullish", "bearish", "neutral", "mixed"]
    setup_model: str
    bias_summary: BiasSummary
    active_range: ActiveRange
    liquidity_story: LiquidityStory
    displacement_assessment: DisplacementAssessment
    active_poi: ActivePOI
    entry_plan: EntryPlan
    stop_loss_plan: StopLossPlan
    target_plan: TargetPlan
    rr_status: RRStatus
    invalidation: InvalidationPlan
    annotation_plan: AnnotationPlan
    self_review: SelfReview = Field(default_factory=SelfReview)
    final_thesis: str

    @field_validator("official_state")
    @classmethod
    def _known_state(cls, value: str) -> str:
        if value not in OFFICIAL_STATES:
            raise ValueError(f"Unsupported official_state: {value}")
        return value

    @model_validator(mode="after")
    def _state_matches_chart(self) -> "AISMCDecision":
        if self.official_state == "TRADE_PLAN_READY":
            if self.annotation_plan.chart_template != "trade_plan_chart":
                raise ValueError("TRADE_PLAN_READY requires trade_plan_chart")
        elif self.annotation_plan.chart_template == "trade_plan_chart":
            raise ValueError("trade_plan_chart requires TRADE_PLAN_READY")
        return self

    def to_official_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def assert_ai_reasoning_order(decision: AISMCDecision) -> None:
    if decision.annotation_plan.reasoning_order != REASONING_ORDER:
        raise ValueError("AI SMC decision did not follow the required reasoning order.")


def parse_ai_smc_decision(payload: str | bytes | Mapping[str, Any]) -> AISMCDecision:
    if isinstance(payload, bytes):
        raw: Any = json.loads(payload.decode("utf-8"))
    elif isinstance(payload, str):
        raw = json.loads(payload)
    else:
        raw = dict(payload)
    decision = AISMCDecision.model_validate(raw)
    assert_ai_reasoning_order(decision)
    return decision


def build_ai_smc_prompt(evidence_pack: Mapping[str, Any]) -> str:
    """Build the local prompt contract for a model or manual AI workspace."""
    from smc_desk.brain.prompt_system.prompt_builder import build_layered_ai_smc_prompt

    return build_layered_ai_smc_prompt(evidence_pack)


class AISMCTraderBrain:
    """Adapter for a local or injected reasoning backend.

    completion_fn receives the prompt text and must return the strict JSON
    payload. The class exists to make the boundary testable without any API.
    """

    def __init__(self, completion_fn: Callable[[str], str | Mapping[str, Any]] | None = None):
        self.completion_fn = completion_fn

    def build_prompt(self, evidence_pack: Mapping[str, Any]) -> str:
        return build_ai_smc_prompt(evidence_pack)

    def decide(self, evidence_pack: Mapping[str, Any]) -> AISMCDecision:
        if self.completion_fn is None:
            raise RuntimeError("AISMCTraderBrain requires an injected completion_fn; no API is owned here.")
        payload = self.completion_fn(self.build_prompt(evidence_pack))
        return parse_ai_smc_decision(payload)
