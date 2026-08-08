"""Structural significance grading (observe-only, additive).

The canonical detectors answer "does this match the geometric definition?".
They do not answer "does this matter?". With `swing_scales` at 1/3/5 bars and
`structure_break_min_bps` at 4.0, a $25 poke beyond an 11-bar fractal on BTC
satisfies every geometric definition of an external structure break. Measured
on real BTCUSDT 15m data that produces ~15 confirmed external breaks and 5
CHoCH in 3.7 days, and evidence packs carrying thousands of objects.

A trader does not read a chart that way. Significance is *relative*: to
volatility, to the leg the move belongs to, and to the active dealing range.
This module supplies that missing relative judgement as a separate, purely
deterministic grading pass.

Design rules (deliberate):

* **Additive.** Nothing here mutates detector output or changes any existing
  contract. Callers opt in by asking for a grade.
* **Observe-only.** A grade is descriptive evidence. It creates no signal, no
  promotion, and no trade authority.
* **Downgrade-shaped.** Grading can only ever *reduce* what a consumer chooses
  to display or reason over. It never invents an object the detector did not
  emit, and never upgrades an unconfirmed object into a confirmed one.
* **Explainable.** Every grade carries the numbers that produced it, so a
  human can audit why a level was called noise.

Grades, in descending order of structural weight:

``major``
    Defines the active range or the controlling leg. A trader would mark it.
``intermediate``
    Real structure inside the leg; useful for timing and refinement.
``minor``
    Visible but subordinate; usually internal noise on the owning timeframe.
``noise``
    Below the volatility floor. Should not be drawn or reasoned over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

GRADES = ("major", "intermediate", "minor", "noise")
_GRADE_RANK = {name: index for index, name in enumerate(GRADES)}

# Prominence expressed as a multiple of ATR. A swing that protrudes less than
# a third of one ATR beyond its neighbours is inside normal bar-to-bar noise.
MAJOR_ATR_PROMINENCE = 1.5
INTERMEDIATE_ATR_PROMINENCE = 0.75
MINOR_ATR_PROMINENCE = 0.30

# Prominence expressed as a fraction of the active range. A swing worth
# calling "major" should account for a meaningful share of the range it sits
# in, regardless of how quiet volatility happens to be.
MAJOR_RANGE_FRACTION = 0.25
INTERMEDIATE_RANGE_FRACTION = 0.10

# Displacement (body travel beyond structure, in ATR) required before a break
# is treated as energetic rather than a marginal poke.
MAJOR_BREAK_DISPLACEMENT_ATR = 1.0
INTERMEDIATE_BREAK_DISPLACEMENT_ATR = 0.5
MINIMUM_BREAK_DISPLACEMENT_ATR = 0.20

# The range axis only carries information when the range is genuinely wider
# than day-to-day volatility. Inside a consolidation barely larger than one
# ATR, "a large share of the range" describes noise, not structure, so the
# range axis is suppressed and volatility alone decides.
MIN_RANGE_ATR_MULTIPLE = 3.0


@dataclass(frozen=True)
class SignificanceScore:
    """Why an object received its grade. Every field is auditable."""

    object_id: str
    grade: str
    atr_multiple: float
    range_fraction: float
    reasons: tuple[str, ...] = ()
    schema: str = "structural_significance_v1"

    @property
    def is_tradeable_structure(self) -> bool:
        """True for grades a trader would actually reason over."""
        return self.grade in {"major", "intermediate"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "object_id": self.object_id,
            "grade": self.grade,
            "atr_multiple": round(self.atr_multiple, 4),
            "range_fraction": round(self.range_fraction, 4),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SignificanceSummary:
    """Aggregate view over one timeframe's graded objects."""

    scores: tuple[SignificanceScore, ...] = ()
    atr: float = 0.0
    range_size: float = 0.0
    schema: str = "structural_significance_summary_v1"

    def by_grade(self, grade: str) -> tuple[SignificanceScore, ...]:
        return tuple(s for s in self.scores if s.grade == grade)

    @property
    def tradeable(self) -> tuple[SignificanceScore, ...]:
        return tuple(s for s in self.scores if s.is_tradeable_structure)

    @property
    def counts(self) -> dict[str, int]:
        return {grade: len(self.by_grade(grade)) for grade in GRADES}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "atr": round(self.atr, 8),
            "range_size": round(self.range_size, 8),
            "counts": self.counts,
            "scores": [s.to_dict() for s in self.scores],
        }


