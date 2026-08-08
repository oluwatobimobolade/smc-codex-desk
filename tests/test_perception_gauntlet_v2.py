from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from smc_desk.evaluation.perception_gauntlet import (
    EXPECTED_PROBE_IDS,
    aggregate_gauntlet_case_scores,
    gauntlet_protocol_manifest,
    response_template,
    score_gauntlet_case,
    validate_gauntlet_response,
)
from smc_desk.evaluation.semantic_metamorphic import (
    SweepCandidate,
    build_semantic_metamorphic_frames,
    decimal_rescale,
    inject_flash_wick,
    one_candle_rollback,
    remove_sweep_wick,
    truncate_origin_history,
    vertical_mirror,
    verify_transformation,
)


def _frame(count: int = 80) -> pd.DataFrame:
    close = np.linspace(100.0, 108.0, count) + np.sin(np.arange(count) / 3.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) + 0.4
    low = np.minimum(open_, close) - 0.4
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=count, freq="15min", tz="UTC"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.arange(count) + 100,
        }
    )


def _complete_submission(case_id: str = "CASE-001") -> dict:
    payload = response_template(case_id)
    for item in payload["responses"]:
        signature = {"classification": "watch", "direction": "mixed", "objects": ["obj-1"]}
        for wording in ("primary", "paraphrase"):
            item[wording] = {
                "answer": "Evidence-grounded answer.",
                "abstain": False,
                "resolution_condition": None,
                "evidence_contract_ids": ["obj-1"],
                "claim_signature": copy.deepcopy(signature),
            }
    return payload


def test_gauntlet_protocol_is_complete_versioned_and_non_authoritative() -> None:
    manifest = gauntlet_protocol_manifest()
    assert manifest["probe_count"] == 46
    assert len(EXPECTED_PROBE_IDS) == 46
    assert len(set(EXPECTED_PROBE_IDS)) == 46
    assert set(manifest["faculties"]) == set("ABCDEFGHIJK")
    assert manifest["authority_contract"]["engine_self_scoring_allowed"] is False
    assert manifest["authority_contract"]["signal_allowed"] is False


def test_gauntlet_requires_two_grounded_consistent_answers_per_probe() -> None:
    payload = _complete_submission()
    validation = validate_gauntlet_response(payload, known_evidence_ids=["obj-1"])
    assert validation["status"] == "PASS_CONTRACT"

    payload["responses"][0]["paraphrase"]["claim_signature"]["direction"] = "bullish"
    validation = validate_gauntlet_response(payload, known_evidence_ids=["obj-1"])
    assert validation["status"] == "FAIL_CONTRACT"
    assert any("A1:paraphrase_claim_signature_mismatch" in issue for issue in validation["issues"])


def test_paraphrase_mismatch_forces_zero_even_when_adjudicator_score_is_two() -> None:
    payload = _complete_submission()
    payload["responses"][0]["paraphrase"]["claim_signature"]["direction"] = "bearish"
    adjudication = {
        "adjudication_status": "complete",
        "probe_scores": {probe_id: 2 for probe_id in EXPECTED_PROBE_IDS},
    }
    report = score_gauntlet_case(payload, adjudication, known_evidence_ids=["obj-1"])
    assert report["probe_scores"]["A1"] == 0
    assert report["forced_zero"]["A1"]
    assert report["score_distribution"]["0"] == 1


def test_promotion_gates_block_annotation_until_time_story_and_structure_pass() -> None:
    perfect = _complete_submission()
    complete = {"adjudication_status": "complete", "probe_scores": {probe_id: 2 for probe_id in EXPECTED_PROBE_IDS}}
    good_report = score_gauntlet_case(perfect, complete, known_evidence_ids=["obj-1"])
    cohort = aggregate_gauntlet_case_scores(
        [{**good_report, "case_id": f"CASE-{index:03d}"} for index in range(30)]
    )
    assert cohort["status"] == "PASS_PROMOTION_GATES"
    assert cohort["promotion_gates"]["K"]["passed"] is True

    weak_time = copy.deepcopy(good_report)
    for probe_id in ("A1", "A2", "A3", "A4"):
        weak_time["probe_scores"][probe_id] = 0
    blocked = aggregate_gauntlet_case_scores(
        [{**weak_time, "case_id": f"WEAK-{index:03d}"} for index in range(30)]
    )
    assert blocked["status"] == "NOT_PASSED"
    assert blocked["promotion_gates"]["A"]["passed"] is False
    assert blocked["promotion_gates"]["K"]["prerequisite_passed"] is False


def test_vertical_mirror_is_exact_directional_symmetry() -> None:
    source = _frame()
    result, contract = vertical_mirror(source)
    axis = contract["parameters"]["axis"]
    assert np.allclose(result["high"], 2 * axis - source["low"])
    assert np.allclose(result["low"], 2 * axis - source["high"])
    assert np.allclose(result["volume"], source["volume"])
    assert verify_transformation(source, result, contract) == []


def test_decimal_rescale_changes_only_price_magnitude() -> None:
    source = _frame()
    result, contract = decimal_rescale(source, 0.0001)
    assert np.allclose(result[["open", "high", "low", "close"]], source[["open", "high", "low", "close"]] * 0.0001)
    assert result["timestamp"].equals(source["timestamp"])
    assert verify_transformation(source, result, contract) == []


def test_rollback_and_origin_truncation_preserve_retained_candles_exactly() -> None:
    source = _frame()
    rolled, rollback_contract = one_candle_rollback(source)
    truncated, truncation_contract = truncate_origin_history(source, keep_bars=40)
    assert len(rolled) == len(source) - 1
    assert len(truncated) == 40
    assert verify_transformation(source, rolled, rollback_contract) == []
    assert verify_transformation(source, truncated, truncation_contract) == []


def test_sweep_removal_changes_exactly_one_wick_field() -> None:
    source = _frame()
    index = 50
    level = float(source.iloc[index - 12:index]["high"].max())
    source.at[index, "open"] = level - 0.3
    source.at[index, "close"] = level - 0.2
    source.at[index, "high"] = level + 0.5
    source.at[index, "low"] = min(float(source.at[index, "open"]), float(source.at[index, "close"])) - 0.4
    result, contract = remove_sweep_wick(source, SweepCandidate(index, "buyside", level, 12))
    assert result.at[index, "high"] <= level
    assert verify_transformation(source, result, contract) == []


def test_flash_wick_changes_one_extreme_without_changing_body() -> None:
    source = _frame()
    result, contract = inject_flash_wick(source, index=40, direction="sellside")
    assert result.at[40, "open"] == source.at[40, "open"]
    assert result.at[40, "close"] == source.at[40, "close"]
    assert result.at[40, "low"] < source.at[40, "low"]
    assert verify_transformation(source, result, contract) == []


def test_semantic_pack_contains_all_six_gauntlet_transformations() -> None:
    variants = build_semantic_metamorphic_frames(_frame())
    assert set(variants) == {
        "vertical_mirror",
        "decimal_rescale",
        "one_candle_rollback",
        "origin_history_truncation",
        "sweep_wick_removal_twin",
        "flash_wick_injection",
    }
    assert all(item["contract"]["authority_contract"]["signal_allowed"] is False for item in variants.values())
