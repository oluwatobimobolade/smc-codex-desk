"""Human-independent definition-conformance gate tests."""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest
import yaml

from smc_desk.data.hashing import file_sha256
from smc_desk.evaluation.autonomous_conformance import (
    run_autonomous_conformance_bundle,
    run_autonomous_definition_conformance,
    run_reference_metamorphic_checks,
)
from smc_desk.evaluation.autonomous_truth import (
    compare_claim_sets,
    load_autonomous_truth_constitution,
)
from smc_desk.evaluation.reference_oracle import OracleConfig, run_reference_oracle


ROOT = Path(__file__).resolve().parents[1]


def _fixture_frame() -> pd.DataFrame:
    return pd.read_csv(ROOT / "sample_ohlcv.csv")


def test_constitution_is_sealed_and_cannot_grant_trade_authority():
    constitution = load_autonomous_truth_constitution()
    assert constitution.sha256 == file_sha256(constitution.path)
    authority = constitution.document["authority_contract"]
    assert authority["human_adjudication_required_for_definition_conformance"] is False
    assert authority["signal_allowed"] is False
    assert authority["paper_execution_allowed"] is False
    assert authority["live_execution_allowed"] is False
    assert constitution.label_contracts["order_block"]["authority_target"] == "NOT_EVALUATED"


