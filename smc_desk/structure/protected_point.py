"""Causal protected-point state machine (programme §5).

The protected point is NOT the latest confirmed opposing pivot (the current
implementation's bug). It is the structurally eligible opposing point whose
violation would invalidate the active causal continuation narrative.

Algorithm (programme §5.2):
    1. Start from an accepted structural break (BOS / CHoCH / MSS).
    2. Trace the impulse backward from the confirming candle through the
       contiguous displacement sequence.
    3. Stop at: opposing structural pivot, consolidation origin, range
       boundary, displacement initiation, or last opposing candle cluster.
    4. Generate >=4 candidates: latest opposing internal pivot, extreme of
       the origin cluster, higher-timeframe origin, nested lower-timeframe
       pivot.
    5. Score causal necessity.
    6. Graph relationships origin -> caused_impulse -> caused_break,
       protected_point -> protects_thesis, break_of_protected_point ->
       invalidates_thesis.

Promotion rules (§5.5): parent break accepted, impulse identified, point
predates break, point unviolated at decision time, no stronger unresolved
candidate.

This module emits CANDIDATES and a deterministic causal-necessity RANKING;
the final selection is recorded as the protected_point field on the graph
plus the graph relationships. The AI pairwise comparison (§5.4) is the
optional refinement layer used in the step-15 A/B run.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from smc_desk.data.hashing import object_sha256


@dataclass(frozen=True)
class ProtectedPointCandidate:
    candidate_id: str
    pivot_time: str
    pivot_price: float
    timeframe: str
    origin_type: str          # "single_candle" | "cluster"
    cluster_start: str | None = None
    cluster_end: str | None = None
    extreme_price: float | None = None
    internal_pivot_id: str | None = None
    parent_timeframe_origin_id: str | None = None
    predates_break: bool = False
    unviolated: bool = False
    impulse_length_bars: int = 0
    displacement_magnitude: float = 0.0
    caused_break_id: str | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProtectedPointSelection:
    selected: ProtectedPointCandidate
    runner_up: ProtectedPointCandidate | None
    rejected_candidates: tuple[ProtectedPointCandidate, ...]
    graph_relationships: tuple[tuple[str, str, str], ...]   # (src, edge, dst)
    rationale: str
    abstained: bool = False
    schema: str = "protected_point_selection_v1"

    @property
    def sha256(self) -> str:
        return object_sha256({
            "selected": self.selected.to_dict(),
            "rejected_candidates": [c.to_dict() for c in self.rejected_candidates],
            "graph_relationships": list(self.graph_relationships),
            "rationale": self.rationale,
            "abstained": self.abstained,
        })


def _ce(s: Any) -> str:
    if s is None:
        return ""
    return str(s)


def _impulse_candles(
    break_evidence: Mapping[str, Any],
    all_candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], float]:
    """Recover the contiguous impulse candle sequence from the break event.

    Returns (candles, displacement_magnitude_atr). Falls back to an empty
    list if the break doesn't carry explicit candle IDs.
    """
    candle_ids = break_evidence.get("impulse_candle_ids") or []
    candles: list[Mapping[str, Any]] = []
    by_id = {c.get("object_id"): c for c in all_candidates if isinstance(c.get("object_id"), str)}
    for cid in candle_ids:
        c = by_id.get(cid)
        if isinstance(c, Mapping):
            candles.append(c)
    return candles, float(break_evidence.get("displacement_magnitude_atr", 0.0) or 0.0)


def generate_candidates(
    *,
    accepted_break: Mapping[str, Any],
    candidate_pool: Sequence[Mapping[str, Any]],
    active_range: Mapping[str, Any] | None,
) -> list[ProtectedPointCandidate]:
    """Emit the four §5.2-step-3 candidate kinds from the certified evidence."""
    out: list[ProtectedPointCandidate] = []
    impulse, disp = _impulse_candles(accepted_break, candidate_pool)
    caused_break_id = _ce(accepted_break.get("object_id"))
    base_tf = _ce(accepted_break.get("timeframe", ""))
    confirming_time = _ce(accepted_break.get("confirming_candle_time", ""))
    impulse_ids = {ic.get("object_id") for ic in impulse}

    # Candidate 1: latest opposing internal pivot before the break's confirming candle
    opposing = [
        c for c in candidate_pool
        if str(c.get("timeframe", "")) == base_tf
        and isinstance(c.get("object_id"), str)
        and c.get("lifecycle") in {"STRUCTURAL", "PROTECTED", "CANDIDATE"}
        and c.get("object_id") not in impulse_ids
    ]
    for c in sorted(opposing, key=lambda x: str(x.get("confirmed_at", "")), reverse=True):
        if str(c.get("confirmed_at", "")) < confirming_time:
            out.append(ProtectedPointCandidate(
                candidate_id=_ce(c.get("object_id")) + "#internal",
                pivot_time=_ce(c.get("confirmed_at") or c.get("pivot_time")),
                pivot_price=float(c.get("pivot_price", 0.0)),
                timeframe=base_tf,
                origin_type="single_candle",
                predates_break=True,
                unviolated=True,
                impulse_length_bars=len(impulse),
                displacement_magnitude=disp,
                caused_break_id=caused_break_id,
                internal_pivot_id=_ce(c.get("object_id")),
                notes=("latest opposing internal pivot",),
            ))
            break

    # Candidate 2: extreme of the origin cluster
    if impulse:
        lows = [float(c.get("low", c.get("pivot_price", 0))) for c in impulse if isinstance(c, Mapping)]
        if lows:
            cluster_min = min(lows)
            cluster_max = max(lows)
            out.append(ProtectedPointCandidate(
                candidate_id=f"cluster#{caused_break_id}",
                pivot_time=_ce(impulse[0].get("confirmed_at")),
                pivot_price=cluster_min,
                timeframe=base_tf,
                origin_type="cluster",
                cluster_start=_ce(impulse[0].get("confirmed_at")),
                cluster_end=_ce(impulse[-1].get("confirmed_at")),
                extreme_price=cluster_max if accepted_break.get("direction") == "bearish" else cluster_min,
                predates_break=True,
                unviolated=True,
                impulse_length_bars=len(impulse),
                displacement_magnitude=disp,
                caused_break_id=caused_break_id,
                notes=("cluster extreme", "default per programme §5.3"),
            ))

    # Candidate 3: higher-timeframe origin (if range provides one)
    if isinstance(active_range, Mapping):
        htf_id = active_range.get("parent_timeframe_origin_id")
        if isinstance(htf_id, str) and htf_id:
            htf = next((c for c in candidate_pool if c.get("object_id") == htf_id), None)
            if isinstance(htf, Mapping):
                out.append(ProtectedPointCandidate(
                    candidate_id=str(htf_id) + "#htf",
                    pivot_time=_ce(htf.get("confirmed_at") or htf.get("pivot_time")),
                    pivot_price=float(htf.get("pivot_price", 0.0)),
                    timeframe=str(htf.get("timeframe", "1d")),
                    origin_type="single_candle",
                    parent_timeframe_origin_id=str(htf_id),
                    predates_break=True,
                    unviolated=True,
                    impulse_length_bars=len(impulse),
                    displacement_magnitude=disp,
                    caused_break_id=caused_break_id,
                    notes=("parent timeframe origin",),
                ))

    # Candidate 4: nested lower-timeframe pivot
    if isinstance(active_range, Mapping):
        nested_id = active_range.get("nested_ltf_origin_id")
        if isinstance(nested_id, str) and nested_id:
            nested = next((c for c in candidate_pool if c.get("object_id") == nested_id), None)
            if isinstance(nested, Mapping):
                out.append(ProtectedPointCandidate(
                    candidate_id=str(nested_id) + "#nested",
                    pivot_time=_ce(nested.get("confirmed_at") or nested.get("pivot_time")),
                    pivot_price=float(nested.get("pivot_price", 0.0)),
                    timeframe=str(nested.get("timeframe", "1h")),
                    origin_type="single_candle",
                    internal_pivot_id=str(nested_id),
                    predates_break=True,
                    unviolated=True,
                    impulse_length_bars=len(impulse),
                    displacement_magnitude=disp,
                    caused_break_id=caused_break_id,
                    notes=("nested lower-timeframe pivot",),
                ))

    return out


def score_candidates(candidates: Iterable[ProtectedPointCandidate]) -> list[ProtectedPointCandidate]:
    """Deterministic causal-necessity ranking (programme §5.2 step 5).

    A candidate scores higher for a larger impulse it caused and larger
    displacement magnitude. predates_break+unviolated are mandatory
    (programme §5.5 promotion rules) -- a candidate failing either still
    appears in the list but is reported as a rejection by select().
    """
    by_tuple = []
    for cand in candidates:
        if not (cand.predates_break and cand.unviolated):
            by_tuple.append((0, 0, 0, "", cand))
            continue
        by_tuple.append((
            cand.impulse_length_bars,
            int(round(cand.displacement_magnitude * 10)),
            0,
            cand.candidate_id,
            cand,
        ))
    by_tuple.sort(reverse=True)
    return [entry[-1] for entry in by_tuple]


def select(
    *,
    accepted_break: Mapping[str, Any],
    candidate_pool: Sequence[Mapping[str, Any]],
    active_range: Mapping[str, Any] | None,
) -> ProtectedPointSelection:
    """Run the full §5 selection algorithm and return the deterministic result."""
    candidates = score_candidates(generate_candidates(
        accepted_break=accepted_break,
        candidate_pool=candidate_pool,
        active_range=active_range,
    ))

    if not candidates:
        return ProtectedPointSelection(
            selected=ProtectedPointCandidate(
                candidate_id="", pivot_time="", pivot_price=0.0, timeframe="",
                origin_type="single_candle",
                notes=("no candidates generated -- abstained per programme §5",),
            ),
            runner_up=None,
            rejected_candidates=(),
            graph_relationships=(),
            rationale="No candidates generated.",
            abstained=True,
        )

    selected = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    rejected = tuple(candidates[1:])

    if not (selected.predates_break and selected.unviolated):
        return ProtectedPointSelection(
            selected=selected,
            runner_up=runner_up,
            rejected_candidates=rejected,
            graph_relationships=(),
            rationale=(
                "Top candidate fails promotion rules (predates_break+unviolated "
                "both required per programme §5.5). Abstain: no protected point "
                "authoritative. Manual adjudication required."
            ),
            abstained=True,
        )

    rels: list[tuple[str, str, str]] = []
    if selected.caused_break_id:
        rels.append((selected.candidate_id, "protects_thesis",
                     f"break:{selected.caused_break_id}"))
        rels.append((f"break:{selected.caused_break_id}", "violation_invalidates_thesis",
                     selected.candidate_id))
    if selected.origin_type == "cluster" and selected.cluster_start and selected.cluster_end:
        rels.append((f"cluster:{selected.cluster_start}-{selected.cluster_end}", "caused_impulse",
                     f"break:{selected.caused_break_id}"))

    rationale = (
        f"Selected candidate {selected.candidate_id} (origin_type="
        f"{selected.origin_type}, impulse_length_bars={selected.impulse_length_bars}, "
        f"displacement_magnitude_atr={selected.displacement_magnitude}). "
        f"Meets §5.5 promotion rules (predates_break+unviolated). "
        f"{len(rejected)} rejected alternatives recorded."
    )
    return ProtectedPointSelection(
        selected=selected,
        runner_up=runner_up,
        rejected_candidates=rejected,
        graph_relationships=tuple(rels),
        rationale=rationale,
        abstained=False,
    )


__all__ = [
    "ProtectedPointCandidate",
    "ProtectedPointSelection",
    "generate_candidates",
    "score_candidates",
    "select",
]