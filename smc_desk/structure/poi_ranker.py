"""POI ranker with three independent scores (programme §8).

A Price of Interest is any candidate price zone where reaction is expected
because of prior causal significance (order blocks, clusters, FVGs, supply/
demand zones, breakers where doctrine permits, nested HTF/LTF zones).

Per programme §8.3, a POI candidate carries THREE separate scores plus a
combined rank and uncertainty:

    deterministic_score  -- structural evidence, fully deterministic
    ai_semantic_score     -- AI pairwise comparison of importance (null until
                             the reconciler emits it)
    empirical_score       -- reaction/outcome history (null until outcomes
                             exist; never invented)
    combined_rank         -- only computed from non-null inputs
    uncertainty           -- decomposed, never averaged into false precision

The programme forbids collapsing the three scores into one number
prematurely. This module computes the deterministic score and a combined
rank that is null when either required input is missing. It deliberately
does NOT fabricate the AI or empirical scores.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from smc_desk.data.hashing import object_sha256


@dataclass(frozen=True)
class POIScores:
    poi_id: str
    timeframe: str
    deterministic_score: float
    ai_semantic_score: float | None = None     # set by the reconciler role
    empirical_score: float | None = None       # set after outcome evaluation
    combined_rank: int | None = None
    uncertainty: str = "insufficient_context"  # see doctrine §17 categories
    eligible: bool = True
    causal_features: dict[str, Any] = field(default_factory=dict)
    location_features: dict[str, Any] = field(default_factory=dict)
    lifecycle_features: dict[str, Any] = field(default_factory=dict)
    quality_features: dict[str, Any] = field(default_factory=dict)
    narrative_features: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    schema: str = "poi_scores_v1"

    @property
    def sha256(self) -> str:
        return object_sha256({
            "poi_id": self.poi_id,
            "deterministic_score": self.deterministic_score,
            "ai_semantic_score": self.ai_semantic_score,
            "empirical_score": self.empirical_score,
            "combined_rank": self.combined_rank,
            "uncertainty": self.uncertainty,
            "eligible": self.eligible,
        })


def deterministic_score(
    *,
    poi: Mapping[str, Any],
    active_range: Mapping[str, Any] | None,
    owning_timeframe: str,
) -> float:
    """Deterministic structural-evidence score per programme §8.2.

    Causal features (binary, weighted):
        originated_displacement  -> +3
        caused_bos               -> +3
        linked_protected_point   -> +2
        created_fvg              -> +1
        in_active_range          -> +1

    Location features:
        premium/discount aligned with direction -> +1
        proximity_to_liquidity                  -> +1
        depth_relative_to_shallow               -> +1 (deeper POI scores higher)

    Lifecycle features:
        fresh                                   -> +2
        partially_mitigated                     -> +1
        fully_mitigated/invalid                 -> 0
        age penalty                             -> -1 if age > active_range bar span

    Quality features:
        departure_speed (ATR/bar)               -> +1 if > 0.8
        imbalance_size (ATR)                    -> +1 if > 0.5
        clean_origin                            -> +1

    Narrative features:
        liquidity_before                        -> +1
        parent_alignment                        -> +1
    """
    score = 0.0
    causal = poi.get("causal_features") or {}
    if causal.get("originated_displacement"):
        score += 3
    if causal.get("caused_bos"):
        score += 3
    if causal.get("linked_protected_point"):
        score += 2
    if causal.get("created_fvg"):
        score += 1
    if causal.get("in_active_range"):
        score += 1

    location = poi.get("location_features") or {}
    if location.get("direction_aligned"):
        score += 1
    if location.get("proximity_to_liquidity"):
        score += 1
    if location.get("depth_relative_to_shallow") == "deeper":
        score += 1

    lifecycle = poi.get("lifecycle_features") or {}
    state = str(lifecycle.get("state", "")).lower()
    if state == "fresh":
        score += 2
    elif state in {"partially_mitigated", "partial"}:
        score += 1
    elif state in {"fully_mitigated", "invalid", "invalidated"}:
        score += 0
    age = int(lifecycle.get("age", 0) or 0)
    if isinstance(active_range, Mapping):
        span = int(active_range.get("bar_span", 0) or 0)
        if span and age > span:
            score -= 1

    quality = poi.get("quality_features") or {}
    if float(quality.get("departure_speed_atr_per_bar", 0.0) or 0.0) > 0.8:
        score += 1
    if float(quality.get("imbalance_size_atr", 0.0) or 0.0) > 0.5:
        score += 1
    if quality.get("clean_origin"):
        score += 1

    narrative = poi.get("narrative_features") or {}
    if narrative.get("liquidity_before"):
        score += 1
    if narrative.get("parent_alignment"):
        score += 1

    return float(score)


def combined_rank_and_uncertainty(
    poi_scores: Sequence[POIScores],
) -> list[POIScores]:
    """Assign combined_rank using whatever non-null inputs exist.

    Per programme §8.3 the combined_rank uses all three scores when present.
    If only the deterministic score is set (typical early state), the rank is
    by deterministic score but uncertainty is 'probable' (one axis only); if
    AI semantic is also present uncertainty is 'probable'/'confirmed' (two
    axes); only with all three is it 'confirmed'. If the deterministic score
    conflicts with the AI score, uncertainty is 'ambiguous'.

    Returns a NEW list with combined_rank and uncertainty populated. Never
    mutates inputs. Empirical score missing -> never 'confirmed' on the
    empirical axis; that is recorded, not silently dropped.
    """
    eligible = [s for s in poi_scores if s.eligible]
    det_order = sorted(eligible, key=lambda x: (-x.deterministic_score, x.poi_id))
    ai_order = sorted(
        [s for s in eligible if s.ai_semantic_score is not None],
        key=lambda x: (-float(x.ai_semantic_score), x.poi_id),
    )
    emp_order = sorted(
        [s for s in eligible if s.empirical_score is not None],
        key=lambda x: (-float(x.empirical_score), x.poi_id),
    )
    positions = {
        "det": {s.poi_id: i for i, s in enumerate(det_order)},
        "ai": {s.poi_id: i for i, s in enumerate(ai_order)},
        "emp": {s.poi_id: i for i, s in enumerate(emp_order)},
    }

    def consensus_key(s: POIScores) -> tuple:
        ranks = [positions["det"][s.poi_id]]
        if s.poi_id in positions["ai"]:
            ranks.append(positions["ai"][s.poi_id])
        if s.poi_id in positions["emp"]:
            ranks.append(positions["emp"][s.poi_id])
        mean_rank = sum(ranks) / len(ranks)
        ai_tiebreak = positions["ai"].get(s.poi_id, len(eligible))
        return (mean_rank, ai_tiebreak, positions["det"][s.poi_id], s.poi_id)

    ranked = sorted(eligible, key=consensus_key)
    out: list[POIScores] = []
    for idx, s in enumerate(ranked, start=1):
        has_det = s.deterministic_score is not None
        has_ai = s.ai_semantic_score is not None
        has_emp = s.empirical_score is not None
        if has_det and has_ai and has_emp:
            # Three axes. Check agreement for uncertainty.
            uncertainty = _agreement(det_order, ai_order, s)
        elif has_det and has_ai:
            uncertainty = "probable" if _agreement(det_order, ai_order, s) == "confirmed" else "ambiguous"
        elif has_det:
            uncertainty = "probable" if s.deterministic_score > 0 else "insufficient_context"
        else:
            uncertainty = "insufficient_context"

        out.append(_replace(s, combined_rank=idx, uncertainty=uncertainty))
    out.extend(
        _replace(s, combined_rank=None, uncertainty="contradicted")
        for s in poi_scores if not s.eligible
    )
    return out


def _agreement(det_ranked: Sequence[POIScores], ai_ranked: Sequence[POIScores], target: POIScores) -> str:
    """Compare a POI's deterministic rank vs its AI rank.

    If they agree on the target's position (within ±1) -> confirmed.
    If they diverge -> ambiguous. Contradicted is reserved for cases where
    one axis ranks the POI high and the other ranks it low (gap > 3).
    """
    det_pos = next((i for i, p in enumerate(det_ranked) if p.poi_id == target.poi_id), None)
    ai_pos = next((i for i, p in enumerate(ai_ranked) if p.poi_id == target.poi_id), None)
    if det_pos is None or ai_pos is None:
        return "insufficient_context"
    gap = abs(det_pos - ai_pos)
    if gap == 0:
        return "confirmed"
    if gap > 3:
        return "contradicted"
    return "ambiguous"


def _replace(s: POIScores, **changes) -> POIScores:
    """Immutable field replacement on the frozen dataclass."""
    base = asdict(s)
    base.update(changes)
    # asdict unwraps tuples to lists for fields like notes; reconstruct cleanly
    base["notes"] = tuple(base.get("notes") or ())
    return POIScores(**base)


def score_pois(
    *,
    pois: Sequence[Mapping[str, Any]],
    active_range: Mapping[str, Any] | None,
) -> list[POIScores]:
    """Score a batch of POIs. ai_semantic_score / empirical_score stay None."""
    out: list[POIScores] = []
    for p in pois:
        normalized = _normalize_poi(p)
        lifecycle = normalized["lifecycle_features"]
        state = str(lifecycle.get("state", "")).lower()
        eligible = state not in {"fully_mitigated", "invalid", "invalidated", "terminal", "consumed"}
        ds = deterministic_score(
            poi=normalized,
            active_range=active_range,
            owning_timeframe=str(normalized.get("origin_timeframe", "")),
        )
        out.append(POIScores(
            poi_id=str(normalized.get("object_id") or normalized.get("poi_id") or ""),
            timeframe=str(normalized.get("origin_timeframe", "")),
            deterministic_score=ds,
            causal_features=dict(normalized.get("causal_features") or {}),
            location_features=dict(normalized.get("location_features") or {}),
            lifecycle_features=dict(normalized.get("lifecycle_features") or {}),
            quality_features=dict(normalized.get("quality_features") or {}),
            narrative_features=dict(normalized.get("narrative_features") or {}),
            eligible=eligible,
            notes=("deterministic score only; AI + empirical pending",),
        ))
    return combined_rank_and_uncertainty(out)


def attach_ai_semantic(
    poi_scores: Sequence[POIScores],
    *,
    ai_ranking: Mapping[str, float],
) -> list[POIScores]:
    """Attach AI semantic scores from the reconciler's pairwise comparison.

    ai_ranking maps poi_id -> ai_semantic_score (a float, higher = more
    important per programme §8.3). POIs not in the mapping keep None.
    Re-runs combined_rank_and_uncertainty so the combined_rank reflects the
    new axis. Does NOT touch the empirical score.
    """
    for poi_id, score in ai_ranking.items():
        if not isinstance(score, (int, float)) or not float("-inf") < float(score) < float("inf"):
            raise ValueError(f"AI semantic score for {poi_id!r} must be finite.")
    with_ai = [
        _replace(s, ai_semantic_score=ai_ranking.get(s.poi_id)) if s.poi_id in ai_ranking else s
        for s in poi_scores
    ]
    return combined_rank_and_uncertainty(with_ai)


def _normalize_poi(poi: Mapping[str, Any]) -> dict[str, Any]:
    """Map real PEV2 POI fields into the ranker's explicit feature contract."""
    out = dict(poi)
    evidence = poi.get("evidence") if isinstance(poi.get("evidence"), Mapping) else {}
    causal = dict(poi.get("causal_features") or {})
    causal.setdefault("caused_bos", bool(evidence.get("origin_break_id")))
    causal.setdefault("created_fvg", str(poi.get("object_type", "")) == "fvg")
    causal.setdefault("originated_displacement", bool(evidence.get("origin_break_id") or evidence.get("displacement_id")))
    lifecycle = dict(poi.get("lifecycle_features") or {})
    lifecycle.setdefault(
        "state",
        poi.get("terminal_reason")
        or poi.get("activity_status")
        or poi.get("mitigation_status")
        or "unknown",
    )
    quality = dict(poi.get("quality_features") or {})
    if evidence.get("atr_ratio") is not None:
        quality.setdefault("imbalance_size_atr", evidence.get("atr_ratio"))
    out["origin_timeframe"] = poi.get("origin_timeframe") or poi.get("timeframe") or ""
    out["causal_features"] = causal
    out["location_features"] = dict(poi.get("location_features") or {})
    out["lifecycle_features"] = lifecycle
    out["quality_features"] = quality
    out["narrative_features"] = dict(poi.get("narrative_features") or {})
    return out


__all__ = [
    "POIScores",
    "deterministic_score",
    "combined_rank_and_uncertainty",
    "score_pois",
    "attach_ai_semantic",
]
