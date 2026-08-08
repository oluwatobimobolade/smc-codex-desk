from pathlib import Path

import pytest

from smc_desk.structure.constitution_v2 import load_constitution_v2


REQUIRED_EVENTS = {
    "INITIAL_DIRECTION_BREAK",
    "INTERNAL_CHOCH_BULLISH",
    "INTERNAL_CHOCH_BEARISH",
    "EXTERNAL_MSS_CANDIDATE_BULLISH",
    "EXTERNAL_MSS_CONFIRMED_BEARISH",
    "WICK_PROBE",
    "BREAKOUT_CANDIDATE",
    "ACCEPTED_BREAKOUT",
    "CONFIRMED_SWEEP",
    "UNRESOLVED",
}


def test_v2_is_hash_sealed_and_non_authoritative():
    constitution = load_constitution_v2()

    assert constitution.is_authoritative is False
    assert REQUIRED_EVENTS <= set(constitution.event_ontology)
    assert constitution.document["authority_contract"]["signal_allowed"] is False


def test_v2_separates_core_structure_from_execution_doctrine():
    document = load_constitution_v2().document
    layers = document["layers"]

    assert "ote" in layers["core_market_structure"]["excludes"]
    assert "ote" in layers["optional_ict_execution_doctrine"]["owns"]
    assert layers["strategy_timing_and_session_rules"]["authority"] == "strategy_module_only"


def test_v2_corrects_choch_mss_and_first_break_semantics():
    doctrine = load_constitution_v2().document["structure_doctrine"]

    assert doctrine["first_break"]["classification"] == "INITIAL_DIRECTION_BREAK"
    assert doctrine["scope"]["choch"] == "early_internal_opposite_transition"
    assert doctrine["scope"]["mss_candidate"] == "externally_meaningful_reversal_candidate"


def test_v2_requires_break_lifecycle_not_one_bar_label():
    lifecycle = load_constitution_v2().document["structure_doctrine"]["break_lifecycle"]

    assert lifecycle["probe_output"] == "WICK_PROBE"
    assert lifecycle["body_close_output"] == "BREAKOUT_CANDIDATE"
    assert "external_displacement_passed_when_external" in lifecycle["accepted_if"]
    assert "follow_through_or_valid_retest_within_confirmation_horizon" in lifecycle["accepted_if"]


def test_v2_rejects_tampered_or_authority_granting_document(tmp_path: Path):
    source = Path("specs/MARKET_STRUCTURE_CONSTITUTION_V2.yaml").read_text(encoding="utf-8")
    altered = tmp_path / "constitution.yaml"
    altered.write_text(source.replace("signal_allowed: false", "signal_allowed: true"), encoding="utf-8")
    seal = tmp_path / "constitution.sha256"
    from smc_desk.data.hashing import file_sha256
    seal.write_text(file_sha256(altered) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot grant"):
        load_constitution_v2(altered, seal)