def test_tampered_constitution_fails_closed(tmp_path: Path):
    source = ROOT / "specs" / "AUTONOMOUS_TRUTH_CONSTITUTION_V1.yaml"
    copy = tmp_path / "constitution.yaml"
    seal = tmp_path / "constitution.sha256"
    copy.write_text(source.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
    seal.write_text((ROOT / "specs" / "AUTONOMOUS_TRUTH_CONSTITUTION_V1.sha256").read_text(), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_autonomous_truth_constitution(copy, seal)


PROHIBITED_FOR_CLEAN_ROOM = (
    "smc_desk.perception",
    "smc_desk.structure",
    "smc_desk.brain",
    "smc_desk.decision",
)


def _module_imports(module: str) -> set[str] | None:
    """Return the smc_desk modules `module` imports, or None if it is not ours."""
    path = ROOT / (module.replace(".", "/") + ".py")
    if not path.exists():
        path = ROOT / module.replace(".", "/") / "__init__.py"
    if not path.exists():
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return {name for name in found if name.startswith("smc_desk")}


def test_clean_room_oracle_has_no_production_imports():
    """Independence must hold through the whole import graph, not one file.

    Checking only the oracle's direct imports would miss the obvious way to
    break this: the oracle imports an innocent-looking helper, and the helper
    imports production perception. Then the "independent" oracle is running
    production code and agreement proves nothing.
    """
    seen: set[str] = set()
    queue = ["smc_desk.evaluation.reference_oracle"]
    violations: list[str] = []
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        imported = _module_imports(module)
        if imported is None:  # third-party or stdlib; not ours to police
            continue
        for name in imported:
            if name.startswith(PROHIBITED_FOR_CLEAN_ROOM):
                violations.append(f"{module} -> {name}")
            queue.append(name)
    assert not violations, f"clean-room independence broken transitively: {violations}"
    # The oracle is meant to stand almost alone; a growing shared surface is
    # itself a warning even when nothing prohibited has been imported yet.
    assert seen <= {
        "smc_desk.evaluation.reference_oracle",
        "smc_desk.data.hashing",
    }, f"clean-room reach widened to {sorted(seen)}"


def test_real_closed_ohlcv_matches_independent_swing_and_fvg_oracles():
    frame = _fixture_frame()
    decision_time = pd.Timestamp(frame.iloc[-1]["timestamp"]) + pd.Timedelta(minutes=15)
    result = run_autonomous_definition_conformance(
        frame,
        market="SAMPLE",
        timeframe="15m",
        decision_time=decision_time,
    )
    comparisons = {item["label_family"]: item for item in result["certificate"]["comparisons"]}
    assert comparisons["swing"]["status"] == "DEFINITION_CONFORMANT"
    assert comparisons["fair_value_gap"]["status"] == "DEFINITION_CONFORMANT"
    assert comparisons["swing"]["matched_count"] > 0
    assert result["certificate"]["status"] == "BOUNDARY_SENSITIVE"
    robustness = result["certificate"]["robustness"]
    assert robustness["schema"] == "autonomous_robustness_envelope_v2"
    assert len(robustness["robust_claims_sample"]) <= robustness["sample_limit"]
    assert len(robustness["boundary_sensitive_claims_sample"]) <= robustness["sample_limit"]
    assert "robust_claims" not in robustness
    assert robustness["robust_claim_set_sha256"]
    assert robustness["boundary_sensitive_claim_set_sha256"]
    assert result["certificate"]["authority_contract"]["human_adjudication_used"] is False
    assert result["certificate"]["authority_contract"]["signal_allowed"] is False


def test_all_required_metamorphic_relations_pass():
    frame = _fixture_frame()
    decision_time = pd.Timestamp(frame.iloc[-1]["timestamp"]) + pd.Timedelta(minutes=15)
    checks = run_reference_metamorphic_checks(
        frame,
        market="SAMPLE",
        timeframe="15m",
        decision_time=decision_time,
        config=OracleConfig(),
    )
    assert checks
    assert all(item["passed"] for item in checks), checks


def test_metamorphic_relations_do_not_confuse_forex_float_tails_with_claim_changes():
    frame = _fixture_frame().copy()
    for column in ("open", "high", "low", "close"):
        frame[column] = 0.8 + frame[column].astype(float) / 123_456.789
    decision_time = pd.Timestamp(frame.iloc[-1]["timestamp"]) + pd.Timedelta(minutes=15)

    checks = run_reference_metamorphic_checks(
        frame,
        market="USDCHF",
        timeframe="15m",
        decision_time=decision_time,
        config=OracleConfig(),
        session_profile="forex_5d",
    )

    assert all(item["passed"] for item in checks), checks


def test_reference_oracle_ignores_future_rows():
    frame = _fixture_frame()
    decision_time = pd.Timestamp(frame.iloc[-2]["timestamp"]) + pd.Timedelta(minutes=15)
    baseline = run_reference_oracle(
        frame.iloc[:-1], market="SAMPLE", timeframe="15m", decision_time=decision_time
    )
    changed = frame.copy()
    changed.loc[changed.index[-1], ["open", "high", "low", "close"]] = [1, 1_000_000, 0.1, 800_000]
    after = run_reference_oracle(
        changed, market="SAMPLE", timeframe="15m", decision_time=decision_time
    )
    assert after == baseline


def test_disagreement_is_an_implementation_conflict():
    reference = [{
        "label_family": "swing", "timeframe": "15m", "scope": "local",
        "direction": "bullish", "pivot_time": "2026-01-01T00:00:00Z",
        "candidate_at": "2026-01-01T00:15:00Z", "confirmed_at": "2026-01-01T00:30:00Z",
        "price_low": "100", "price_high": "102", "reference_time": "",
        "reference_price": "", "state": "CONFIRMED",
    }]
    production = [{**reference[0], "price_low": "100.01"}]
    comparison = compare_claim_sets(
        label_family="swing",
        reference_claims=reference,
        production_claims=production,
    )
    assert comparison["status"] == "IMPLEMENTATION_CONFLICT"
    assert comparison["missing_from_production"]
    assert comparison["unexpected_from_production"]


def test_contract_does_not_call_ai_agreement_ground_truth():
    document = yaml.safe_load((ROOT / "specs" / "AUTONOMOUS_TRUTH_CONSTITUTION_V1.yaml").read_text())
    assert document["promotion_rules"]["majority_vote"] == "prohibited"
    assert "convert_ai_agreement_into_ground_truth" in document["non_goals"]


def test_multi_timeframe_bundle_exposes_scope_and_never_grants_trade_authority():
    frame = _fixture_frame().head(80)
    result = run_autonomous_conformance_bundle({"15m": frame}, market="SAMPLE")
    bundle = result["bundle"]
    assert bundle["status"] in {"DEFINITION_CONFORMANT", "BOUNDARY_SENSITIVE"}
    assert bundle["by_timeframe"]["15m"]["certificate"]["status"] in {
        "DEFINITION_CONFORMANT", "BOUNDARY_SENSITIVE"
    }
    assert bundle["authority_contract"]["structure_semantics_certified"] is False
    assert bundle["authority_contract"]["order_blocks_certified"] is False
    assert bundle["authority_contract"]["signal_allowed"] is False


def test_continuous_market_gap_fails_closed():
    frame = _fixture_frame().head(40).drop(index=20).reset_index(drop=True)
    decision_time = pd.Timestamp(frame.iloc[-1]["timestamp"]) + pd.Timedelta(minutes=15)
    with pytest.raises(ValueError, match="unexplained candle gap"):
        run_reference_oracle(
            frame, market="ETHUSDT", timeframe="15m", decision_time=decision_time,
            session_profile="continuous",
        )
    bundle = run_autonomous_conformance_bundle({"15m": frame}, market="ETHUSDT")["bundle"]
    assert bundle["status"] == "BLOCKED"
    assert bundle["by_timeframe"]["15m"]["certificate"]["status"] == "DATA_FAILED"


def test_declared_weekend_closure_is_allowed_but_midweek_gap_is_not():
    def row(timestamp: str) -> dict:
        return {
            "timestamp": timestamp, "open": 100.0, "high": 101.0,
            "low": 99.0, "close": 100.5, "volume": 10.0,
        }

    weekend = pd.DataFrame([
        row("2026-08-07T19:00:00Z"), row("2026-08-07T20:00:00Z"),
        row("2026-08-09T21:00:00Z"), row("2026-08-09T22:00:00Z"),
    ])
    result = run_reference_oracle(
        weekend, market="XAUUSD", timeframe="1h",
        decision_time="2026-08-09T23:00:00Z", session_profile="forex_5d",
    )
    assert result["claim_counts"]["swing"] == 0

    midweek = pd.DataFrame([
        row("2026-08-11T19:00:00Z"), row("2026-08-11T20:00:00Z"),
        row("2026-08-13T05:00:00Z"), row("2026-08-13T06:00:00Z"),
    ])
    with pytest.raises(ValueError, match="unexplained candle gap"):
        run_reference_oracle(
            midweek, market="XAUUSD", timeframe="1h",
            decision_time="2026-08-13T07:00:00Z", session_profile="forex_5d",
        )


def test_forex_bundle_certifies_latest_contiguous_segment_when_depth_survives():
    frame = _fixture_frame().head(90).drop(index=20).reset_index(drop=True)

    result = run_autonomous_conformance_bundle(
        {"15m": frame},
        market="USDCHF",
        session_profile="forex_5d",
        minimum_depths={"15m": 40},
    )["bundle"]

    preparation = result["input_preparation"]["15m"]
    assert preparation["status"] == "LATEST_CONTIGUOUS_SEGMENT"
    assert preparation["historical_gap_detected"] is True
    assert preparation["evaluated_rows"] == len(frame) - 20
    assert result["by_timeframe"]["15m"]["certificate"]["status"] in {
        "DEFINITION_CONFORMANT",
        "BOUNDARY_SENSITIVE",
    }


def test_forex_bundle_refuses_gap_trim_when_recent_segment_is_too_shallow():
    frame = _fixture_frame().head(90).drop(index=70).reset_index(drop=True)

    result = run_autonomous_conformance_bundle(
        {"15m": frame},
        market="USDCHF",
        session_profile="forex_5d",
        minimum_depths={"15m": 40},
    )["bundle"]

    assert result["input_preparation"]["15m"]["status"] == "TRIM_REFUSED_INSUFFICIENT_DEPTH"
    assert result["status"] == "BLOCKED"
    assert result["by_timeframe"]["15m"]["certificate"]["status"] == "DATA_FAILED"
