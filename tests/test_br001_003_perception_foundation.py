from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from smc_desk.brain.structure_reasoning_roles import (
    REQUIRED_ROLES,
    load_structure_reasoning_contract,
)
from smc_desk.data.market_truth_certificate import (
    assert_future_append_invariant,
    certify_market_truth,
)
from smc_desk.data.ohlcv_contract import OHLCVContractError
from smc_desk.perception.config import load_perception_config


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "br002_market_truth_expected.json").read_text()
)


def _base_frame(rows: int = 96, start: str = "2026-01-01T00:00:00Z") -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=rows, freq="15min", tz="UTC").tz_convert(None)
    indices = list(range(rows))
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index for index in indices],
            "high": [102.0 + index for index in indices],
            "low": [99.0 + index for index in indices],
            "close": [101.0 + index for index in indices],
            "volume": [10.0 + index for index in indices],
        }
    )


def _certify(frame: pd.DataFrame, decision: str = "2026-01-02T00:00:00Z", **kwargs):
    return certify_market_truth(
        frame,
        symbol="BTCUSDT",
        observed_symbol=kwargs.pop("observed_symbol", "BTCUSDT"),
        decision_time=decision,
        dataset_id="independent_fixture",
        **kwargs,
    )


def test_fixture_declares_all_fourteen_required_cases() -> None:
    assert len(FIXTURE["cases"]) == 14
    required = {
        "normal_15m_to_1h",
        "normal_15m_to_4h",
        "daily_boundary_reconstruction",
        "decision_exactly_on_boundary",
        "decision_between_boundaries",
        "incomplete_1h",
        "incomplete_4h",
        "incomplete_1d",
        "missing_15m",
        "duplicate_timestamp",
        "out_of_order",
        "source_mismatch",
        "future_rows_appended",
        "live_tail_overlap",
    }
    assert {case["id"] for case in FIXTURE["cases"]} == required


def test_independent_ohlcv_aggregation_and_lineage() -> None:
    truth = _certify(_base_frame())
    expected = FIXTURE["independent_expected_ohlcv"]
    for timeframe, key, count in (
        ("1h", "first_1h", 4),
        ("4h", "first_4h", 16),
        ("1d", "first_1d", 96),
    ):
        actual = truth.timeframe_dfs[timeframe].iloc[0]
        for field, value in expected[key].items():
            assert float(actual[field]) == value
        first_lineage = truth.certificate["lineage"][timeframe][0]
        assert first_lineage["source_count"] == count
        assert len(first_lineage["source_rows_sha256"]) == 64


@pytest.mark.parametrize(
    ("decision", "expected_1h", "expected_4h", "expected_1d"),
    [
        ("2026-01-01T01:00:00Z", 1, 0, 0),
        ("2026-01-01T01:37:00Z", 1, 0, 0),
        ("2026-01-01T04:00:00Z", 4, 1, 0),
        ("2026-01-02T00:00:00Z", 24, 6, 1),
    ],
)
def test_decision_boundaries_and_partial_htf_exclusion(
    decision: str,
    expected_1h: int,
    expected_4h: int,
    expected_1d: int,
) -> None:
    truth = _certify(_base_frame(), decision)
    assert len(truth.timeframe_dfs["1h"]) == expected_1h
    assert len(truth.timeframe_dfs["4h"]) == expected_4h
    assert len(truth.timeframe_dfs["1d"]) == expected_1d
    for timeframe in ("1h", "4h", "1d"):
        if truth.certificate["excluded_incomplete_buckets"][timeframe]:
            assert all(
                item["reason"] in {
                    "bucket_not_closed_at_decision",
                    "incomplete_source_rows_for_bucket",
                }
                for item in truth.certificate["excluded_incomplete_buckets"][timeframe]
            )


@pytest.mark.parametrize("mutation, expected_code", [
    ("missing", "missing_15m_candle"),
    ("duplicate", "duplicate_timestamp"),
    ("out_of_order", "out_of_order"),
    ("live_tail_overlap", "duplicate_timestamp"),
])
def test_source_defects_fail_loudly(mutation: str, expected_code: str) -> None:
    frame = _base_frame()
    if mutation == "missing":
        frame = frame.drop(index=10).reset_index(drop=True)
    elif mutation == "duplicate":
        frame = pd.concat([frame.iloc[:11], frame.iloc[[10]], frame.iloc[11:]], ignore_index=True)
    elif mutation == "out_of_order":
        frame.iloc[[10, 11]] = frame.iloc[[11, 10]].to_numpy()
    elif mutation == "live_tail_overlap":
        frame = pd.concat([frame, frame.tail(1)], ignore_index=True)
    with pytest.raises(OHLCVContractError) as error:
        _certify(frame)
    assert expected_code in {issue["code"] for issue in error.value.issues}


