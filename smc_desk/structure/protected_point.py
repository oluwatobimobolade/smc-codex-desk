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

import pandas as pd

from smc_desk.data.hashing import object_sha256
from smc_desk.perception.programme_schema import canonical_object_id, candidate_time


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
    causal_score: float = 0.0
    violation_checked: bool = False
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
    timeframe_candles: Sequence[Mapping[str, Any]] | None = None,
    decision_time: str | None = None,
) -> list[ProtectedPointCandidate]:
    """Emit the four §5.2-step-3 candidate kinds from the certified evidence."""
    out: list[ProtectedPointCandidate] = []
    impulse, disp = _impulse_candles(accepted_break, candidate_pool)
    caused_break_id = _ce(accepted_break.get("object_id"))
    base_tf = _ce(accepted_break.get("timeframe", ""))
    confirming_time = _ce(accepted_break.get("confirming_candle_time", ""))
    impulse_ids = {ic.get("object_id") for ic in impulse}
    direction = str(accepted_break.get("direction", "")).lower()
    if direction not in {"bullish", "bearish"}:
        return []
    required_pivot_type = "low" if direction == "bullish" else "high"

    # Candidate 1: latest opposing internal pivot before the break's confirming candle
    opposing = [
        c for c in candidate_pool
        if str(c.get("timeframe", "")) == base_tf
        and canonical_object_id(c)
        and str(c.get("pivot_type") or c.get("kind") or "").lower() == required_pivot_type
        and c.get("lifecycle") in {"STRUCTURAL", "PROTECTED", "CANDIDATE"}
        and canonical_object_id(c) not in impulse_ids
    ]
    for c in sorted(opposing, key=candidate_time, reverse=True):
        ctime = candidate_time(c)
        if _precedes(ctime, confirming_time):
            price = float(c.get("pivot_price", c.get("price", 0.0)))
            checked, unviolated = _unviolated(
                price=price,
                pivot_type=required_pivot_type,
                after_time=ctime,
                candles=timeframe_candles,
                decision_time=decision_time,
                explicit=c.get("unviolated_at_decision"),
            )
            oid = str(canonical_object_id(c))
            out.append(ProtectedPointCandidate(
                candidate_id=oid + "#internal",
                pivot_time=ctime,
                pivot_price=price,
                timeframe=base_tf,
                origin_type="single_candle",
                predates_break=True,
                unviolated=unviolated,
                violation_checked=checked,
                impulse_length_bars=len(impulse),
                displacement_magnitude=disp,
                caused_break_id=caused_break_id,
                internal_pivot_id=oid,
                causal_score=3.0,
                notes=("latest directionally opposing structural pivot",),
            ))
            break

    # Candidate 2: extreme of the origin cluster
    cluster_ids = accepted_break.get("origin_cluster_candle_ids") or []
    by_id = {canonical_object_id(c): c for c in candidate_pool if canonical_object_id(c)}
    cluster = [by_id[cid] for cid in cluster_ids if cid in by_id]
    if cluster:
        prices = [
            float(c.get("low", c.get("pivot_price", 0.0))) if direction == "bullish"
            else float(c.get("high", c.get("pivot_price", 0.0)))
            for c in cluster
        ]
        if prices:
            protected_price = min(prices) if direction == "bullish" else max(prices)
            cluster_start = min((candidate_time(c) for c in cluster if candidate_time(c)), default="")
            cluster_end = max((candidate_time(c) for c in cluster if candidate_time(c)), default="")
            checked, unviolated = _unviolated(
                price=protected_price,
                pivot_type=required_pivot_type,
                after_time=cluster_end,
                candles=timeframe_candles,
                decision_time=decision_time,
                explicit=accepted_break.get("origin_cluster_unviolated_at_decision"),
            )
            out.append(ProtectedPointCandidate(
                candidate_id=f"cluster#{caused_break_id}",
                pivot_time=cluster_end,
                pivot_price=protected_price,
                timeframe=base_tf,
                origin_type="cluster",
                cluster_start=cluster_start,
                cluster_end=cluster_end,
                extreme_price=protected_price,
                predates_break=_precedes(cluster_end, confirming_time),
                unviolated=unviolated,
                violation_checked=checked,
                impulse_length_bars=len(impulse),
                displacement_magnitude=disp,
                caused_break_id=caused_break_id,
                causal_score=4.0,
                notes=("explicit causal origin-cluster extreme",),
            ))

    # Candidate 3: higher-timeframe origin (if range provides one)
    if isinstance(active_range, Mapping):
        htf_id = active_range.get("parent_timeframe_origin_id")
        if isinstance(htf_id, str) and htf_id:
            htf = next((c for c in candidate_pool if canonical_object_id(c) == htf_id), None)
            if isinstance(htf, Mapping):
                htime = candidate_time(htf)
                hprice = float(htf.get("pivot_price", htf.get("price", 0.0)))
                hkind = str(htf.get("pivot_type") or htf.get("kind") or "").lower()
                if hkind != required_pivot_type:
                    htf = None
            if isinstance(htf, Mapping):
                checked, unviolated = _unviolated(
                    price=hprice, pivot_type=hkind, after_time=htime,
                    candles=timeframe_candles, decision_time=decision_time,
                    explicit=htf.get("unviolated_at_decision"),
                )
                out.append(ProtectedPointCandidate(
                    candidate_id=str(htf_id) + "#htf",
                    pivot_time=htime,
                    pivot_price=hprice,
                    timeframe=str(htf.get("timeframe", "1d")),
                    origin_type="single_candle",
                    parent_timeframe_origin_id=str(htf_id),
                    predates_break=_precedes(htime, confirming_time),
                    unviolated=unviolated,
                    violation_checked=checked,
                    impulse_length_bars=len(impulse),
                    displacement_magnitude=disp,
                    caused_break_id=caused_break_id,
                    causal_score=2.0,
                    notes=("parent timeframe origin",),
                ))

    # Candidate 4: nested lower-timeframe pivot
    if isinstance(active_range, Mapping):
        nested_id = active_range.get("nested_ltf_origin_id")
        if isinstance(nested_id, str) and nested_id:
            nested = next((c for c in candidate_pool if canonical_object_id(c) == nested_id), None)
            if isinstance(nested, Mapping):
                ntime = candidate_time(nested)
                nprice = float(nested.get("pivot_price", nested.get("price", 0.0)))
                nkind = str(nested.get("pivot_type") or nested.get("kind") or "").lower()
                if nkind != required_pivot_type:
                    nested = None
            if isinstance(nested, Mapping):
                checked, unviolated = _unviolated(
                    price=nprice, pivot_type=nkind, after_time=ntime,
                    candles=timeframe_candles, decision_time=decision_time,
                    explicit=nested.get("unviolated_at_decision"),
                )
                out.append(ProtectedPointCandidate(
                    candidate_id=str(nested_id) + "#nested",
                    pivot_time=ntime,
                    pivot_price=nprice,
                    timeframe=str(nested.get("timeframe", "1h")),
                    origin_type="single_candle",
                    internal_pivot_id=str(nested_id),
                    predates_break=_precedes(ntime, confirming_time),
                    unviolated=unviolated,
                    violation_checked=checked,
                    impulse_length_bars=len(impulse),
                    displacement_magnitude=disp,
                    caused_break_id=caused_break_id,
                    causal_score=1.0,
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
        if not (cand.predates_break and cand.unviolated and cand.violation_checked):
            by_tuple.append((0, 0, 0, "", cand))
            continue
        by_tuple.append((
            int(round(cand.causal_score * 100)),
            cand.impulse_length_bars,
            int(round(cand.displacement_magnitude * 10)),
            cand.pivot_time,
            cand,
        ))
    by_tuple.sort(reverse=True)
    return [entry[-1] for entry in by_tuple]


def select(
    *,
    accepted_break: Mapping[str, Any],
    candidate_pool: Sequence[Mapping[str, Any]],
    active_range: Mapping[str, Any] | None,
    timeframe_candles: Sequence[Mapping[str, Any]] | None = None,
    decision_time: str | None = None,
) -> ProtectedPointSelection:
    """Run the full §5 selection algorithm and return the deterministic result."""
    candidates = score_candidates(generate_candidates(
        accepted_break=accepted_break,
        candidate_pool=candidate_pool,
        active_range=active_range,
        timeframe_candles=timeframe_candles,
        decision_time=decision_time,
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

    if runner_up is not None and _selection_key(selected) == _selection_key(runner_up):
        return ProtectedPointSelection(
            selected=selected,
            runner_up=runner_up,
            rejected_candidates=rejected,
            graph_relationships=(),
            rationale=(
                "Top protected-point candidates are causally tied. The deterministic layer "
                "refuses to resolve the ambiguity by candidate identifier."
            ),
            abstained=True,
        )

    if not (selected.predates_break and selected.unviolated and selected.violation_checked):
        return ProtectedPointSelection(
            selected=selected,
            runner_up=runner_up,
            rejected_candidates=rejected,
            graph_relationships=(),
            rationale=(
                "Top candidate fails promotion rules (predates_break, replayed "
                "unviolated status, and violation evidence are all required). "
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


def _precedes(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return pd.Timestamp(left) < pd.Timestamp(right)
    except (TypeError, ValueError):
        return False


def _selection_key(candidate: ProtectedPointCandidate) -> tuple[Any, ...]:
    return (
        candidate.predates_break,
        candidate.unviolated,
        candidate.violation_checked,
        round(candidate.causal_score, 8),
        candidate.impulse_length_bars,
        round(candidate.displacement_magnitude, 8),
        candidate.pivot_time,
    )


def _unviolated(*, price, pivot_type, after_time, candles, decision_time, explicit):
    """Replay violation from candles; explicit booleans are accepted only as sealed fixture evidence."""
    if candles is None:
        return (isinstance(explicit, bool), bool(explicit) if isinstance(explicit, bool) else False)
    if pivot_type not in {"high", "low"} or not after_time:
        return False, False
    start = pd.Timestamp(after_time)
    end = pd.Timestamp(decision_time) if decision_time else None
    checked = False
    for candle in candles:
        raw_time = candle.get("timestamp") or candle.get("confirmed_at")
        if not raw_time:
            continue
        timestamp = pd.Timestamp(raw_time)
        if timestamp <= start or (end is not None and timestamp > end):
            continue
        checked = True
        close = float(candle.get("close"))
        if pivot_type == "low" and close < price:
            return True, False
        if pivot_type == "high" and close > price:
            return True, False
    return checked, checked


__all__ = [
    "ProtectedPointCandidate",
    "ProtectedPointSelection",
    "generate_candidates",
    "score_candidates",
    "select",
]
