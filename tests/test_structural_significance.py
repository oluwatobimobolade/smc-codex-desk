"""Tests for the structural significance layer.

Pins the contract that stops the detector firehose being treated as structure:

  * significance is relative to volatility (ATR) and to the active range;
  * an unconfirmed wick probe can never grade above ``noise``;
  * a body close that barely clears a level is not a major break, no matter
    how many basis points the detector's ``structure_break_min_bps`` allows;
  * grading is downgrade-shaped: it never invents or upgrades an object;
  * filtering drops ungraded objects rather than assuming significance.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from smc_desk.perception.significance import (
    MINIMUM_BREAK_DISPLACEMENT_ATR,
    SignificanceScore,
    average_true_range,
    filter_to_significant,
    grade_structure_break,
    grade_swing,
    grade_timeframe,
)


def _candles(n=30, high=101.0, low=99.0, close=100.0):
    return [{"high": high, "low": low, "close": close} for _ in range(n)]


def _swing(object_id: str, prominence: float):
    return {"object_id": object_id, "evidence": {"prominence_price": prominence}}


def _break(object_id: str, penetration: float, *, probe: bool = False):
    return {
        "object_id": object_id,
        "evidence": {
            "body_close_penetration": penetration,
            "is_unconfirmed_probe": probe,
        },
    }


# -- ATR ----------------------------------------------------------------------


def test_atr_is_positive_on_normal_candles():
    assert average_true_range(_candles()) == pytest.approx(2.0, rel=1e-6)


def test_atr_is_zero_without_candles():
    assert average_true_range([]) == 0.0


def test_cannot_grade_without_atr():
    """Zero volatility must produce an explicit non-grade, never a default pass."""
    score = grade_swing(_swing("s1", 10.0), atr=0.0)
    assert score.grade == "noise"
    assert "cannot grade without ATR" in score.reasons


# -- swing grading ------------------------------------------------------------


def test_large_swing_relative_to_atr_is_major():
    score = grade_swing(_swing("s1", 4.0), atr=2.0)     # 2.0x ATR
    assert score.grade == "major"
    assert score.is_tradeable_structure


def test_swing_can_be_major_on_range_share_in_quiet_volatility():
    """A move can matter because it carves out the range, not just because it is fast."""
    score = grade_swing(_swing("s1", 300.0), atr=100.0, range_size=1000.0)
    assert score.atr_multiple < 4.0
    assert score.range_fraction == pytest.approx(0.30)
    assert score.grade == "major"


def test_range_axis_is_suppressed_inside_a_tight_consolidation():
    """A wiggle filling a 2-ATR range is noise, not structure.

    Without this guard every move inside a tight consolidation occupies a
    large share of "the range" and gets promoted.
    """
    score = grade_swing(_swing("s1", 0.4), atr=4.0, range_size=4.0)
    assert score.range_fraction == 0.0
    assert score.grade == "noise"
    assert any("range axis suppressed" in r for r in score.reasons)


def test_small_swing_is_noise():
    score = grade_swing(_swing("s1", 0.2), atr=2.0)     # 0.1x ATR
    assert score.grade == "noise"
    assert not score.is_tradeable_structure


def test_grades_are_ordered_by_prominence():
    atr = 2.0
    grades = [grade_swing(_swing(f"s{i}", p), atr=atr).grade
              for i, p in enumerate([4.0, 1.8, 0.8, 0.1])]
    assert grades == ["major", "intermediate", "minor", "noise"]


# -- break grading ------------------------------------------------------------


def test_unconfirmed_probe_is_never_significant():
    score = grade_structure_break(_break("b1", 5.0, probe=True), atr=1.0)
    assert score.grade == "noise"
    assert "wick probe" in score.reasons[0]


def test_marginal_body_close_is_not_a_major_break():
    """The detector confirms on any body close; significance requires energy.

    4 bps on a 63,000 instrument is ~$25. Against a $255 ATR that is 0.1x —
    below the displacement floor, so it must not read as structure.
    """
    score = grade_structure_break(_break("b1", 25.0), atr=255.0)
    assert score.atr_multiple < MINIMUM_BREAK_DISPLACEMENT_ATR
    assert score.grade == "noise"


def test_displaced_break_is_major():
    score = grade_structure_break(_break("b1", 300.0), atr=255.0)
    assert score.grade == "major"
    assert score.is_tradeable_structure


def test_moderate_break_is_intermediate():
    score = grade_structure_break(_break("b1", 150.0), atr=255.0)   # 0.59x ATR
    assert score.grade == "intermediate"


# -- timeframe summary --------------------------------------------------------


def test_grade_timeframe_separates_signal_from_noise():
    summary = grade_timeframe(
        candles=_candles(high=102.0, low=98.0),        # ATR 4.0
        swings=[_swing("big", 8.0), _swing("small", 0.4)],
        structure_breaks=[_break("real", 6.0), _break("poke", 0.3)],
    )
    assert summary.counts["major"] == 2
    assert summary.counts["noise"] == 2
    assert {s.object_id for s in summary.tradeable} == {"big", "real"}


def test_summary_is_serialisable_and_explains_itself():
    summary = grade_timeframe(candles=_candles(), swings=[_swing("s1", 6.0)])
    payload = summary.to_dict()
    assert payload["schema"] == "structural_significance_summary_v1"
    assert payload["scores"][0]["reasons"], "every grade must carry its reason"


# -- filtering ----------------------------------------------------------------


def test_filter_drops_ungraded_objects():
    """An ungraded object is unproven; this layer must never widen the view."""
    objects = [{"object_id": "known"}, {"object_id": "unknown"}]
    scores = {"known": SignificanceScore("known", "major", 2.0, 0.3)}
    kept = filter_to_significant(objects, scores)
    assert [o["object_id"] for o in kept] == ["known"]


def test_filter_respects_minimum_grade():
    objects = [{"object_id": "a"}, {"object_id": "b"}]
    scores = {
        "a": SignificanceScore("a", "major", 2.0, 0.3),
        "b": SignificanceScore("b", "minor", 0.4, 0.02),
    }
    assert len(filter_to_significant(objects, scores, minimum_grade="major")) == 1
    assert len(filter_to_significant(objects, scores, minimum_grade="minor")) == 2


def test_filter_rejects_unknown_grade():
    with pytest.raises(ValueError):
        filter_to_significant([], {}, minimum_grade="enormous")


# -- object-shape tolerance ---------------------------------------------------


def test_grading_accepts_live_detector_objects_not_just_mappings():
    """Works on real SwingObjects as well as serialised evidence packs."""
    from smc_desk.perception.ontology import SwingEvidence

    class _Stub:
        object_id = "live_swing"
        evidence = SwingEvidence(
            bars_left=5, bars_right=5, prominence_atr_pct=0.0,
            is_external=True, scale_name="external", pivot_index=10,
            prominence_price=Decimal("8.0"),
        )

    score = grade_swing(_Stub(), atr=2.0)
    assert score.object_id == "live_swing"
    assert score.grade == "major"