def test_source_symbol_mismatch_fails() -> None:
    with pytest.raises(OHLCVContractError) as error:
        _certify(_base_frame(), observed_symbol="ETHUSDT")
    assert {issue["code"] for issue in error.value.issues} == {"source_symbol_mismatch"}


def test_future_append_does_not_change_any_frame_visible_at_t() -> None:
    base = _base_frame()
    decision = "2026-01-01T12:00:00Z"
    original = _certify(base.iloc[:48].copy(), decision)
    appended = _certify(base.copy(), decision)
    assert appended.certificate["future_rows_excluded"] == 48
    assert_future_append_invariant(original, appended)


def test_detector_runtime_has_no_strategy_authority() -> None:
    config = load_perception_config()
    fields = set(type(config).model_fields)
    assert "risk_reward_floor" not in fields
    assert "stop_buffer_atr_mult" not in fields
    assert "require_fresh_poi" not in fields
    assert config.detector_config_id == "PERCEPTION_DETECTOR_CONFIG_V2"


def test_active_perception_import_graph_does_not_load_legacy_modules() -> None:
    code = (
        "import json,sys; "
        "import smc_desk.perception.engine_v2; "
        "import smc_desk.colleague.run_context; "
        "import smc_desk.research.perception_experiment; "
        "forbidden=['smc_desk.engine','smc_desk.rules','smc_desk.mtf','smc_desk.case_library']; "
        "print(json.dumps([name for name in forbidden if name in sys.modules]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout) == []


def test_ai_is_semantic_brain_but_never_geometry_or_trade_authority() -> None:
    contract = load_structure_reasoning_contract()
    assert tuple(contract["roles"]) == REQUIRED_ROLES
    assert "construct_causal_structure_episodes" in contract["global_ai_permissions"]
    assert "rank_competing_interpretations" in contract["global_ai_permissions"]
    assert "move_candidate_time_or_price_coordinates" in contract["global_ai_prohibitions"]
    assert contract["roles"]["annotation_planner"]["coordinate_authority"] == "certified_geometry_only"
    assert contract["roles"]["adversarial_structure_critic"]["promotion_allowed"] is False
    assert contract["execution_authority"]["signal_allowed"] is False


def test_baseline_envelope_is_reproducible_and_complete(tmp_path: Path) -> None:
    source = tmp_path / "BTCUSDT_15m.csv"
    _base_frame(rows=192).to_csv(source, index=False)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    def run_clean_process(output: Path) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "run_perception_experiment.py"),
                "baseline",
                "--symbol",
                "BTCUSDT",
                "--source",
                str(source),
                "--decision-time",
                "2026-01-03T00:00:00Z",
                "--out",
                str(output),
                "--window-15m",
                "192",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert '"status": "PASS"' in completed.stdout
        return json.loads((output / "run_manifest.json").read_text())

    first = run_clean_process(first_dir)
    second = run_clean_process(second_dir)
    assert first["experiment_fingerprint"] == second["experiment_fingerprint"]
    required = {
        "run_manifest.json",
        "input_manifest.json",
        "environment_manifest.json",
        "market_truth_certificate.json",
        "authority_trace.json",
        "ai_trace.json",
        "perception_result.json",
        "annotation_plan.json",
        "validation_summary.json",
    }
    assert required.issubset({path.name for path in first_dir.iterdir()})
    summary = json.loads((first_dir / "validation_summary.json").read_text())
    authority = json.loads((first_dir / "authority_trace.json").read_text())
    assert summary["status"] == "PASS"
    assert summary["readiness_gate"] == "NOT_PASSED_BR004_BR006_PENDING"
    assert authority["legacy_engine_loaded"] is False
    assert authority["forbidden_legacy_modules_loaded"] == []
    assert authority["signal_allowed"] is False
    assert first["ai_provider"] == "NONE"
    assert first["evaluation_result"] == "NOT_EVALUATED_NO_ADJUDICATED_GOLD"


def test_baseline_records_fail_closed_if_process_is_legacy_contaminated(tmp_path: Path) -> None:
    import smc_desk.rules  # noqa: F401 - intentional contamination fixture
    from smc_desk.research.perception_experiment import run_deterministic_baseline

    source = tmp_path / "BTCUSDT_15m.csv"
    _base_frame(rows=192).to_csv(source, index=False)
    output = tmp_path / "contaminated"
    run_deterministic_baseline(
        symbol="BTCUSDT",
        source=source,
        decision_time="2026-01-03T00:00:00Z",
        output_dir=output,
        window_15m=192,
    )
    summary = json.loads((output / "validation_summary.json").read_text())
    authority = json.loads((output / "authority_trace.json").read_text())
    assert summary["status"] == "FAIL"
    assert summary["checks"]["legacy_authority_absent"] is False
    assert "smc_desk.rules" in authority["forbidden_legacy_modules_loaded"]