def _f(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def average_true_range(candles: Sequence[Mapping[str, Any]], period: int = 14) -> float:
    """Wilder-style ATR over the last ``period`` completed candles.

    Falls back to mean high-low range when there are too few candles to build
    true ranges. Returns 0.0 only when there is no usable data at all, which
    callers must treat as "cannot grade".
    """
    rows = [c for c in candles if c is not None]
    if not rows:
        return 0.0
    trs: list[float] = []
    previous_close: float | None = None
    for row in rows:
        high = _f(row.get("high"))
        low = _f(row.get("low"))
        close = _f(row.get("close"))
        if previous_close is None:
            trs.append(max(0.0, high - low))
        else:
            trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    window = trs[-period:] if len(trs) > period else trs
    if not window:
        return 0.0
    return sum(window) / len(window)


def _usable_range_fraction(
    prominence: float,
    range_size: float,
    atr: float,
    reasons: list[str],
) -> float:
    """Share of the active range, suppressed when the range is degenerate.

    Inside a consolidation only a couple of ATRs wide, every wiggle occupies a
    large fraction of the range. Treating that as structural significance is
    how noise gets promoted, so the axis is disabled below
    ``MIN_RANGE_ATR_MULTIPLE`` and volatility alone decides.
    """
    if range_size <= 0:
        return 0.0
    if atr > 0 and range_size < MIN_RANGE_ATR_MULTIPLE * atr:
        reasons.append(
            f"range {range_size / atr:.1f}x ATR is too tight to be structural; "
            "range axis suppressed"
        )
        return 0.0
    return prominence / range_size


def _grade_from_thresholds(
    *,
    atr_multiple: float,
    range_fraction: float,
    reasons: list[str],
) -> str:
    """Combine the volatility view and the range view.

    Either axis alone can justify ``major``: a move can matter because it is
    large relative to current volatility, or because it carves out a large
    share of the range even in quiet conditions. Both must fail for an object
    to fall to ``noise``.
    """
    if atr_multiple >= MAJOR_ATR_PROMINENCE:
        reasons.append(f"prominence {atr_multiple:.2f}x ATR >= {MAJOR_ATR_PROMINENCE}")
        return "major"
    if range_fraction >= MAJOR_RANGE_FRACTION:
        reasons.append(f"spans {range_fraction:.1%} of active range >= {MAJOR_RANGE_FRACTION:.0%}")
        return "major"
    if atr_multiple >= INTERMEDIATE_ATR_PROMINENCE or range_fraction >= INTERMEDIATE_RANGE_FRACTION:
        reasons.append(
            f"prominence {atr_multiple:.2f}x ATR / {range_fraction:.1%} of range meets intermediate floor"
        )
        return "intermediate"
    if atr_multiple >= MINOR_ATR_PROMINENCE:
        reasons.append(f"prominence {atr_multiple:.2f}x ATR meets minor floor {MINOR_ATR_PROMINENCE}")
        return "minor"
    reasons.append(
        f"prominence {atr_multiple:.2f}x ATR below noise floor {MINOR_ATR_PROMINENCE}"
    )
    return "noise"


def grade_swing(
    swing: Any,
    *,
    atr: float,
    range_size: float = 0.0,
) -> SignificanceScore:
    """Grade one swing by how far it protrudes beyond its neighbours.

    Accepts either a ``SwingObject`` or a plain mapping carrying the same
    evidence fields, so this works on live detector output and on serialised
    evidence packs alike.
    """
    object_id, prominence = _swing_prominence(swing)
    reasons: list[str] = []
    if atr <= 0:
        return SignificanceScore(
            object_id=object_id,
            grade="noise",
            atr_multiple=0.0,
            range_fraction=0.0,
            reasons=("cannot grade without ATR",),
        )
    atr_multiple = prominence / atr if atr else 0.0
    range_fraction = _usable_range_fraction(prominence, range_size, atr, reasons)
    grade = _grade_from_thresholds(
        atr_multiple=atr_multiple, range_fraction=range_fraction, reasons=reasons
    )
    return SignificanceScore(
        object_id=object_id,
        grade=grade,
        atr_multiple=atr_multiple,
        range_fraction=range_fraction,
        reasons=tuple(reasons),
    )


def _swing_prominence(swing: Any) -> tuple[str, float]:
    """Pull (object_id, prominence_price) from an object or mapping."""
    if isinstance(swing, Mapping):
        object_id = str(swing.get("object_id") or swing.get("swing_id") or "")
        evidence = swing.get("evidence")
        if isinstance(evidence, Mapping):
            prominence = _f(evidence.get("prominence_price"))
        else:
            prominence = _f(swing.get("prominence_price"))
        return object_id, prominence
    object_id = str(getattr(swing, "object_id", "") or "")
    evidence = getattr(swing, "evidence", None)
    prominence = _f(getattr(evidence, "prominence_price", None))
    return object_id, prominence


def grade_structure_break(
    brk: Any,
    *,
    atr: float,
    range_size: float = 0.0,
) -> SignificanceScore:
    """Grade a structural break by displacement, not by bare penetration.

    A break earns its label from the energy of the move that produced it. The
    canonical detector confirms a break on any body close beyond the level
    (``structure_break_min_bps`` is 4.0, i.e. 0.04%), which is why marginal
    pokes currently arrive labelled BOS. Here, body-close penetration measured
    in ATR is the discriminator, and an unconfirmed wick probe can never grade
    above ``noise``.
    """
    object_id, penetration, is_probe = _break_penetration(brk)
    reasons: list[str] = []
    if is_probe:
        return SignificanceScore(
            object_id=object_id,
            grade="noise",
            atr_multiple=0.0,
            range_fraction=0.0,
            reasons=("unconfirmed wick probe is never significant structure",),
        )
    if atr <= 0:
        return SignificanceScore(
            object_id=object_id,
            grade="noise",
            atr_multiple=0.0,
            range_fraction=0.0,
            reasons=("cannot grade without ATR",),
        )
    atr_multiple = penetration / atr if atr else 0.0
    range_fraction = _usable_range_fraction(penetration, range_size, atr, reasons)

    if atr_multiple < MINIMUM_BREAK_DISPLACEMENT_ATR:
        reasons.append(
            f"body close only {atr_multiple:.2f}x ATR beyond structure; "
            f"below the {MINIMUM_BREAK_DISPLACEMENT_ATR} displacement floor"
        )
        grade = "noise"
    elif atr_multiple >= MAJOR_BREAK_DISPLACEMENT_ATR or range_fraction >= MAJOR_RANGE_FRACTION:
        reasons.append(f"displacement {atr_multiple:.2f}x ATR beyond structure")
        grade = "major"
    elif atr_multiple >= INTERMEDIATE_BREAK_DISPLACEMENT_ATR:
        reasons.append(f"displacement {atr_multiple:.2f}x ATR meets intermediate floor")
        grade = "intermediate"
    else:
        reasons.append(f"displacement {atr_multiple:.2f}x ATR is a marginal penetration")
        grade = "minor"
    return SignificanceScore(
        object_id=object_id,
        grade=grade,
        atr_multiple=atr_multiple,
        range_fraction=range_fraction,
        reasons=tuple(reasons),
    )


def _break_penetration(brk: Any) -> tuple[str, float, bool]:
    """Pull (object_id, body_close_penetration, is_unconfirmed_probe)."""
    if isinstance(brk, Mapping):
        object_id = str(brk.get("object_id") or "")
        evidence = brk.get("evidence") if isinstance(brk.get("evidence"), Mapping) else {}
        penetration = abs(_f(evidence.get("body_close_penetration")))
        probe = bool(evidence.get("is_unconfirmed_probe", False))
        if not evidence and brk.get("is_wick_only_probe") is not None:
            probe = bool(brk.get("is_wick_only_probe"))
        return object_id, penetration, probe
    object_id = str(getattr(brk, "object_id", "") or "")
    evidence = getattr(brk, "evidence", None)
    penetration = abs(_f(getattr(evidence, "body_close_penetration", None)))
    probe = bool(getattr(evidence, "is_unconfirmed_probe", False))
    return object_id, penetration, probe


def grade_timeframe(
    *,
    candles: Sequence[Mapping[str, Any]],
    swings: Iterable[Any] = (),
    structure_breaks: Iterable[Any] = (),
    range_size: float | None = None,
    atr_period: int = 14,
) -> SignificanceSummary:
    """Grade every object on one timeframe against that timeframe's volatility.

    ``range_size`` defaults to the high-low span of the supplied candles, which
    is the honest local proxy when no certified dealing range exists yet.
    """
    atr = average_true_range(candles, period=atr_period)
    if range_size is None:
        highs = [_f(c.get("high")) for c in candles if c is not None]
        lows = [_f(c.get("low")) for c in candles if c is not None]
        range_size = (max(highs) - min(lows)) if highs and lows else 0.0

    scores: list[SignificanceScore] = []
    for swing in swings:
        scores.append(grade_swing(swing, atr=atr, range_size=range_size))
    for brk in structure_breaks:
        scores.append(grade_structure_break(brk, atr=atr, range_size=range_size))
    return SignificanceSummary(scores=tuple(scores), atr=atr, range_size=range_size)


def filter_to_significant(
    objects: Sequence[Any],
    scores: Mapping[str, SignificanceScore],
    *,
    minimum_grade: str = "intermediate",
) -> list[Any]:
    """Return only the objects graded at or above ``minimum_grade``.

    Objects with no score are dropped rather than assumed significant: an
    ungraded object is unproven, and this layer must never widen what a
    consumer sees.
    """
    if minimum_grade not in _GRADE_RANK:
        raise ValueError(f"Unknown grade: {minimum_grade!r}")
    ceiling = _GRADE_RANK[minimum_grade]
    kept: list[Any] = []
    for obj in objects:
        object_id = (
            str(obj.get("object_id") or "")
            if isinstance(obj, Mapping)
            else str(getattr(obj, "object_id", "") or "")
        )
        score = scores.get(object_id)
        if score is None:
            continue
        if _GRADE_RANK[score.grade] <= ceiling:
            kept.append(obj)
    return kept


__all__ = [
    "GRADES",
    "MAJOR_ATR_PROMINENCE",
    "INTERMEDIATE_ATR_PROMINENCE",
    "MINOR_ATR_PROMINENCE",
    "MINIMUM_BREAK_DISPLACEMENT_ATR",
    "SignificanceScore",
    "SignificanceSummary",
    "average_true_range",
    "filter_to_significant",
    "grade_structure_break",
    "grade_swing",
    "grade_timeframe",
]
