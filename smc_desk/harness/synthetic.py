"""Synthetic market-data and case generators for the perception harness
(programme §19, §29).

Deterministic, hand-labelled market scenarios with KNOWN expected
interpretations, so the structure machines and validators can be tested
against ground truth rather than only internal consistency.

Each generator returns a ``SyntheticCase`` carrying (case, expected
interpretation, decision_time, expected_certified, expected_violation_codes).
The positive cases assert the validators CERTIFY; the negative cases assert
the validators CATCH a specific code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd


@dataclass
class SyntheticCase:
    name: str
    description: str
    case: dict[str, Any]
    expected_interpretation: dict[str, Any]
    decision_time: str
    per_timeframe_cutoff: dict[str, str] = field(default_factory=dict)
    expected_certified: bool = True
    expected_violation_codes: tuple[str, ...] = ()


def _candle(oid, ts, o, h, l, c, tf, lifecycle="CANDIDATE"):
    return {"object_id": oid, "confirmed_at": ts, "timeframe": tf,
            "open": o, "high": h, "low": l, "close": c,
            "pivot_price": c, "lifecycle": lifecycle}


def bullish_bos_accepted() -> SyntheticCase:
    """Clean 4h bullish BOS: protected point pp1 (07:00), origin s10 (08:00),
    impulse c1..c3, break br1 at 12:00. Expected: CERTIFIED."""
    swings = [
        _candle("pp1", "2026-01-05T07:00:00Z", 97.0, 98.5, 96.5, 98.0, "4h", "PROTECTED"),
        _candle("s10", "2026-01-05T08:00:00Z", 98.0, 99.5, 97.8, 99.0, "4h", "STRUCTURAL"),
        _candle("c1", "2026-01-05T10:00:00Z", 99.0, 100.5, 98.9, 100.4, "4h"),
        _candle("c2", "2026-01-05T11:00:00Z", 100.4, 101.2, 100.3, 101.1, "4h"),
        _candle("c3", "2026-01-05T12:00:00Z", 101.1, 102.0, 101.0, 101.9, "4h"),
    ]
    case = {"candidate_objects": {"4h": {"swings": swings}}, "formal_structure_graph": {}}
    interp = {
        "accepted_breaks": [{
            "object_id": "br1", "timeframe": "4h", "direction": "bullish",
            "origin_object_id": "s10", "breaking_candidate_id": "c3",
            "accepted": True,
            "displacement_evidence_ids": ["c1", "c2", "c3"],
            "confirming_candle_time": "2026-01-05T12:00:00Z",
            "evidence_ids": ["s10", "c3"],
        }],
        "protected_point": {"object_id": "pp1", "timeframe": "4h",
                            "evidence_ids": ["pp1"]},
        "summary": "bullish break accepted above the 4h structural high",
    }
    return SyntheticCase(
        name="bullish_bos_accepted",
        description="clean 4h bullish BOS with grounded origin + protected point",
        case=case, expected_interpretation=interp,
        decision_time="2026-01-05T13:00:00Z",
        per_timeframe_cutoff={"4h": "2026-01-05T13:00:00Z"},
        expected_certified=True,
    )


def future_leak_case() -> SyntheticCase:
    """Negative: break confirming_candle_time past the cutoff -> FUTURE_DATA_LEAK."""
    base = bullish_bos_accepted()
    interp = {**base.expected_interpretation,
              "accepted_breaks": [{**base.expected_interpretation["accepted_breaks"][0],
                                   "confirming_candle_time": "2026-01-05T18:00:00Z"}]}
    return SyntheticCase(
        name="future_leak",
        description="break confirming time past the decision cutoff",
        case=base.case, expected_interpretation=interp,
        decision_time="2026-01-05T13:00:00Z",
        per_timeframe_cutoff={"4h": "2026-01-05T13:00:00Z"},
        expected_certified=False,
        expected_violation_codes=("FUTURE_DATA_LEAK",),
    )


def nongrounded_origin_case() -> SyntheticCase:
    """Negative: break origin not in the candidate pool -> BREAK_ORIGIN_NOT_GROUNDED."""
    base = bullish_bos_accepted()
    interp = {**base.expected_interpretation,
              "accepted_breaks": [{**base.expected_interpretation["accepted_breaks"][0],
                                   "origin_object_id": "ghost_origin"}]}
    return SyntheticCase(
        name="nongrounded_origin",
        description="break origin not present in candidate pool",
        case=base.case, expected_interpretation=interp,
        decision_time=base.decision_time,
        per_timeframe_cutoff=base.per_timeframe_cutoff,
        expected_certified=False,
        expected_violation_codes=("BREAK_ORIGIN_NOT_GROUNDED",),
    )


def lifecycle_contradiction_case() -> SyntheticCase:
    """Negative: candidate simultaneously PROTECTED and BROKEN -> LIFECYCLE_CONTRADICTION."""
    base = bullish_bos_accepted()
    swings = base.case["candidate_objects"]["4h"]["swings"]
    case = {**base.case, "candidate_objects": {"4h": {"swings": [
        {**swings[0], "lifecycle": "PROTECTED BROKEN"}, *swings[1:],
    ]}}}
    return SyntheticCase(
        name="lifecycle_contradiction",
        description="candidate marked both PROTECTED and BROKEN",
        case=case, expected_interpretation=base.expected_interpretation,
        decision_time=base.decision_time,
        per_timeframe_cutoff=base.per_timeframe_cutoff,
        expected_certified=False,
        expected_violation_codes=("LIFECYCLE_CONTRADICTION",),
    )


def accepted_break_without_displacement_case() -> SyntheticCase:
    """Negative: accepted break missing displacement evidence -> ACCEPTED_BREAK_WITHOUT_DISPLACEMENT."""
    base = bullish_bos_accepted()
    interp = {**base.expected_interpretation,
              "accepted_breaks": [{**base.expected_interpretation["accepted_breaks"][0],
                                   "displacement_evidence_ids": []}]}
    return SyntheticCase(
        name="accepted_break_without_displacement",
        description="break marked accepted with no displacement evidence",
        case=base.case, expected_interpretation=interp,
        decision_time=base.decision_time,
        per_timeframe_cutoff=base.per_timeframe_cutoff,
        expected_certified=False,
        expected_violation_codes=("ACCEPTED_BREAK_WITHOUT_DISPLACEMENT",),
    )


def all_cases() -> list[SyntheticCase]:
    return [
        bullish_bos_accepted(),
        future_leak_case(),
        nongrounded_origin_case(),
        lifecycle_contradiction_case(),
        accepted_break_without_displacement_case(),
    ]


def stepped_random_walk(n: int, seed: int, *, impulses: tuple[tuple[int, int, float], ...] = ()) -> pd.DataFrame:
    """Deterministic walk with optional injected impulses (start, length, mag)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    ts = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(n)]
    ret = rng.normal(0, 0.0015, n)
    for start, length, mag in impulses:
        ret[start:start + length] = mag
    close = 100 * np.exp(np.cumsum(ret))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.3, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.3, n))
    return pd.DataFrame({"timestamp": ts, "open": open_, "high": high,
                         "low": low, "close": close,
                         "volume": np.abs(rng.normal(1000, 200, n))})


__all__ = [
    "SyntheticCase",
    "all_cases",
    "bullish_bos_accepted",
    "future_leak_case",
    "nongrounded_origin_case",
    "lifecycle_contradiction_case",
    "accepted_break_without_displacement_case",
    "stepped_random_walk",
]