"""Tests for the synthetic / metamorphic / counterfactual harness (step 8).

Programme §19 + §29: test against ground truth, with metamorphic relations and
counterfactual mutations. Each test asserts a known direction, so a validator
regression is pinpointed.
"""
from __future__ import annotations

import pytest

from smc_desk.harness import counterfactual, metamorphic, synthetic
from smc_desk.perception.candidates import atlas as atlas_mod
from smc_desk.validation import certify_interpretation


def _cert(c):
    return certify_interpretation(
        c.expected_interpretation, c.case,
        decision_time=c.decision_time,
        per_timeframe_cutoff=c.per_timeframe_cutoff,
    )


# -- synthetic ground-truth cases --------------------------------------------

def test_synthetic_positive_case_is_certified():
    c = synthetic.bullish_bos_accepted()
    res = _cert(c)
    assert res["certified"] is True
    assert res["summary"]["blocks"] == 0


@pytest.mark.parametrize("case", synthetic.all_cases()[1:])
def test_synthetic_negative_cases_are_caught_with_expected_code(case):
    res = _cert(case)
    assert res["certified"] is False
    got = {v["code"] for v in res["violations"]}
    assert set(case.expected_violation_codes) <= got


# -- metamorphic relations ---------------------------------------------------

def test_m1_determinism():
    df = synthetic.stepped_random_walk(300, 7, impulses=((80, 3, 0.005), (150, 3, -0.004)))
    cfg = atlas_mod.AtlasConfig(timeframe="15m", bars_left=5, bars_right=5, prominence_atr=0.3)
    assert metamorphic.m1_determinism(df, cfg)


def test_m2_recency_invariance():
    df = synthetic.stepped_random_walk(300, 7, impulses=((80, 3, 0.005),))
    cfg = atlas_mod.AtlasConfig(timeframe="15m", bars_left=5, bars_right=5, prominence_atr=0.3)
    assert metamorphic.m2_recency_invariance(df, cfg)


def test_m3_scale_monotonicity():
    df = synthetic.stepped_random_walk(300, 7, impulses=((80, 3, 0.005),))
    assert metamorphic.m3_scale_monotonicity(df)


def test_m4_abstention_monotonicity():
    c = synthetic.bullish_bos_accepted()
    assert metamorphic.m4_abstention_monotonicity(
        c.case, c.expected_interpretation, c.decision_time, c.per_timeframe_cutoff)


def test_m5_anchor_preservation():
    case = {
        "candidate_objects": {"15m": {"swings": [
            {"object_id": f"s{i}", "confirmed_at": "2026-01-05T00:00:00Z",
             "timeframe": "15m", "pivot_price": 100 + i} for i in range(50)]}},
        "formal_structure_graph": {"protected_point": {"object_id": "s10"}},
    }
    assert metamorphic.m5_anchor_preservation(case)


# -- counterfactual mutations ------------------------------------------------

@pytest.mark.parametrize("cf", counterfactual.all_counterfactuals())
def test_counterfactuals_caught_with_expected_code(cf):
    base = synthetic.bullish_bos_accepted()
    env = counterfactual.run_counterfactual(
        cf, base_interp=base.expected_interpretation, case=base.case,
        decision_time=base.decision_time, cutoff=base.per_timeframe_cutoff,
    )
    assert env["certified"] is False
    got = {v["code"] for v in env["violations"]}
    assert set(cf.expected_violation_codes) <= got


# -- expert truth-label integration (step 9 bridge) --------------------------

def test_synthetic_cases_carry_expected_certification_flag():
    """Every synthetic case asserts the direction the validator should return,
    so the suite doubles as expert-labelled ground truth (step 9)."""
    for c in synthetic.all_cases():
        res = _cert(c)
        assert res["certified"] == c.expected_certified


def test_harness_is_deterministic_across_runs():
    """Re-running the positive case twice yields identical certification."""
    c = synthetic.bullish_bos_accepted()
    a = _cert(c)
    b = _cert(c)
    assert a == b