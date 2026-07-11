"""Strict role outputs for the AI-first structure laboratory."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Timeframe = Literal["1d", "4h", "1h", "15m", "5m"]
Direction = Literal["bullish", "bearish", "mixed", "neutral", "unclear"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


class VisualObservation(StrictModel):
    visual_id: str
    timeframe: Timeframe
    kind: Literal[
        "candidate_swing_high",
        "candidate_swing_low",
        "candidate_break",
        "wick_probe",
        "displacement",
        "liquidity_cluster",
        "candidate_poi",
        "range_boundary",
        "unclear",
    ]
    direction: Direction = "unclear"
    timestamp: str | None = None
    price: float | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str


class BlindVisualStructureRead(StrictModel):
    schema_id: Literal["blind_visual_structure_read_v1"] = Field("blind_visual_structure_read_v1", alias="schema")
    role: Literal["blind_visual_structure_reader"] = "blind_visual_structure_reader"
    observations: list[VisualObservation]
    timeframe_summaries: dict[Timeframe, str]
    unresolved_visual_questions: list[str]
    abstain: bool = False


class RejectedCandidate(StrictModel):
    evidence_id: str
    reason: str


class CandidateReconciliation(StrictModel):
    schema_id: Literal["candidate_reconciliation_v1"] = Field("candidate_reconciliation_v1", alias="schema")
    role: Literal["deterministic_candidate_reconciler"] = "deterministic_candidate_reconciler"
    accepted_evidence_ids: list[str]
    rejected_candidates: list[RejectedCandidate]
    visual_to_evidence_map: dict[str, list[str]]
    unresolved_conflicts: list[str]
    ambiguity_status: Literal["CLEAR", "MIXED", "INSUFFICIENT_EVIDENCE"]


class AlternativeInterpretation(StrictModel):
    label: str
    evidence_ids: list[str]
    reason: str
    confidence: float = Field(ge=0, le=1)


class CausalStructureEpisode(StrictModel):
    schema_id: Literal["causal_structure_episode_v1"] = Field("causal_structure_episode_v1", alias="schema")
    role: Literal["causal_episode_constructor"] = "causal_episode_constructor"
    controlling_timeframe: Timeframe | None
    parent_external_state: Direction
    child_internal_state: Direction
    active_leg_evidence_ids: list[str]
    protected_point_evidence_ids: list[str]
    event_sequence_evidence_ids: list[str]
    liquidity_evidence_ids: list[str]
    selected_poi_evidence_id: str | None
    causal_story: str
    classification: Literal["CONTINUATION", "PULLBACK", "TRANSITION", "RANGE", "UNCLEAR"]
    confidence: float = Field(ge=0, le=1)
    alternatives: list[AlternativeInterpretation]
    what_would_change_the_read: list[str]


class CriticViolation(StrictModel):
    code: str
    message: str
    contradiction_evidence_ids: list[str]


class StructureCriticReview(StrictModel):
    schema_id: Literal["structure_critic_v1"] = Field("structure_critic_v1", alias="schema")
    role: Literal["adversarial_structure_critic"] = "adversarial_structure_critic"
    verdict: Literal["PASS", "REVISE", "DOWNGRADE"]
    violations: list[CriticViolation]
    required_corrections: list[str]
    promotion_allowed: Literal[False] = False


class AnnotationSelection(StrictModel):
    # WP-0044 stabilization: path_projection is intentionally absent from the
    # AI-selectable set. A path projection draws a forward arrow past the last
    # candle (mild forecast), so it must NOT be an AI-selected object -- that
    # would grant the AI forecasting authority it does not hold. The deterministic
    # conservative composer (annotation_candidate_composer.compose_local_annotation_plan_v2)
    # is the only sanctioned emitter of path_projection, gated on a certified
    # active POI and an official state in PATH_ALLOWED_STATES. The certified
    # evidence resolver (annotation_bridge._resolve_selection) has no branch for
    # it, so the AI schema and the resolver now agree: structure_segment, poi_zone,
    # and liquidity_line are the only AI-selectable object types.
    object_type: Literal["structure_segment", "poi_zone", "liquidity_line"]
    semantic_object_id: str
    timeframe: Timeframe
    label: str
    reason: str
    priority: int = Field(ge=1, le=5)


class SemanticAnnotationPlan(StrictModel):
    schema_id: Literal["semantic_annotation_selection_v1"] = Field("semantic_annotation_selection_v1", alias="schema")
    role: Literal["annotation_planner"] = "annotation_planner"
    selections: list[AnnotationSelection]
    hidden_evidence_ids: list[str]
    clutter_budget: int = Field(ge=0, le=12)
    geometry_source: Literal["certified_evidence_resolver"] = "certified_evidence_resolver"
    trade_box_allowed: Literal[False] = False


class VisualIssue(StrictModel):
    code: str
    message: str
    semantic_object_ids: list[str]


class VisualAnnotationReview(StrictModel):
    schema_id: Literal["visual_annotation_review_v1"] = Field("visual_annotation_review_v1", alias="schema")
    role: Literal["visual_annotation_critic"] = "visual_annotation_critic"
    verdict: Literal["PASS", "CLEANUP", "DOWNGRADE"]
    issues: list[VisualIssue]
    cleanup_requests: list[str]
    visual_inspection_basis: Literal["rendered_images", "render_manifest_only", "not_available"] = "not_available"
    reviewed_render_manifest_sha256: str | None = None
    reviewed_image_sha256: list[str] = Field(default_factory=list)
    promotion_allowed: Literal[False] = False


ROLE_SCHEMAS = {
    "blind_visual_structure_reader": BlindVisualStructureRead,
    "deterministic_candidate_reconciler": CandidateReconciliation,
    "causal_episode_constructor": CausalStructureEpisode,
    "adversarial_structure_critic": StructureCriticReview,
    "annotation_planner": SemanticAnnotationPlan,
    "visual_annotation_critic": VisualAnnotationReview,
}
