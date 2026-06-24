"""Perception panel — multiple independent 'experts' label the same chart.

Per CANONICAL_SMC_THESIS.md, an object is trustworthy only when independent viewpoints
agree, and confidence must be *earned* (calibrated), not asserted. This module provides
the first, dependency-free expert ensemble: the deterministic engine run at many slightly
**perturbed thresholds**. Each parameterization is a viewpoint.

  - An object detected across MOST perturbations is *robust* -> high confidence.
  - An object that appears at only one threshold setting is *fragile* -> low confidence /
    abstain. (This is exactly how noise-induced BOS/sweeps get filtered: they are
    threshold-fragile, while real displacement structure is not.)

Independent vision / numeric-LLM experts plug into the same ``Labeler`` contract later;
their object lists feed the identical consensus layer. The robustness ensemble is not a
substitute for an independent modality — it measures *stability*, which is a necessary
(not sufficient) condition for a correct call, and it gives us calibrated confidence today.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import analyze_dataframe
from .models import AnalysisResult
from .perception_legacy import PerceptionAnnotation, greedy_match_annotations
from .rules import RuleConfig

_EVENT_MAP = {"BOS": "bos", "CHoCH": "choch", "Liquidity Sweep": "liquidity_sweep"}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h = df["high"].to_numpy(float); l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    if len(c) == 0:
        return 1e-9
    pc = np.empty_like(c); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return max(float(tr[-n:].mean()), 1e-9)


def _grade(s: float) -> str:
    """Significance score -> earned confidence. Below 'low' the panel abstains."""
    return "high" if s >= 0.60 else "medium" if s >= 0.35 else "low"


# Heuristic salience thresholds informed by a small anchor review (4 symbols x regimes,
# scale $2->$20k). They improve annotation readability but are *not* calibrated accuracy
# claims; only the adjudicated gold-set evaluator may make those claims. The reviewed
# salient objects were swing-scope with significance >= 0.90, while internal-scope
# whipsaws were over-produced. "high" therefore requires BOTH.
HIGH_SIG = 0.90
MED_SIG = 0.55


def _dealing_range(result: AnalysisResult, atr: float) -> float:
    rl = float(result.metrics.get("range_low") or 0.0)
    rh = float(result.metrics.get("range_high") or 0.0)
    return max(rh - rl, 3.0 * atr, 1e-9)


def _event_significance(event, df: pd.DataFrame, atr: float, dr: float) -> float:
    """Thesis significance for a structure/sweep event: magnitude vs dealing range,
    swing-vs-internal scope, displacement strength."""
    i = int(event.index)
    cr = float(df["high"].iat[i] - df["low"].iat[i]) if 0 <= i < len(df) else atr
    mag = _clip01((cr / dr) / 0.12)                                   # candle range >=12% of range = max
    scope = 1.0 if event.structure_scope in {"swing", "external"} else 0.45
    strength = {"strong": 1.0, "valid": 0.6, "weak": 0.2}.get(event.strength, 0.5)
    disp = _clip01(float(event.displacement_score) / 3.0)
    return 0.40 * mag + 0.25 * scope + 0.20 * strength + 0.15 * disp


def _zone_significance(zone, atr: float, dr: float) -> float:
    """Thesis significance for a zone: width vs dealing range, freshness, score, touches."""
    wfrac = _clip01((float(zone.high - zone.low) / dr) / 0.08)
    fresh = {"fresh": 1.0, "partial": 0.6, "mitigated": 0.2}.get(zone.status or "", 0.5)
    score = _clip01(float(zone.score or 0.0))
    if zone.kind == "liquidity":
        touch = _clip01((zone.touched_count or 0) / 4.0)
        return 0.30 * wfrac + 0.25 * touch + 0.25 * fresh + 0.20 * score
    return 0.35 * wfrac + 0.30 * fresh + 0.35 * score


def analysis_to_objects(
    result: AnalysisResult, timeframe: str = "15m", df: pd.DataFrame | None = None
) -> list[PerceptionAnnotation]:
    """Convert an engine AnalysisResult into thesis-schema perception objects.

    When ``df`` is supplied, confidence is graded by thesis SIGNIFICANCE (magnitude vs
    dealing range, scope, freshness) so minor/noise structures self-report 'low' and the
    panel can abstain. Without ``df`` it falls back to raw strength/score.
    """
    atr = _atr(df) if df is not None else 1e-9
    dr = _dealing_range(result, atr) if df is not None else 1e-9
    objects: list[PerceptionAnnotation] = []
    for number, event in enumerate(result.events):
        primitive = _EVENT_MAP.get(event.label)
        if primitive is None:
            continue
        if df is not None:
            sig = _event_significance(event, df, atr, dr)
            swing = event.structure_scope in ("swing", "external")
            conf = "high" if (sig >= HIGH_SIG and swing) else "medium" if sig >= MED_SIG else "low"
        else:
            conf = "high" if event.strength == "strong" else "medium"
        objects.append(
            PerceptionAnnotation(
                annotation_id=f"engine-event-{number}",
                primitive=primitive,
                timeframe=timeframe,
                direction=event.direction,
                structure_scope=event.structure_scope,
                timestamp=event.timestamp,
                price=event.price,
                status="swept" if primitive == "liquidity_sweep" else "unknown",
                confidence=conf,
                notes=event.reason,
            )
        )
    for number, zone in enumerate(result.zones):
        primitive = None
        if zone.kind == "fvg":
            primitive = "fvg"
        elif zone.kind == "order_block":
            primitive = "order_block"
        elif zone.label == "Equal Highs":
            primitive = "equal_highs"
        elif zone.label == "Equal Lows":
            primitive = "equal_lows"
        if primitive is None:
            continue
        if df is not None:
            sig = _zone_significance(zone, atr, dr)
            conf = "high" if sig >= HIGH_SIG else "medium" if sig >= MED_SIG else "low"
        else:
            conf = "high" if float(zone.score or 0.0) >= 0.8 else "medium"
        objects.append(
            PerceptionAnnotation(
                annotation_id=f"engine-zone-{number}",
                primitive=primitive,
                timeframe=timeframe,
                direction=zone.direction,
                price_low=zone.low,
                price_high=zone.high,
                status=zone.status or "unknown",
                confidence=conf,
                notes=zone.reason,
            )
        )
    return objects


def perturbations(base: RuleConfig) -> list[RuleConfig]:
    """A spread of threshold viewpoints around the base config (the 'panel of experts')."""
    grid = [
        {},  # base
        {"pivot_window": max(2, base.pivot_window - 1)},
        {"pivot_window": base.pivot_window + 1},
        {"displacement_body_factor": base.displacement_body_factor * 0.85},
        {"displacement_body_factor": base.displacement_body_factor * 1.15},
        {"structure_break_min_pct": base.structure_break_min_pct * 0.5},
        {"structure_break_min_pct": base.structure_break_min_pct * 2.0},
        {"fvg_min_gap_pct": base.fvg_min_gap_pct * 1.5},
        {"equal_level_tolerance_pct": base.equal_level_tolerance_pct * 1.5},
    ]
    return [base.model_copy(update=upd) for upd in grid]


@dataclass
class PanelObject:
    annotation: PerceptionAnnotation
    votes: int
    n_experts: int

    @property
    def robustness(self) -> float:
        return self.votes / max(self.n_experts, 1)

    @property
    def graded_confidence(self) -> str:
        r = self.robustness
        return "high" if r >= 0.7 else "medium" if r >= 0.4 else "low"


def panel_label(
    df: pd.DataFrame,
    base_config: RuleConfig,
    symbol: str = "PANEL",
    timeframe: str = "15m",
    *,
    time_tolerance_minutes: float = 30.0,
    price_tolerance_pct: float = 0.0015,
    min_zone_iou: float = 0.4,
) -> tuple[list[PanelObject], list[PanelObject]]:
    """Run the engine under every perturbation, then score each base object by how many
    experts (perturbations) independently reproduce it.

    Returns (consensus_objects, fragile_objects): consensus = robustness >= 0.4 (>=medium),
    fragile = below that (abstain candidates). Confidence is the *earned* robustness grade.
    """
    configs = perturbations(base_config)
    per_expert: list[list[PerceptionAnnotation]] = []
    for cfg in configs:
        result, _ = analyze_dataframe(
            df=df, symbol=symbol, timeframe=timeframe, config=cfg,
            notes="panel", input_type="ohlcv",
        )
        per_expert.append(analysis_to_objects(result, timeframe, df=df))

    order = {"low": 0, "medium": 1, "high": 2}
    anchors = per_expert[0]  # significance-graded objects from the base config
    scored: list[PanelObject] = []
    for anchor in anchors:
        votes = 1
        for other in per_expert[1:]:
            matches = greedy_match_annotations(
                [anchor], other,
                time_tolerance_minutes=time_tolerance_minutes,
                price_tolerance_pct=price_tolerance_pct,
                min_zone_iou=min_zone_iou,
            )
            if matches:
                votes += 1
        po = PanelObject(annotation=anchor, votes=votes, n_experts=len(configs))
        # Final confidence = the WEAKER of significance (already on the annotation) and
        # robustness (stability across perturbations). An object must be BOTH to be trusted.
        sig_grade = anchor.confidence
        combined = sig_grade if order[sig_grade] <= order[po.graded_confidence] else po.graded_confidence
        po.annotation.confidence = combined
        scored.append(po)

    consensus = [p for p in scored if p.annotation.confidence != "low"]
    fragile = [p for p in scored if p.annotation.confidence == "low"]
    return consensus, fragile
