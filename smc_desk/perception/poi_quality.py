"""Rank POI candidates the way a trader weighs them (observe-only).

Detection now emits every opposing base it finds rather than deleting the
thin-bodied ones, because a turning-point candle is habitually small-bodied
and the body filter was removing exactly the zones worth watching. That leaves
a real question the system did not previously have to answer: given eleven
candidates, which one would a trader actually mark, and why?

The ordering below is the SMC one, strongest criterion first:

1. **Causation.** An order block IS the origin of a move that broke structure.
   A zone whose departure produced displacement and broke structure outranks
   any zone that merely looks tidy.
2. **Scope.** External structure owns the trend; internal structure is timing.
   An external-scope origin outranks an internal one.
3. **Displacement quality.** How decisively price left the zone.
4. **Location.** Supply belongs in premium, demand in discount. A demand zone
   sitting in premium is a worse place to buy regardless of its geometry.
5. **Freshness.** Untouched beats partially mitigated beats consumed.
6. **Proximity.** Only ever a tie-break. Nearest is not a reason -- a trader
   steps over a near zone to reach the one that owns the move.

Body ratio is deliberately absent from the ranking. It is recorded on the
evidence as a fact, and it may inform a human or an AI reviewer, but it is not
evidence about whether a zone matters.

Authority: descriptive. Ranking promotes nothing, creates no signal, and never
invents a zone the detector did not emit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from smc_desk.perception.poi_contract import (
    SPENT_STATES as CONTRACT_SPENT_STATES,
    canonicalize_poi_candidate,
)

# Revised once, under specs/POI_WEIGHT_REVISION_V1.yaml, which was sealed before
# the change was applied. Still NOT calibrated constants -- they are reasoned
# weights, one of which now has out-of-sample evidence behind it.
#
# Location is the largest weight because it is the only factor that has
# replicated on held-out data: +8.1% on BTCUSDT and +9.9% on ETHUSDT at 4h,
# roughly doubling expectancy. Its mechanism is positioning rather than
# geometry -- a supply zone high in its range has trapped buyers above it, which
# is where the resting orders are.
#
# Causation lost its position as the heaviest weight because it showed no
# measurable lift, and was deliberately not cut further. Absence of lift in the
# tests run so far is not proof of no value, and causation is what makes an
# object an order block rather than an arbitrary opposing candle -- it defines
# the population within which the location evidence was measured.
#
# Freshness is untouched. Nothing has tested it, so there is no basis for moving
# it in either direction.
WEIGHT_LOCATION = 0.30
WEIGHT_CAUSATION = 0.26
WEIGHT_SCOPE = 0.17
WEIGHT_DISPLACEMENT = 0.15
WEIGHT_FRESHNESS = 0.12

SPENT_STATES = {"consumed", "terminal", "invalidated", "mitigated"}


@dataclass(frozen=True)
class PoiScore:
    """One ranked POI with the reasons that placed it."""

    object_id: str
    direction: str
    price_low: float
    price_high: float
    timeframe: str
    score: float
    caused_structure_break: bool
    scope: str
    location: str
    freshness: str
    distance: float | None = None
    reasons: tuple[str, ...] = ()

    @property
    def midpoint(self) -> float:
        return (self.price_low + self.price_high) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "direction": self.direction,
            "price_low": self.price_low,
            "price_high": self.price_high,
            "timeframe": self.timeframe,
            "score": round(self.score, 4),
            "caused_structure_break": self.caused_structure_break,
            "scope": self.scope,
            "location": self.location,
            "freshness": self.freshness,
            "distance": self.distance,
            "reasons": list(self.reasons),
        }


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_location(
    direction: str,
    midpoint: float,
    equilibrium: float | None,
) -> str:
    """Premium, discount or equilibrium relative to the dealing range."""
    if equilibrium is None:
        return "unknown"
    if midpoint > equilibrium:
        return "premium"
    if midpoint < equilibrium:
        return "discount"
    return "equilibrium"


def location_alignment(direction: str, location: str) -> float:
    """Supply is wanted in premium, demand in discount.

    A zone on the wrong side of equilibrium is not disqualified -- price does
    trade from it -- but it is a worse place to act from, and the score says so.
    """
    if location in {"unknown", "equilibrium"}:
        return 0.5
    if direction == "bearish":
        return 1.0 if location == "premium" else 0.15
    if direction == "bullish":
        return 1.0 if location == "discount" else 0.15
    return 0.5


def freshness_of(poi: Mapping[str, Any]) -> tuple[str, float]:
    """Untouched > partial > spent."""
    explicit = str(poi.get("freshness") or "").lower()
    if explicit in CONTRACT_SPENT_STATES:
        return "spent", 0.0
    if explicit in {"partial", "partially_mitigated"}:
        return "partial", 0.5
    if explicit in {"touched", "first_touched"}:
        return "touched", 0.65
    if explicit in {"fresh", "untouched"}:
        return "fresh", 1.0
    activity = str(poi.get("activity_status") or "").lower()
    mitigation = str(poi.get("mitigation_status") or "untouched").lower()
    if activity in SPENT_STATES or mitigation == "full":
        return "spent", 0.0
    if mitigation == "partial":
        return "partial", 0.5
    return "fresh", 1.0


def score_poi(
    poi: Mapping[str, Any],
    *,
    equilibrium: float | None = None,
    current_price: float | None = None,
) -> PoiScore | None:
    """Score one POI candidate. Returns None when it carries no geometry."""
    candidate = canonicalize_poi_candidate(poi)
    low, high = _f(candidate.get("price_low")), _f(candidate.get("price_high"))
    if low is None or high is None:
        return None
    low, high = min(low, high), max(low, high)
    midpoint = (low + high) / 2.0
    direction = str(candidate.get("direction") or "unknown").lower()
    caused = bool(candidate.get("caused_structure_break"))
    scope = str(candidate.get("structure_scope") or "internal").lower()
    location = classify_location(direction, midpoint, equilibrium)
    freshness, freshness_value = freshness_of(candidate)

    reasons: list[str] = []
    causation_value = 1.0 if caused else 0.0
    if caused:
        reasons.append("origin of a displacement that broke structure")
    else:
        reasons.append("no confirmed structure-breaking departure")

    scope_value = 1.0 if scope == "external" else 0.45
    reasons.append(f"{scope} scope")

    measured_displacement = _f(candidate.get("displacement_strength"))
    displacement_value = min(
        1.0,
        max(0.0, measured_displacement if measured_displacement is not None else (0.8 if caused else 0.2)),
    )

    alignment = location_alignment(direction, location)
    reasons.append(
        f"{direction} zone in {location}"
        + ("" if alignment >= 1.0 else " (wrong side of equilibrium)")
    )
    reasons.append(f"{freshness}")

    score = (
        causation_value * WEIGHT_CAUSATION
        + scope_value * WEIGHT_SCOPE
        + displacement_value * WEIGHT_DISPLACEMENT
        + alignment * WEIGHT_LOCATION
        + freshness_value * WEIGHT_FRESHNESS
    )

    distance = abs(midpoint - current_price) if current_price is not None else None
    return PoiScore(
        object_id=str(candidate.get("object_id") or ""),
        direction=direction, price_low=low, price_high=high,
        timeframe=str(candidate.get("timeframe") or "unknown"),
        score=round(score, 6), caused_structure_break=caused, scope=scope,
        location=location, freshness=freshness, distance=distance,
        reasons=tuple(reasons),
    )


def rank_pois(
    pois: Iterable[Mapping[str, Any]],
    *,
    equilibrium: float | None = None,
    current_price: float | None = None,
    direction: str | None = None,
    include_spent: bool = False,
) -> list[PoiScore]:
    """Rank candidates strongest-first. Proximity is only a tie-break."""
    scored: list[PoiScore] = []
    for poi in pois or ():
        if not isinstance(poi, Mapping):
            continue
        result = score_poi(poi, equilibrium=equilibrium, current_price=current_price)
        if result is None:
            continue
        if direction and result.direction != direction:
            continue
        if not include_spent and result.freshness == "spent":
            continue
        scored.append(result)

    scored.sort(
        key=lambda s: (
            -s.score,
            s.distance if s.distance is not None else 0.0,
            s.object_id,
        )
    )
    return scored


def select_primary(
    pois: Iterable[Mapping[str, Any]],
    *,
    equilibrium: float | None = None,
    current_price: float | None = None,
    direction: str | None = None,
) -> tuple[PoiScore | None, list[PoiScore]]:
    """Return (primary, alternates).

    The alternates are kept deliberately: a trader who cannot say what the
    second choice was, and why it lost, has not really chosen.
    """
    ranked = rank_pois(
        pois, equilibrium=equilibrium, current_price=current_price, direction=direction
    )
    if not ranked:
        return None, []
    return ranked[0], ranked[1:]


__all__ = [
    "WEIGHT_CAUSATION",
    "WEIGHT_DISPLACEMENT",
    "WEIGHT_FRESHNESS",
    "WEIGHT_LOCATION",
    "WEIGHT_SCOPE",
    "PoiScore",
    "classify_location",
    "freshness_of",
    "location_alignment",
    "rank_pois",
    "score_poi",
    "select_primary",
]
