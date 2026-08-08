"""Tests for markup cohort scoring.

This is the harness that finally measures perception against a human. Its
correctness matters as much as the perception code: a scorer that flatters the
system produces a number worse than no number at all.

Pinned here:

  * blinding is structural -- a case with no completed markup is not scored;
  * a miss and a false positive are counted separately, because a system that
    marks everything must not score well;
  * tolerance is ATR-relative, so "the same level" scales with volatility;
  * blank human fields are unscored, never counted as system failures;
  * ambiguous human marks never punish the system.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.score_markup_cohort import (
    _metric,
    _score_bias,
    _score_draw,
    _score_poi,
    _score_range,
    _score_structure,
    score_case,
)


def _human(**overrides):
    payload = {
        "case_id": "trend_01",
        "htf_bias": "bullish",
        "context_timeframe": "4h",
        "dealing_range": {"high": 66000.0, "low": 62000.0},
        "annotations": [],
        "liquidity": {"expected_draw": {"price": 67000.0, "direction": "bullish"}},
        "primary_poi": {"price_low": 62500.0, "price_high": 63200.0},
        "would_you_trade_this": "watch",
    }
    payload.update(overrides)
    return payload


def _system(**overrides):
    payload = {
        "htf_bias": "bullish",
        "context_timeframe": "4h",
        "dealing_range": {"high": 66010.0, "low": 61990.0},
        "draw": {"target_price": 67005.0, "direction": "bullish", "target_kind": "equal_highs"},
        "significant_structure": {},
        "object_prices": {},
        "market_state": {"state": "PRICE_AT_POI",
                         "poi": {"primary_low": 62600.0, "primary_high": 63100.0}},
    }
    payload.update(overrides)
    return payload


# -- metric arithmetic ---------------------------------------------------------


def test_metric_reports_precision_and_recall_separately():
    m = _metric(tp=3, fp=7, fn=1)
    assert m["precision"] == pytest.approx(0.3)
    assert m["recall"] == pytest.approx(0.75)


def test_metric_is_none_rather_than_zero_when_undefined():
    """No marks at all is 'not measured', not 'scored zero'."""
    m = _metric(0, 0, 0)
    assert m["precision"] is None and m["recall"] is None and m["f1"] is None


# -- bias ----------------------------------------------------------------------


def test_bias_agreement_and_timeframe_agreement_are_separate():
    scored = _score_bias(_human(), _system())
    assert scored["agree"] and scored["timeframe_agree"]

    disagree = _score_bias(_human(), _system(htf_bias="bearish"))
    assert disagree["agree"] is False


def test_blank_human_bias_never_counts_as_agreement():
    scored = _score_bias(_human(htf_bias=""), _system())
    assert scored["agree"] is False


# -- range ---------------------------------------------------------------------


def test_range_agrees_within_atr_tolerance():
    scored = _score_range(_human(), _system(), atr=200.0)
    assert scored["scored"] and scored["high_agree"] and scored["low_agree"]


def test_range_disagrees_outside_tolerance():
    scored = _score_range(_human(), _system(dealing_range={"high": 69000.0, "low": 58000.0}), atr=200.0)
    assert scored["high_agree"] is False and scored["low_agree"] is False


def test_blank_human_range_is_unscored_not_failed():
    """A structureless chart with no range is a correct human answer."""
    scored = _score_range(_human(dealing_range={"high": None, "low": None}), _system(), atr=200.0)
    assert scored["scored"] is False
    assert "blank" in scored["reason"]


def test_tolerance_scales_with_volatility():
    """The same 400-point gap passes on a volatile chart and fails on a quiet one."""
    system = _system(dealing_range={"high": 66400.0, "low": 62000.0})
    assert _score_range(_human(), system, atr=1000.0)["high_agree"] is True
    assert _score_range(_human(), system, atr=100.0)["high_agree"] is False


# -- structure -----------------------------------------------------------------


def _mark(price, primitive="bos", ambiguous=False):
    return {"primitive": primitive, "direction": "bullish", "price": price,
            "timestamp": "2026-06-15T00:00:00Z", "is_ambiguous": ambiguous}


def test_matched_structure_counts_as_a_true_positive():
    human = _human(annotations=[_mark(64000.0)])
    system = _system(significant_structure={"4h": ["b1"]}, object_prices={"b1": 64010.0})
    scored = _score_structure(human, system, atr=200.0)
    assert scored["metrics"]["true_positives"] == 1
    assert scored["metrics"]["false_negatives"] == 0


def test_missed_structure_is_a_false_negative_and_is_named():
    human = _human(annotations=[_mark(64000.0)])
    scored = _score_structure(human, _system(), atr=200.0)
    assert scored["metrics"]["false_negatives"] == 1
    assert scored["missed_by_system"][0]["price"] == 64000.0


def test_invented_structure_is_a_false_positive():
    """Marking everything must not score well."""
    system = _system(
        significant_structure={"4h": ["x1", "x2", "x3"]},
        object_prices={"x1": 10.0, "x2": 20.0, "x3": 30.0},
    )
    scored = _score_structure(_human(annotations=[]), system, atr=200.0)
    assert scored["metrics"]["false_positives"] == 3
    assert scored["metrics"]["precision"] == 0.0


def test_ambiguous_human_marks_do_not_punish_the_system():
    human = _human(annotations=[_mark(64000.0, ambiguous=True)])
    scored = _score_structure(human, _system(), atr=200.0)
    assert scored["metrics"]["false_negatives"] == 0
    assert scored["human_ambiguous"] == 1


def test_one_system_mark_cannot_satisfy_two_human_marks():
    human = _human(annotations=[_mark(64000.0), _mark(64020.0)])
    system = _system(significant_structure={"4h": ["b1"]}, object_prices={"b1": 64010.0})
    scored = _score_structure(human, system, atr=200.0)
    assert scored["metrics"]["true_positives"] == 1
    assert scored["metrics"]["false_negatives"] == 1


# -- draw and POI --------------------------------------------------------------


def test_draw_agreement_within_tolerance():
    assert _score_draw(_human(), _system(), atr=200.0)["agree"] is True


def test_blank_human_draw_is_unscored():
    human = _human(liquidity={"expected_draw": {"price": None}})
    assert _score_draw(human, _system(), atr=200.0)["scored"] is False


def test_poi_overlap_is_detected():
    scored = _score_poi(_human(), _system())
    assert scored["overlap"] is True
    assert scored["overlap_fraction"] > 0


def test_no_system_poi_is_recorded_as_such():
    system = _system(market_state={"state": "ACCEPTED_DISPLACEMENT", "poi": {}})
    scored = _score_poi(_human(), system)
    assert scored["system_had_poi"] is False
    assert scored["overlap"] is False


def test_non_overlapping_poi_scores_false():
    system = _system(market_state={"poi": {"primary_low": 70000.0, "primary_high": 71000.0}})
    assert _score_poi(_human(), system)["overlap"] is False


# -- blinding ------------------------------------------------------------------


def test_case_without_completed_markup_is_not_scored(tmp_path: Path):
    """Blinding is structural: no markup file means no score."""
    case = tmp_path / "trend_01"
    case.mkdir()
    (case / "_sealed_system_answer.json").write_text(json.dumps(_system()))
    assert score_case(case, "markup.json") is None


def test_case_with_blank_bias_is_flagged_incomplete(tmp_path: Path):
    case = tmp_path / "trend_01"
    case.mkdir()
    (case / "_sealed_system_answer.json").write_text(json.dumps(_system()))
    (case / "markup.json").write_text(json.dumps(_human(htf_bias="")))
    result = score_case(case, "markup.json")
    assert result["status"] == "INCOMPLETE"


def test_complete_case_scores_every_dimension(tmp_path: Path):
    case = tmp_path / "trend_01"
    case.mkdir()
    (case / "metadata.json").write_text(json.dumps({"regime_type": "trend"}))
    (case / "_sealed_system_answer.json").write_text(json.dumps(_system()))
    (case / "markup.json").write_text(json.dumps(_human()))
    result = score_case(case, "markup.json")
    assert result["status"] == "SCORED"
    assert result["regime"] == "trend"
    for dimension in ("bias", "dealing_range", "structure", "draw", "poi", "decision"):
        assert dimension in result
