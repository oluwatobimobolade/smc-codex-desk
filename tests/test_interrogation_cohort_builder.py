from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from smc_desk.evaluation.interrogation_cohort import (
    build_interrogation_cohort,
    derive_visible_timeframes,
    select_blind_cutoffs,
    verify_interrogation_cohort,
)


def _frame(count: int = 16_000) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    timestamp = pd.date_range("2022-01-01", periods=count, freq="15min", tz="UTC")
    volatility = np.linspace(0.1, 2.0, count)
    change = rng.normal(0, volatility)
    close = 100 + np.cumsum(change)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) + rng.random(count) * volatility
    low = np.minimum(open_, close) - rng.random(count) * volatility
    return pd.DataFrame({
        "timestamp": timestamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.integers(1, 1000, count),
    })


def test_cutoff_selection_is_deterministic_engine_blind_and_spaced() -> None:
    frame = _frame()
    first = select_blind_cutoffs(frame, count=2, minimum_history_bars=4_000, minimum_spacing_days=10)
    second = select_blind_cutoffs(frame, count=2, minimum_history_bars=4_000, minimum_spacing_days=10)
    assert first == second
    assert len(first) == 2
    assert abs(first[1] - first[0]) >= pd.Timedelta(days=10)


def test_visible_timeframes_exclude_forming_and_future_candles() -> None:
    frame = _frame(14_000)
    cutoff = pd.Timestamp("2022-05-20T12:00:00Z")
    windows = derive_visible_timeframes(frame, cutoff)
    duration = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}
    assert set(windows) == set(duration)
    for timeframe, visible in windows.items():
        assert pd.Timestamp(visible.iloc[-1]["timestamp"]) + duration[timeframe] <= cutoff


def test_cohort_contains_blind_reviews_counterfactuals_and_true_rerenders(tmp_path: Path) -> None:
    frame = _frame()
    source = tmp_path / "BTCUSDT_15m_4year.csv"
    frame.to_csv(source, index=False)
    manifest = build_interrogation_cohort(
        symbol_csv_paths={"BTCUSDT": source},
        output_root=tmp_path / "cohort",
        cases_per_symbol=1,
        cohort_id="TEST-COHORT",
    )
    assert manifest["case_count"] == 1
    assert manifest["certification_eligible"] is False
    assert manifest["selection_contract"]["future_outcomes_used"] is False
    case = manifest["cases"][0]
    assert case["future_candles_included"] is False
    assert case["engine_output_included"] is False
    assert len(case["presentation_variants"]) == 15
    assert case["sequential_replay"]["stage_count"] == 4
    stage_counts = [stage["visible_candle_count"] for stage in case["sequential_replay"]["stages"]]
    assert stage_counts == sorted(stage_counts)
    assert stage_counts[-1] == 160
    semantic_hashes = {item["ohlcv_semantic_hash"] for item in case["presentation_variants"].values()}
    assert len(semantic_hashes) == 1
    assert all(Path(path).is_file() for path in case["reviewer_templates"])
    reviewer = json.loads(Path(case["reviewer_templates"][0]).read_text(encoding="utf-8"))
    assert reviewer["independent_review_attested"] is False
    assert len(reviewer["dimension_judgments"]) == 10
    assert len(reviewer["hard_question_answers"]) == 20
    assert Path(case["counterfactual_chart_path"]).is_file()
    assert manifest["no_evidence_pack"]["expected_policy"] == "abstain_on_all_four"
    verification = verify_interrogation_cohort(tmp_path / "cohort")
    assert verification["status"] == "PASS"
    assert verification["checked_counterfactual_count"] == 1
    assert verification["trust_registry_ready"] is False


def test_cohort_verifier_detects_tampering(tmp_path: Path) -> None:
    frame = _frame()
    source = tmp_path / "BTCUSDT_15m_4year.csv"
    frame.to_csv(source, index=False)
    manifest = build_interrogation_cohort(
        symbol_csv_paths={"BTCUSDT": source},
        output_root=tmp_path / "cohort",
        cases_per_symbol=1,
        cohort_id="TAMPER-TEST",
    )
    chart = Path(manifest["cases"][0]["chart_paths"]["15m"])
    chart.write_bytes(chart.read_bytes() + b"tampered")
    verification = verify_interrogation_cohort(tmp_path / "cohort")
    assert verification["status"] == "FAIL"
    assert any("file_hash_mismatch" in issue for issue in verification["issues"])


def test_gauntlet_v2_cohort_adds_dual_wording_and_semantic_mutations(tmp_path: Path) -> None:
    frame = _frame()
    source = tmp_path / "BTCUSDT_15m_4year.csv"
    frame.to_csv(source, index=False)
    manifest = build_interrogation_cohort(
        symbol_csv_paths={"BTCUSDT": source},
        output_root=tmp_path / "gauntlet_cohort",
        cases_per_symbol=1,
        cohort_id="TEST-GAUNTLET-V2",
        include_gauntlet_v2=True,
    )
    assert manifest["gauntlet_v2"]["probe_count"] == 46
    assert manifest["gauntlet_v2"]["responses_per_probe"] == 2
    case = manifest["cases"][0]
    semantic = case["semantic_metamorphic_pack"]
    assert semantic["variant_count"] == 6
    assert set(semantic["variants"]) == {
        "vertical_mirror",
        "decimal_rescale",
        "one_candle_rollback",
        "origin_history_truncation",
        "sweep_wick_removal_twin",
        "flash_wick_injection",
    }
    response = json.loads(Path(case["gauntlet_response_template"]).read_text(encoding="utf-8"))
    assert len(response["responses"]) == 46
    assert all(set(item) == {"probe_id", "primary", "paraphrase"} for item in response["responses"])
    verification = verify_interrogation_cohort(tmp_path / "gauntlet_cohort")
    assert verification["status"] == "PASS"
    assert verification["checked_semantic_transformation_count"] >= 5
