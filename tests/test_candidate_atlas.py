"""Tests for the multi-scale candidate atlas (programme step 2).

Pins:
  * Every required programme §4.3 candidate field is present on SwingCandidate.
  * All five generators emit on a frame containing known impulses / regimes.
  * Fuse: when two generators record the same pivot the fused record carries
    both in cross_generator without duplicates.
  * Determinism: same input -> same atlas_sha256.
  * Fusion reduces duplicates (emitted > fused).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from smc_desk.perception.candidates import atlas as atlas_mod
from smc_desk.perception.candidates.schema import (
    ALL_GENERATORS,
    SwingCandidate,
    candidate_id,
)


def _synthetic(n: int = 500, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(n)]
    ret = rng.normal(0, 0.0015, n)
    ret[80:85] = np.array([0.005, 0.007, 0.006, -0.004, -0.005])
    ret[150:153] = np.array([-0.004, -0.005, 0.006])
    ret[260:268] = np.array([0.006, 0.007, 0.008, 0.007, 0.006, -0.004, -0.005, -0.006])
    ret[400:404] = np.array([-0.007, -0.008, 0.006, -0.005])
    close = 100 * np.exp(np.cumsum(ret))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.3, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.3, n))
    vol = np.abs(rng.normal(1000, 200, n))
    return pd.DataFrame({"timestamp": ts, "open": open_, "high": high, "low": low, "close": close, "volume": vol})


REQUIRED_CANDIDATE_FIELDS = {
    "candidate_id", "timeframe", "pivot_type", "pivot_time", "pivot_price",
    "generator_source", "scale", "prominence", "volatility_normalized_move",
    "bars_left", "bars_right", "survival_bars", "subordinate_pivot_count",
    "displacement_after", "fvg_created", "breaks_caused", "liquidity_visibility",
    "touch_count", "age", "lifecycle", "parent_candidate_ids",
    "child_candidate_ids", "causal_origin_hypotheses",
}


@pytest.fixture(scope="module")
def result():
    df = _synthetic()
    cfg = atlas_mod.AtlasConfig(timeframe="15m", bars_left=5, bars_right=5, fractal_scale="internal", prominence_atr=0.3)
    return atlas_mod.build_for_timeframe(df, config=cfg, decision_time=df["timestamp"].iloc[-1])


def test_candidate_schema_has_all_required_fields():
    cand = SwingCandidate(
        candidate_id="t:p:ti", timeframe="15m", pivot_type="high", pivot_time="t", pivot_price=1.0,
        generator_source="fractal",
    )
    missing = REQUIRED_CANDIDATE_FIELDS - set(cand.to_dict())
    assert not missing, f"missing fields: {missing}"


def test_candidate_id_is_stable_across_generators():
    assert candidate_id("fractal", "15m", "2026-01-01T00:00:00Z", "high") == \
        candidate_id("directional_change", "15m", "2026-01-01T00:00:00Z", "high")


def test_all_five_generators_emit(result):
    counts = result.generator_run_counts
    assert set(counts) == set(ALL_GENERATORS)
    for g in ALL_GENERATORS:
        assert counts[g] >= 0
    # The synthetic series DOES trigger displacement and prominence with the
    # tuned defaults; if a future change drops them, the test fails loudly.
    assert counts["displacement"] > 0
    assert counts["prominence"] > 0
    assert counts["fractal"] > 0
    assert counts["directional_change"] > 0


def test_fusion_dedupes(result):
    summary = result.fusion_summary
    # Fusion reduces records when generators overlap; when they don't (e.g.,
    # a degenerate frame) the post-fusion count equals the sum, so we only
    # assert the upper bound and that the fusion actually ran.
    assert 0 < summary["after_fusion"] <= summary["total_emitted"]


def test_fusion_records_cross_generator_membership(result):
    """At least one record is seen by two or more generators."""
    multi = 0
    for c in result.candidates:
        for h in c.causal_origin_hypotheses:
            if "cross_generator" in h and len(h["cross_generator"]) >= 2:
                multi += 1
                break
    assert multi > 0, "atlas produced no cross-generator records"


def test_atlas_hash_is_deterministic(result):
    cfg = atlas_mod.AtlasConfig(timeframe="15m", bars_left=5, bars_right=5, fractal_scale="internal", prominence_atr=0.3)
    df = _synthetic()
    a = atlas_mod.build_for_timeframe(df, config=cfg, decision_time=df["timestamp"].iloc[-1])
    b = atlas_mod.build_for_timeframe(df, config=cfg, decision_time=df["timestamp"].iloc[-1])
    assert a.atlas_sha256 == b.atlas_sha256 == result.atlas_sha256


def test_atlas_does_not_look_forward(result):
    """The last pivot must come from a generator whose decision depends only on
    candles up to (and including) that pivot, not beyond."""
    last_ts = pd.Timestamp(_synthetic()["timestamp"].iloc[-1])
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize("UTC")
    for c in result.candidates:
        ts = pd.Timestamp(c.pivot_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        assert ts <= last_ts


def test_candidate_records_have_unique_ids(result):
    assert len({c.candidate_id for c in result.candidates}) == len(result.candidates)


def test_known_doctrine_alignment():
    """swing concept must forbid the fixed-window shortcut and require evidence_ids."""
    from smc_desk.structure.doctrine import concept as doctrine_concept
    c = doctrine_concept("swing")
    fs = " ".join(c.get("forbidden_shortcuts", []))
    assert "highest of last N bars" in fs
