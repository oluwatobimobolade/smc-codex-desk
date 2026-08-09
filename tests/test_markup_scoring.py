"""Tests for honest, fail-closed human-markup scoring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.build_markup_cohort import (
    _artifact,
    _definition_case_set_sha256,
    _json_bytes,
    _manifest_content_sha256,
    _sha256_bytes,
    _write_json,
)
from tools.score_markup_cohort import (
    _build_report,
    _metric,
    _score_bias,
    _score_decision,
    _score_draw,
    _score_poi,
    _score_range,
    _score_structure,
    score_case,
)


def _human(**overrides):
    payload = {
        "schema": "markup_annotation_v2",
        "case_id": "trend_01",
        "reviewer_id": "founder",
        "instrument": "BTCUSDT",
        "decision_time": "2026-06-15T12:00:00Z",
        "review_status": "COMPLETE",
        "review_completed_at": "2026-08-08T21:00:00Z",
        "htf_bias": "bullish",
        "context_timeframe": "4h",
        "dealing_range": {"high": 66000.0, "low": 62000.0, "timeframe": "4h"},
        "annotations": [],
        "liquidity": {
            "swept": [],
            "unswept": [],
            "expected_draw": {
                "price": 67000.0,
                "direction": "bullish",
                "timeframe": "4h",
            },
        },
        "primary_poi": {
            "price_low": 62500.0,
            "price_high": 63200.0,
            "timeframe": "4h",
            "kind": "order_block",
        },
        "would_you_trade_this": "watch",
    }
    payload.update(overrides)
    return payload


def _system(**overrides):
    payload = {
        "sealed": True,
        "generation_status": "COMPLETE",
        "decision_time": "2026-06-15T12:00:00Z",
        "htf_bias": "bullish",
        "context_timeframe": "4h",
        "dealing_range": {"high": 66010.0, "low": 61990.0, "timeframe": "4h"},
        "draw": {"target_price": 67005.0, "direction": "bullish", "target_kind": "equal_highs"},
        "significant_structure": {},
        "object_prices": {},
        "object_metadata": {},
        "atr": {"15m": 100.0, "1h": 200.0, "4h": 400.0, "1d": 1000.0},
        "market_state": {
            "state": "PRICE_AT_POI",
            "poi": {"primary_low": 62600.0, "primary_high": 63100.0},
        },
        "decision": {
            "classification": "watch",
            "source_state": "PRICE_AT_POI",
            "authority": "observe_only_no_signal_or_execution_authority",
        },
    }
    payload.update(overrides)
    return payload


def _mark(price, primitive="bos", ambiguous=False, timeframe="4h"):
    return {
        "primitive": primitive,
        "direction": "bullish",
        "scope": "external",
        "timeframe": timeframe,
        "price": price,
        "timestamp": "2026-06-15T00:00:00Z",
        "is_ambiguous": ambiguous,
    }


def _sealed_cohort(tmp_path: Path, *, markup: dict | None = None) -> Path:
    source = tmp_path / "source.csv"
    source.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    definition = tmp_path / "definition"
    definition.mkdir()
    definition_status = definition / "definition_set_status.json"
    definition_status.write_text('{"selection_status":"ANALYST_REVIEWED"}', encoding="utf-8")
    instructions = tmp_path / "REVIEW_INSTRUCTIONS.md"
    instructions.write_text("blind review\n", encoding="utf-8")

    case = tmp_path / "trend_01"
    charts = case / "charts"
    charts.mkdir(parents=True)
    metadata = {
        "instrument": "BTCUSDT",
        "decision_time": "2026-06-15T12:00:00Z",
        "regime_type": "trend",
    }
    definition_case = definition / "trend_01"
    definition_case.mkdir()
    (definition_case / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    artifacts = {
        "_sealed_system_answer.json": _write_json(case / "_sealed_system_answer.json", _system()),
        "metadata.json": _write_json(case / "metadata.json", metadata),
        "markup_template.json": _write_json(case / "markup_template.json", _human(review_status="IN_PROGRESS")),
    }
    chart_names = []
    for timeframe in ("1d", "4h", "1h", "15m"):
        name = f"BTCUSDT_{timeframe}_clean.png"
        path = charts / name
        path.write_bytes(f"PNG:{timeframe}".encode("utf-8"))
        artifacts[f"charts/{name}"] = _artifact(path)
        chart_names.append(name)
    if markup is not None:
        (case / "markup.json").write_text(json.dumps(markup), encoding="utf-8")

    source_slices = {
        timeframe: {
            "sha256": hashlib.sha256(timeframe.encode("utf-8")).hexdigest(),
            "row_count": 1,
            "first_timestamp": "2026-06-15T00:00:00Z",
            "last_timestamp": "2026-06-15T00:00:00Z",
        }
        for timeframe in ("1d", "4h", "1h", "15m")
    }
    seal_payload = {"artifacts": artifacts, "source_slices": source_slices}
    row = {
        "case_id": "trend_01",
        "status": "READY",
        "charts": chart_names,
        "sealed_answer_sha256": artifacts["_sealed_system_answer.json"]["sha256"],
        "artifacts": artifacts,
        "source_slices": source_slices,
        "case_seal_sha256": _sha256_bytes(_json_bytes(seal_payload)),
    }
    manifest = {
        "schema": "markup_cohort_v2",
        "validation_status": "VALID_FOR_EXPERT_DEVELOPMENT",
        "invalid_reasons": [],
        "definition_set": {
            "path": str(definition),
            "status_file_sha256": hashlib.sha256(definition_status.read_bytes()).hexdigest(),
            "all_case_ids": ["trend_01"],
            "all_case_set_sha256": _definition_case_set_sha256(definition, ["trend_01"]),
        },
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "size_bytes": source.stat().st_size,
        },
        "reviewer_id": "founder",
        "cohort_artifacts": {"REVIEW_INSTRUCTIONS.md": _artifact(instructions)},
        "case_count": 1,
        "ready_count": 1,
        "failed_count": 0,
        "cases": [row],
    }
    manifest["cohort_content_sha256"] = _manifest_content_sha256(manifest)
    _write_json(tmp_path / "cohort_manifest.json", manifest)
    return case


def test_metric_reports_precision_and_recall_separately():
    metric = _metric(tp=3, fp=7, fn=1)
    assert metric["precision"] == pytest.approx(0.3)
    assert metric["recall"] == pytest.approx(0.75)


def test_metric_is_none_only_when_undefined():
    undefined = _metric(0, 0, 0)
    total_failure = _metric(0, 3, 1)
    assert undefined["precision"] is None and undefined["recall"] is None and undefined["f1"] is None
    assert total_failure["precision"] == 0.0
    assert total_failure["recall"] == 0.0
    assert total_failure["f1"] == 0.0


def test_bias_agreement_and_timeframe_agreement_are_separate():
    scored = _score_bias(_human(), _system())
    assert scored["agree"] and scored["timeframe_agree"]
    assert _score_bias(_human(), _system(htf_bias="bearish"))["agree"] is False


def test_blank_human_bias_never_counts_as_agreement():
    assert _score_bias(_human(htf_bias=""), _system())["agree"] is False


def test_range_agrees_within_atr_tolerance():
    scored = _score_range(_human(), _system(), atr=200.0)
    assert scored["scored"] and scored["high_agree"] and scored["low_agree"]


def test_range_disagrees_outside_tolerance():
    scored = _score_range(
        _human(), _system(dealing_range={"high": 69000.0, "low": 58000.0}), atr=200.0
    )
    assert scored["high_agree"] is False and scored["low_agree"] is False


def test_blank_human_range_is_unscored_not_failed():
    scored = _score_range(
        _human(dealing_range={"high": None, "low": None}), _system(), atr=200.0
    )
    assert scored["scored"] is False


def test_tolerance_scales_with_volatility():
    system = _system(dealing_range={"high": 66400.0, "low": 62000.0})
    assert _score_range(_human(), system, atr=1000.0)["high_agree"] is True
    assert _score_range(_human(), system, atr=100.0)["high_agree"] is False


def test_matched_structure_counts_as_a_true_positive():
    human = _human(annotations=[_mark(64000.0)])
    system = _system(significant_structure={"4h": ["b1"]}, object_prices={"4h:b1": 64010.0})
    scored = _score_structure(human, system, atr=200.0)
    assert scored["metrics"]["true_positives"] == 1
    assert scored["metrics"]["false_negatives"] == 0


def test_missed_and_invented_structure_are_separate_errors():
    human = _human(annotations=[_mark(64000.0)])
    system = _system(significant_structure={"4h": ["x1"]}, object_prices={"4h:x1": 60000.0})
    scored = _score_structure(human, system, atr=200.0)
    assert scored["metrics"]["false_negatives"] == 1
    assert scored["metrics"]["false_positives"] == 1


def test_invented_structure_has_zero_not_undefined_f1():
    system = _system(
        significant_structure={"4h": ["x1", "x2", "x3"]},
        object_prices={"4h:x1": 10.0, "4h:x2": 20.0, "4h:x3": 30.0},
    )
    scored = _score_structure(_human(annotations=[]), system, atr=200.0)
    assert scored["metrics"]["precision"] == 0.0
    assert scored["metrics"]["f1"] is None  # recall is undefined when the human marked nothing


def test_ambiguous_human_marks_do_not_punish_the_system():
    scored = _score_structure(_human(annotations=[_mark(64000.0, ambiguous=True)]), _system(), 200.0)
    assert scored["metrics"]["false_negatives"] == 0
    assert scored["human_ambiguous"] == 1


def test_one_system_mark_cannot_satisfy_two_human_marks():
    human = _human(annotations=[_mark(64000.0), _mark(64020.0)])
    system = _system(significant_structure={"4h": ["b1"]}, object_prices={"4h:b1": 64010.0})
    scored = _score_structure(human, system, atr=200.0)
    assert scored["metrics"]["true_positives"] == 1
    assert scored["metrics"]["false_negatives"] == 1


def test_structure_uses_the_marks_own_timeframe_atr():
    human = _human(annotations=[_mark(1000.0, timeframe="15m")], context_timeframe="1d")
    system = _system(
        significant_structure={"15m": ["b1"]},
        object_prices={"15m:b1": 1100.0},
        object_metadata={
            "15m:b1": {
                "primitive": "bos",
                "direction": "bullish",
                "scope": "external",
                "timeframe": "15m",
            }
        },
    )
    scored = _score_structure(human, system, atr={"15m": 100.0, "1d": 1000.0})
    assert scored["metrics"]["true_positives"] == 0


def test_close_price_cannot_hide_semantic_mismatch():
    human = _human(annotations=[_mark(64000.0, primitive="bos")])
    system = _system(
        significant_structure={"4h": ["b1"]},
        object_prices={"4h:b1": 64000.0},
        object_metadata={
            "4h:b1": {
                "primitive": "choch",
                "direction": "bearish",
                "scope": "external",
                "timeframe": "4h",
            }
        },
    )
    scored = _score_structure(human, system, atr=200.0)
    assert scored["metrics"]["true_positives"] == 0


def test_sweeps_are_not_silently_counted_as_structure_false_negatives():
    scored = _score_structure(_human(annotations=[_mark(64000.0, primitive="sweep")]), _system(), 200.0)
    assert scored["metrics"]["false_negatives"] == 0
    assert scored["human_sweeps_deferred_to_liquidity_review"] == 1


def test_draw_and_poi_scoring_respect_blank_answers():
    assert _score_draw(_human(), _system(), atr=200.0)["agree"] is True
    blank_draw = _human(liquidity={"expected_draw": {"price": None}})
    assert _score_draw(blank_draw, _system(), atr=200.0)["scored"] is False
    assert _score_poi(_human(), _system())["overlap"] is True
    blank_poi = _human(primary_poi={"price_low": None, "price_high": None})
    assert _score_poi(blank_poi, _system())["scored"] is False


def test_decision_agreement_is_explicit():
    assert _score_decision(_human(), _system())["agree"] is True
    assert _score_decision(_human(would_you_trade_this="no"), _system())["agree"] is False


def test_aggregate_denominators_exclude_unscored_dimensions():
    structure = {"metrics": {"true_positives": 0, "false_positives": 0, "false_negatives": 0}}
    base = {
        "status": "SCORED",
        "bias": {"scored": True, "agree": True, "timeframe_agree": True},
        "structure": structure,
        "draw": {"scored": False},
        "poi": {"scored": False},
        "decision": {"scored": True, "agree": True},
    }
    results = [
        {**base, "case_id": "a", "dealing_range": {"scored": False}},
        {
            **base,
            "case_id": "b",
            "dealing_range": {"scored": True, "high_agree": True, "low_agree": False},
        },
    ]
    report = _build_report(Path("/cohort"), results)
    assert report["summary"]["range_high_agreement"] == {"agreed": 1, "scored": 1, "rate": 1.0}
    assert report["summary"]["draw_agreement"]["scored"] == 0


def test_case_without_completed_markup_is_not_scored(tmp_path: Path):
    case = _sealed_cohort(tmp_path)
    assert score_case(case, "markup.json") is None


def test_only_filling_bias_is_still_incomplete(tmp_path: Path):
    markup = _human(
        review_status="IN_PROGRESS",
        review_completed_at="",
        context_timeframe="",
        would_you_trade_this="",
    )
    case = _sealed_cohort(tmp_path, markup=markup)
    result = score_case(case, "markup.json")
    assert result["status"] == "INCOMPLETE"
    assert "review_status" in result["reason"]


def test_future_human_annotation_is_refused(tmp_path: Path):
    markup = _human(
        annotations=[
            {
                **_mark(64000.0),
                "timestamp": "2026-06-15T12:15:00Z",
            }
        ]
    )
    case = _sealed_cohort(tmp_path, markup=markup)

    result = score_case(case, "markup.json")

    assert result["status"] == "INCOMPLETE"
    assert "after the decision time" in result["reason"]


def test_complete_case_scores_every_dimension(tmp_path: Path):
    case = _sealed_cohort(tmp_path, markup=_human())
    result = score_case(case, "markup.json")
    assert result["status"] == "SCORED"
    assert result["regime"] == "trend"
    assert result["decision"]["agree"] is True
    for dimension in ("bias", "dealing_range", "structure", "draw", "poi", "decision"):
        assert dimension in result


def test_direct_case_scoring_refuses_invalid_parent_cohort(tmp_path: Path):
    case = tmp_path / "trend_01"
    case.mkdir()
    (tmp_path / "cohort_manifest.json").write_text(
        '{"validation_status":"INVALID_DO_NOT_MARK","invalid_reasons":["quarantined"]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="INVALID_DO_NOT_MARK"):
        score_case(case, "markup.json")
