"""Counterfactual case harness (programme §29 counterfactual testing).

A counterfactual takes a known-good interpretation and applies a single
targeted mutation, then asserts the validators CATCH it with the expected
violation code. Each mutation is one logical change, so a failure pinpoints
which invariant the validator is missing.

The harness also supports the programme's "ablation" variant: remove one
feature class from the POI deterministic score and assert the rank ordering
is stable for the remaining POIs (ablation should not invert unrelated
ranks).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from smc_desk.validation import certify_interpretation


@dataclass
class Counterfactual:
    name: str
    mutate: Callable[[dict[str, Any]], dict[str, Any]]
    expected_violation_codes: tuple[str, ...]
    description: str = ""


def _set_path(obj: dict, path: str, value: Any) -> dict:
    """Immutable-ish deep set: returns a shallow-copied dict with path set."""
    out = dict(obj)
    parts = path.split(".")
    cur = out
    for p in parts[:-1]:
        cur[p] = dict(cur.get(p, {}))
        cur = cur[p]
    cur[parts[-1]] = value
    return out


# -- the canonical mutation set ---------------------------------------------

def cf_future_confirming_time() -> Counterfactual:
    return Counterfactual(
        name="cf_future_confirming_time",
        description="move the break confirming_candle_time past the cutoff",
        mutate=lambda interp: _set_path(
            interp, "accepted_breaks",
            [{**interp["accepted_breaks"][0],
              "confirming_candle_time": "2026-01-05T18:00:00Z"}]),
        expected_violation_codes=("FUTURE_DATA_LEAK",),
    )


def cf_ghost_origin() -> Counterfactual:
    return Counterfactual(
        name="cf_ghost_origin",
        description="replace the break origin with an id not in the pool",
        mutate=lambda interp: _set_path(
            interp, "accepted_breaks",
            [{**interp["accepted_breaks"][0], "origin_object_id": "ghost_origin"}]),
        expected_violation_codes=("BREAK_ORIGIN_NOT_GROUNDED",),
    )


def cf_drop_displacement() -> Counterfactual:
    return Counterfactual(
        name="cf_drop_displacement",
        description="empty the displacement evidence list on an accepted break",
        mutate=lambda interp: _set_path(
            interp, "accepted_breaks",
            [{**interp["accepted_breaks"][0], "displacement_evidence_ids": []}]),
        expected_violation_codes=("ACCEPTED_BREAK_WITHOUT_DISPLACEMENT",),
    )


def cf_naked_narrative() -> Counterfactual:
    return Counterfactual(
        name="cf_naked_narrative",
        description="add a narrative string with an ungrounded price claim",
        mutate=lambda interp: {**interp, "narrative": "price 8888.8888 ungrounded"},
        expected_violation_codes=("NARRATIVE_NAKED_CLAIM",),
    )


def all_counterfactuals() -> list[Counterfactual]:
    return [
        cf_future_confirming_time(),
        cf_ghost_origin(),
        cf_drop_displacement(),
        cf_naked_narrative(),
    ]


def run_counterfactual(
    cf: Counterfactual,
    *,
    base_interp: Mapping[str, Any],
    case: Mapping[str, Any],
    decision_time: str,
    cutoff: Mapping[str, str],
) -> dict[str, Any]:
    """Apply the mutation and return the certification envelope."""
    mutated = cf.mutate(dict(base_interp))
    return certify_interpretation(mutated, case, decision_time=decision_time,
                                  per_timeframe_cutoff=cutoff)


__all__ = [
    "Counterfactual",
    "all_counterfactuals",
    "run_counterfactual",
    "cf_future_confirming_time",
    "cf_ghost_origin",
    "cf_drop_displacement",
    "cf_naked_narrative",
]