"""Truth, immutability, and production-shape tests for markup cohorts."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import tools.build_markup_cohort as builder
from tools.build_markup_cohort import (
    CohortGenerationError,
    _case_ids_sha256,
    _definition_case_set_sha256,
    _evaluation_object_index,
    _slice_at,
    build_cohort,
)
from tools.score_markup_cohort import _assert_cohort_scoreable, score_case


def _frame(periods: int = 2200) -> pd.DataFrame:
    timestamps = pd.date_range("2026-05-20T00:00:00Z", periods=periods, freq="15min")
    index = np.arange(periods, dtype=float)
    base = 65000.0 + index * 0.7 + np.sin(index / 7.0) * 420.0 + np.sin(index / 41.0) * 900.0
    close = base + np.sin(index / 3.0) * 55.0
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": base,
            "high": np.maximum(base, close) + 80.0,
            "low": np.minimum(base, close) - 80.0,
            "close": close,
            "volume": 10.0 + (index % 17),
        }
    )


def _definition_set(root: Path, decision_time: str) -> Path:
    case = root / "trend_01"
    case.mkdir(parents=True)
    (case / "metadata.json").write_text(
        json.dumps(
            {
                "instrument": "BTCUSDT",
                "timeframe": "15m",
                "decision_time": decision_time,
                "regime_type": "trend",
            }
        ),
        encoding="utf-8",
    )
    (root / "definition_set_status.json").write_text(
        json.dumps(
            {
                "schema": "definition_set_status_v2",
                "selection_status": "ANALYST_REVIEWED",
                "analyst_id": "analyst-1",
                "reviewed_at": "2026-08-08T20:00:00Z",
                "selection_rationale": "Independent chart review before system answers were generated.",
                "scoreable": True,
                "case_count": 1,
                "case_ids_sha256": _case_ids_sha256(["trend_01"]),
                "case_set_sha256": _definition_case_set_sha256(root, ["trend_01"]),
            }
        ),
        encoding="utf-8",
    )
    return root


def _source(path: Path) -> tuple[Path, str]:
    frame = _frame()
    frame.to_csv(path, index=False)
    decision_time = (frame["timestamp"].iloc[-1] + pd.Timedelta("15min")).isoformat()
    return path, decision_time


def _fake_answer(decision_time: str) -> dict:
    return {
        "sealed": True,
        "generation_status": "COMPLETE",
        "pack_hash": "a" * 64,
        "decision_time": decision_time,
        "detector_timeframes": ["1d", "4h", "1h", "15m"],
        "htf_bias": "bullish",
        "context_timeframe": "4h",
        "dealing_range": {"high": 68000.0, "low": 62000.0, "timeframe": "4h"},
        "draw": {"target_price": 69000.0, "direction": "bullish"},
        "market_state": {"state": "POI_MAPPED", "poi": {}},
        "decision": {
            "classification": "watch",
            "source_state": "POI_MAPPED",
            "authority": "observe_only_no_signal_or_execution_authority",
        },
        "significant_structure": {"1d": [], "4h": [], "1h": [], "15m": []},
        "atr": {"1d": 2000.0, "4h": 800.0, "1h": 400.0, "15m": 200.0},
        "object_prices": {},
        "object_metadata": {},
    }


def _fast_render(_frame: pd.DataFrame, path: Path, title: str) -> None:
    path.write_bytes(("PNG:" + title).encode("utf-8"))


def _build_fast_cohort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict]:
    source_path, decision_time = _source(tmp_path / "source.csv")
    definition = _definition_set(tmp_path / "definition", decision_time)
    output = tmp_path / "cohort"
    monkeypatch.setattr(builder, "_render_clean", _fast_render)
    monkeypatch.setattr(builder, "_system_answer", lambda _frames, _symbol: _fake_answer(decision_time))
    manifest = build_cohort(
        gold_root=definition,
        source_path=source_path,
        out_root=output,
        reviewer_id="founder",
    )
    return output, manifest


def test_decision_time_excludes_the_candle_that_only_opens_then():
    sliced = _slice_at(_frame(100), pd.Timestamp("2026-05-20T12:00:00Z"))

    assert sliced["15m"]["timestamp"].iloc[-1] == pd.Timestamp("2026-05-20T11:45:00Z")


def test_every_emitted_timeframe_is_closed_by_the_decision_time():
    decision_time = pd.Timestamp("2026-06-10T12:07:00Z")
    durations = {
        "15m": pd.Timedelta("15min"),
        "1h": pd.Timedelta("1h"),
        "4h": pd.Timedelta("4h"),
        "1d": pd.Timedelta("1D"),
    }

    for timeframe, frame in _slice_at(_frame(), decision_time).items():
        assert not frame.empty
        assert (
            pd.to_datetime(frame["timestamp"], utc=True) + durations[timeframe] <= decision_time
        ).all()


def test_evaluation_index_reads_real_nested_detector_objects():
    candidates = {
        "4h": {
            "liquidity_levels": [
                {
                    "object_id": "liq_equal_lows_1",
                    "timeframe": "4h",
                    "direction": "bullish",
                    "price_low": "99.0",
                    "price_high": "101.0",
                    "evidence": {"level_kind": "equal_lows", "side": "sell_side"},
                }
            ]
        }
    }

    prices, metadata = _evaluation_object_index(candidates)

    assert prices["4h:liq_equal_lows_1"] == 100.0
    assert metadata["4h:liq_equal_lows_1"]["primitive"] == "equal_lows"
    assert metadata["4h:liq_equal_lows_1"]["side"] == "sell_side"


def test_evaluation_index_flattens_production_swing_scales():
    prices, metadata = _evaluation_object_index(
        {
            "4h": {
                "swings": {
                    "local": [
                        {
                            "object_id": "swing_local_1",
                            "direction": "bearish",
                            "price_low": 90.0,
                            "price_high": 110.0,
                        }
                    ],
                    "internal": [],
                    "external": [],
                }
            }
        }
    )

    assert prices["4h:swing_local_1"] == 110.0
    assert metadata["4h:swing_local_1"]["primitive"] == "swing_high"


def test_timeframe_qualified_object_keys_cannot_overwrite_each_other():
    candidates = {
        timeframe: {
            "swings": {"local": [{"object_id": "same", "direction": "bullish", "price_low": price}]}
        }
        for timeframe, price in (("15m", 100.0), ("4h", 200.0))
    }

    prices, _ = _evaluation_object_index(candidates)

    assert prices == {"15m:same": 100.0, "4h:same": 200.0}


def test_builder_is_atomic_immutable_and_hash_sealed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, manifest = _build_fast_cohort(tmp_path, monkeypatch)
    sealed = output / "trend_01" / "_sealed_system_answer.json"
    original = sealed.read_bytes()

    validated = _assert_cohort_scoreable(output)
    assert validated["cohort_content_sha256"] == manifest["cohort_content_sha256"]
    assert validated["cases"][0]["sealed_answer_sha256"]
    assert set(validated["cases"][0]["source_slices"]) == {"1d", "4h", "1h", "15m"}

    (output / "trend_01" / "markup.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite immutable cohort"):
        build_cohort(
            gold_root=tmp_path / "definition",
            source_path=tmp_path / "source.csv",
            out_root=output,
            reviewer_id="founder",
        )
    assert sealed.read_bytes() == original


def test_scorer_rejects_tampered_sealed_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, _ = _build_fast_cohort(tmp_path, monkeypatch)
    sealed = output / "trend_01" / "_sealed_system_answer.json"
    sealed.write_text(sealed.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact size mismatch"):
        _assert_cohort_scoreable(output)


def test_scorer_rejects_source_drift_after_sealing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, _ = _build_fast_cohort(tmp_path, monkeypatch)
    source = tmp_path / "source.csv"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source size changed"):
        _assert_cohort_scoreable(output)


def test_scorer_rejects_definition_metadata_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, _ = _build_fast_cohort(tmp_path, monkeypatch)
    metadata_path = tmp_path / "definition" / "trend_01" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["decision_time"] = "2026-06-01T12:00:00Z"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="case metadata changed"):
        _assert_cohort_scoreable(output)


def test_generation_error_never_becomes_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_path, decision_time = _source(tmp_path / "source.csv")
    definition = _definition_set(tmp_path / "definition", decision_time)
    output = tmp_path / "failed-cohort"
    monkeypatch.setattr(builder, "_render_clean", _fast_render)

    def fail(_frames, _symbol):
        raise CohortGenerationError("detector failed for 4h")

    monkeypatch.setattr(builder, "_system_answer", fail)
    manifest = build_cohort(
        gold_root=definition,
        source_path=source_path,
        out_root=output,
        reviewer_id="founder",
    )

    assert manifest["validation_status"] == "INVALID_GENERATION_FAILED"
    assert manifest["cases"][0]["status"] == "FAILED"
    assert not (output / "trend_01" / "_sealed_system_answer.json").exists()
    with pytest.raises(ValueError, match="INVALID_GENERATION_FAILED"):
        _assert_cohort_scoreable(output)


def test_reviewed_label_without_full_provenance_is_rejected(tmp_path: Path):
    source_path, decision_time = _source(tmp_path / "source.csv")
    definition = _definition_set(tmp_path / "definition", decision_time)
    (definition / "definition_set_status.json").write_text(
        '{"selection_status":"ANALYST_REVIEWED"}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Invalid analyst-review provenance"):
        build_cohort(
            gold_root=definition,
            source_path=source_path,
            out_root=tmp_path / "cohort",
            reviewer_id="founder",
        )
    assert not (tmp_path / "cohort").exists()


def test_invalid_cohort_is_refused_before_scoring(tmp_path: Path):
    (tmp_path / "cohort_manifest.json").write_text(
        '{"validation_status":"INVALID_DO_NOT_MARK","invalid_reasons":["future candle leak"]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="INVALID_DO_NOT_MARK"):
        _assert_cohort_scoreable(tmp_path)


def test_real_engine_build_to_completed_markup_to_score(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_path, decision_time = _source(tmp_path / "source.csv")
    definition = _definition_set(tmp_path / "definition", decision_time)
    output = tmp_path / "real-engine-cohort"
    monkeypatch.setattr(builder, "_render_clean", _fast_render)

    manifest = build_cohort(
        gold_root=definition,
        source_path=source_path,
        out_root=output,
        reviewer_id="founder",
    )
    row = manifest["cases"][0]
    answer = json.loads(
        (output / "trend_01" / "_sealed_system_answer.json").read_text(encoding="utf-8")
    )
    significant_keys = {
        f"{timeframe}:{object_id}"
        for timeframe, object_ids in answer["significant_structure"].items()
        for object_id in object_ids
    }
    assert significant_keys <= set(answer["object_prices"])
    assert significant_keys <= set(answer["object_metadata"])
    assert any(
        metadata.get("group") == "swings" for metadata in answer["object_metadata"].values()
    )
    assert answer["generation_status"] == "COMPLETE"
    assert row["status"] == "READY"

    template_path = output / "trend_01" / "markup_template.json"
    markup = json.loads(template_path.read_text(encoding="utf-8"))
    markup.update(
        {
            "review_status": "COMPLETE",
            "review_completed_at": "2026-08-08T21:00:00Z",
            "htf_bias": answer["htf_bias"] if answer["htf_bias"] in {"bullish", "bearish", "ranging"} else "unclear",
            "context_timeframe": answer["context_timeframe"]
            if answer["context_timeframe"] in {"1d", "4h", "1h", "15m"}
            else "4h",
            "would_you_trade_this": answer["decision"]["classification"],
        }
    )
    (output / "trend_01" / "markup.json").write_text(json.dumps(markup), encoding="utf-8")

    result = score_case(output / "trend_01", "markup.json")

    assert result is not None and result["status"] == "SCORED"
    assert result["decision"]["agree"] is True
