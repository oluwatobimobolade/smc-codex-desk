"""Canonical swing candidate schema shared by every candidate generator.

Per programme §4.3 ("Swing candidate schema") and §4.4 ("Structural selection
features"), every swing candidate carries the same record shape so the AI
reconciler can reason across generators without per-generator glue.

The record is a plain dataclass (not Pydantic) so generator code never has
to validate every row at emission time -- the atlas validates, hashes, and
indexes after all generators have run.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


# Recognised generator identifiers -- the atlas and reconciler index on these.
GENERATOR_FRACTAL = "fractal"
GENERATOR_DIRECTIONAL_CHANGE = "directional_change"
GENERATOR_PROMINENCE = "prominence"
GENERATOR_CHANGEPOINT = "changepoint"
GENERATOR_DISPLACEMENT = "displacement"

ALL_GENERATORS: tuple[str, ...] = (
    GENERATOR_FRACTAL,
    GENERATOR_DIRECTIONAL_CHANGE,
    GENERATOR_PROMINENCE,
    GENERATOR_CHANGEPOINT,
    GENERATOR_DISPLACEMENT,
)


@dataclass(frozen=True)
class SwingCandidate:
    """A swing pivot candidate, emitted by exactly one generator at first,
    then enriched by the atlas with observations from later passes and other
    generators (when the same pivot appears across generators, generator_sources
    records every generator that produced it).

    Required fields per programme §4.3 (every candidate stores these).
    Optional fields start with ``_``-less defaults and may be enriched by the
    atlas after generation.
    """
    candidate_id: str                       # stable within a case
    timeframe: str                          # owning timeframe label (e.g., "15m")
    pivot_type: str                         # "high" | "low"
    pivot_time: str                         # ISO-8601 candle close time
    pivot_price: float                      # high price (if pivot_type=high) or low (if low)
    generator_source: str                   # which generator produced this record
    scale: str = "unknown"                  # "micro" | "local" | "internal" | "external_candidate" | "atlas"
    prominence: float | None = None          # protrusion from surrounding extrema
    volatility_normalized_move: float | None = None  # ATR-normalised distance from neighbouring pivot
    bars_left: int | None = None            # fractal window (or DC overshoot count)
    bars_right: int | None = None
    survival_bars: int | None = None        # how long the level held unbroken
    subordinate_pivot_count: int | None = None  # how many smaller pivots formed inside the leg
    displacement_after: bool = False        # was there a displacement candle immediately after this pivot?
    fvg_created: bool = False               # was an FVG created after this pivot?
    breaks_caused: list[str] = field(default_factory=list)   # break IDs this pivot caused
    liquidity_visibility: str | None = None # qualitative: "high" | "medium" | "low"
    touch_count: int = 0                    # how many times price has touched this level
    age: int = 0                            # bars since pivot formed
    lifecycle: str = "CANDIDATE"            # CANDIDATE | STRUCTURAL | PROTECTED | BROKEN | REJECTED | STALE
    parent_candidate_ids: list[str] = field(default_factory=list)
    child_candidate_ids: list[str] = field(default_factory=list)
    causal_origin_hypotheses: list[Mapping[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def candidate_id(generator: str, timeframe: str, pivot_time: str, pivot_type: str) -> str:
    """Stable deterministic id: same pivot from two generators has the SAME id
    (so the atlas can fuse across generators).

    The id is NOT generator-prefixed on purpose: when fractal and prominence
    both find the same pivot, they share one record with generator_sources
    populated from both.
    """
    return f"{timeframe}:{pivot_type}:{pivot_time}"


__all__ = [
    "ALL_GENERATORS",
    "GENERATOR_FRACTAL",
    "GENERATOR_DIRECTIONAL_CHANGE",
    "GENERATOR_PROMINENCE",
    "GENERATOR_CHANGEPOINT",
    "GENERATOR_DISPLACEMENT",
    "SwingCandidate",
    "candidate_id",
]