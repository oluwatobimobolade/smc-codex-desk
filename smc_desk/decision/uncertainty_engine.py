"""Uncertainty scoring for conservative colleague decisions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UncertaintyAssessment:
    signal_confidence: float
    structure_confidence: float
    execution_confidence: float
    signal_stability_score: float
    final_verdict: str
    pipeline_confidence: float
    analysis_confidence: float
    context_confidence: float
    poi_confidence: float
    visual_confidence: float | None = None
    breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def blocks_signal(self) -> bool:
        return self.signal_confidence < 0.60

    def to_dict(self) -> dict:
        return {
            "signal_confidence": round(self.signal_confidence, 4),
            "structure_confidence": round(self.structure_confidence, 4),
            "execution_confidence": round(self.execution_confidence, 4),
            "signal_stability_score": round(self.signal_stability_score, 4),
            "pipeline_confidence": round(self.pipeline_confidence, 4),
            "analysis_confidence": round(self.analysis_confidence, 4),
            "context_confidence": round(self.context_confidence, 4),
            "poi_confidence": round(self.poi_confidence, 4),
            "visual_confidence": None if self.visual_confidence is None else round(self.visual_confidence, 4),
            "final_confidence_label": _confidence_label(self.analysis_confidence),
            "final_verdict": self.final_verdict,
            "blocks_signal": self.blocks_signal,
            "breakdown": {key: round(value, 4) for key, value in self.breakdown.items()},
            "reasons": list(self.reasons),
        }


def score_uncertainty(
    *,
    truth_report: Any,
    regime_assessment: Any,
    contradiction_resolution: Any,
    perception_by_tf: dict[str, Any] | None = None,
) -> UncertaintyAssessment:
    """Score signal validity, stability, and execution confidence."""
    reasons: list[str] = []
    truth_score = 1.0 if getattr(truth_report, "ok", False) else 0.0
    if truth_score == 0.0:
        reasons.append("market_truth_failed")

    regime_confidence = float(getattr(regime_assessment, "confidence", 0.0) or 0.0)
    if regime_confidence < 0.60:
        reasons.append("regime_confidence_below_threshold")

    contradiction_score = float(getattr(contradiction_resolution, "contradiction_score", 1.0) or 0.0)
    contradiction_outcome = getattr(contradiction_resolution, "outcome", "WAIT")
    if contradiction_outcome == "ALIGN":
        contradiction_confidence = max(0.0, 1.0 - contradiction_score)
    elif contradiction_outcome == "WAIT":
        contradiction_confidence = max(0.0, 0.45 - contradiction_score * 0.5)
        reasons.append("contradiction_resolver_wait")
    else:
        contradiction_confidence = 0.0
        reasons.append("contradiction_invalidates_setup")

    structure_confidence = _structure_confidence(perception_by_tf or {})
    execution_confidence = min(regime_confidence, contradiction_confidence)
    signal_stability = _clamp(
        truth_score * 0.30
        + regime_confidence * 0.25
        + contradiction_confidence * 0.30
        + structure_confidence * 0.15
    )
    signal_confidence = _clamp(
        truth_score * 0.35
        + structure_confidence * 0.20
        + execution_confidence * 0.25
        + signal_stability * 0.20
    )
    pipeline_confidence = _clamp(truth_score * 0.50 + regime_confidence * 0.20 + structure_confidence * 0.30)
    context_confidence = _clamp(truth_score * 0.35 + regime_confidence * 0.25 + contradiction_confidence * 0.40)
    poi_confidence = 0.0
    analysis_confidence = _clamp(context_confidence * 0.40 + structure_confidence * 0.35 + poi_confidence * 0.25)

    if signal_confidence < 0.60:
        final_verdict = "NO_SIGNAL"
    elif signal_confidence < 0.75:
        final_verdict = "WEAK_VALIDATION"
    else:
        final_verdict = "OBSERVATION_VALID"

    return UncertaintyAssessment(
        signal_confidence=signal_confidence,
        structure_confidence=structure_confidence,
        execution_confidence=execution_confidence,
        signal_stability_score=signal_stability,
        final_verdict=final_verdict,
        pipeline_confidence=pipeline_confidence,
        analysis_confidence=analysis_confidence,
        context_confidence=context_confidence,
        poi_confidence=poi_confidence,
        visual_confidence=None,
        breakdown={
            "truth": truth_score,
            "regime": regime_confidence,
            "contradiction": contradiction_confidence,
            "structure": structure_confidence,
            "pipeline_confidence": pipeline_confidence,
            "analysis_confidence": analysis_confidence,
            "context_confidence": context_confidence,
            "poi_confidence": poi_confidence,
        },
        reasons=reasons,
    )


def _structure_confidence(perception_by_tf: dict[str, Any]) -> float:
    if not perception_by_tf:
        return 0.0
    scores: list[float] = []
    for snapshot in perception_by_tf.values():
        if isinstance(snapshot, dict):
            swings = snapshot.get("swings", {}) or {}
            breaks = snapshot.get("structure_breaks", []) or []
            fvgs = snapshot.get("fvgs", []) or []
        else:
            swings = getattr(snapshot, "swings", {}) or {}
            breaks = getattr(snapshot, "structure_breaks", []) or []
            fvgs = getattr(snapshot, "fvgs", []) or []
        swing_count = sum(len(v) for v in swings.values()) if isinstance(swings, dict) else len(swings)
        score = 0.35
        if swing_count:
            score += 0.20
        if breaks:
            score += 0.25
        if fvgs:
            score += 0.10
        scores.append(_clamp(score))
    return sum(scores) / len(scores)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _confidence_label(value: float) -> str:
    if value < 0.35:
        return "VERY_LOW_ANALYSIS_CONFIDENCE"
    if value < 0.55:
        return "LOW_ANALYSIS_CONFIDENCE"
    if value < 0.75:
        return "MODERATE_ANALYSIS_CONFIDENCE"
    return "HIGH_ANALYSIS_CONFIDENCE"
