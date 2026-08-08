"""Tests for the end-to-end perception-programme run scaffolding (step 10).

Pins the programme §10/§17/§30 rule: while the Constitution is PROPOSED,
the run MUST refuse to CERTIFY even when the validators pass, and must
report the unresolved contested decisions as the abstention reason.

When the doctrine becomes authoritative (simulated here by monkeypatching
``is_authoritative``), a clean interpretation IS certified. This is the one-
flag path to the live AI run (programme step 10).
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from smc_desk.harness import synthetic
from smc_desk.perception.programme_run import run_perception_programme
from smc_desk.structure import doctrine as doctrine_mod


def _run(positive=True):
    case = synthetic.bullish_bos_accepted()
    return run_perception_programme(
        case=case.case,
        candidate_pool=case.case["candidate_objects"]["4h"]["swings"],
        decision_time=case.decision_time,
        per_timeframe_cutoff=case.per_timeframe_cutoff,
        interpretation=case.expected_interpretation,
    )


def test_run_abstains_because_doctrine_is_proposed():
    """The Constitution is PROPOSED -> no CERTIFIED output, even with a clean
    interpretation that passes every deterministic validator."""
    env = _run()
    assert env.doctrine_authoritative is False
    assert env.certification["certified"] is False
    assert env.certification["abstained"] is True
    assert "PROPOSED" in env.abstention_reason
    # All 14 contested decisions are listed as unresolved.
    assert len(env.contested_decisions_unresolved) == 14


def test_run_reports_validator_pass_under_the_abstention():
    """Even while abstaining, the envelope reports that the validators passed
    (blocks=0, errors=0), so the only blocker is doctrine authority."""
    env = _run()
    assert env.certification["summary"]["blocks"] == 0
    assert env.certification["summary"]["errors"] == 0


def test_run_certifies_when_doctrine_becomes_authoritative(monkeypatch):
    """The one-flag path: once the doctrine is authoritative, a clean
    interpretation is CERTIFIED. This is what step 10 unlocks."""
    import smc_desk.perception.programme_run as pr
    monkeypatch.setattr(pr, "is_authoritative", lambda load=None: True)
    monkeypatch.setattr(pr, "unresolved_contested_decisions", lambda load=None: [])
    env = _run()
    assert env.doctrine_authoritative is True
    assert env.certification["certified"] is True
    assert env.certification["abstained"] is False


def test_run_still_certifies_false_when_validators_fail_even_if_authoritative(monkeypatch):
    """Doctrine authority is necessary but not sufficient: a violated
    interpretation stays non-certified even after adjudication."""
    import smc_desk.perception.programme_run as pr
    monkeypatch.setattr(pr, "is_authoritative", lambda load=None: True)
    monkeypatch.setattr(pr, "unresolved_contested_decisions", lambda load=None: [])
    case = synthetic.future_leak_case()
    env = run_perception_programme(
        case=case.case,
        candidate_pool=case.case["candidate_objects"]["4h"]["swings"],
        decision_time=case.decision_time,
        per_timeframe_cutoff=case.per_timeframe_cutoff,
        interpretation=case.expected_interpretation,
    )
    assert env.certification["certified"] is False
    assert any(v["code"] == "FUTURE_DATA_LEAK" for v in env.certification["violations"])


def test_run_envelope_carries_atlas_and_context_hashes():
    env = _run()
    assert env.atlas_sha256
    assert env.context_sha256
    assert env.candidate_payload_design == "anchor"
    assert env.retrieval_tools_advertised is False
    assert env.retrieval_tools_executed is False
    assert env.interpretation_source == "SUPPLIED_REPLAY_FIXTURE"


def test_envelope_is_serialisable():
    env = _run()
    d = env.to_dict()
    assert d["schema"] == "perception_run_envelope_v2"
    assert "certification" in d


def test_programme_builds_real_atlas_under_decision_cutoff():
    case = synthetic.bullish_bos_accepted()
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    timestamps = pd.date_range(start, periods=120, freq="15min")
    close = 100 + np.sin(np.arange(120) / 4) + np.arange(120) * 0.02
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": np.maximum(open_, close) + 0.4,
        "low": np.minimum(open_, close) - 0.4,
        "close": close,
        "volume": np.full(120, 1000.0),
    })
    decision_time = (timestamps[-1] + timedelta(minutes=15)).isoformat()
    envelope = run_perception_programme(
        case=case.case,
        timeframe_dfs={"15m": frame},
        decision_time=decision_time,
        per_timeframe_cutoff={"15m": decision_time},
        interpretation=case.expected_interpretation,
    )
    assert envelope.atlas_built is True
    assert envelope.atlas_candidate_counts["15m"] > 0
    assert envelope.atlas_sha256
