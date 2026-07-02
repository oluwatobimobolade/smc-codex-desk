from __future__ import annotations

from pathlib import Path

import yaml
from yaml.constructor import ConstructorError


ROOT = Path(__file__).resolve().parents[1]


class _NoDuplicateKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping_no_duplicates(loader: _NoDuplicateKeyLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


def _load_yaml(path: str) -> dict:
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def test_governance_yaml_has_no_duplicate_keys() -> None:
    for path in (ROOT / "governance").glob("*.yaml"):
        with path.open("r", encoding="utf-8") as handle:
            yaml.load(handle, Loader=_NoDuplicateKeyLoader)


def test_required_governance_foundation_files_exist() -> None:
    required = [
        "governance/README_FIRST.md",
        "governance/CORE_MEMORY.md",
        "governance/CURRENT_STATE.yaml",
        "governance/CAPABILITY_MATRIX.yaml",
        "governance/DATASET_REGISTRY.yaml",
        "governance/AUTHORITY_MATRIX.yaml",
        "governance/NEXT_ACTIONS.yaml",
        "governance/DOCUMENT_INDEX.yaml",
        "governance/STRATEGY_TRUTH_AUDIT.md",
        "governance/STRATEGY_EVIDENCE_REGISTRY.yaml",
        "governance/STRATEGY_AUTHORITY_MATRIX.yaml",
        "governance/WORK_PACKAGES/WP-0001-COLLEAGUE-FOUNDATION/charter.md",
        "reports/current/ARCHITECTURE_CURRENT.md",
        "reports/current/ARCHITECTURE_TARGET.md",
        "reports/current/ONTOLOGY_CONFLICT_REPORT.md",
        "reports/current/LEGACY_DEPENDENCY_REPORT.md",
    ]

    missing = [path for path in required if not (ROOT / path).exists()]

    assert not missing


def test_current_state_keeps_execution_and_prediction_authority_disabled() -> None:
    state = _load_yaml("governance/CURRENT_STATE.yaml")

    assert state["project"]["release"] == "colleague-core-rc0"
    assert state["scope"]["certified_initial_scope"]["symbol"] == "BTCUSDT"
    assert state["authority"]["paper_execution"] == "disabled"
    assert state["authority"]["live_execution"] == "disabled"
    assert state["authority"]["prediction"] == "research_only"
    assert state["active_contracts"]["active_strategy_candidate"] == "RASC_SMC_V1"
    assert state["active_contracts"]["scenario_contract"] == "SCENARIO_CONTRACT_V1"
    assert state["active_contracts"]["decision_policy"] == "DECISION_POLICY_V1"


def test_active_strategy_candidate_is_research_only_and_zero_capital_risk() -> None:
    contract = _load_yaml("strategies/active/REGIME_ALIGNED_SMC_CONTINUATION_V1/STRATEGY_CONTRACT.yaml")
    risk = _load_yaml("strategies/active/REGIME_ALIGNED_SMC_CONTINUATION_V1/RISK_CONTRACT.yaml")

    assert contract["strategy"]["id"] == "RASC-SMC-V1"
    assert contract["strategy"]["status"] == "RESEARCH_CANDIDATE"
    assert contract["strategy"]["authority"] == "LIVE_SHADOW_ONLY"
    assert contract["strategy"]["live_capital_risk"] == 0
    assert contract["strategy"]["paper_execution_enabled"] is False
    assert contract["strategy"]["live_execution_enabled"] is False
    assert risk["research"]["capital_risk"] == 0
    assert risk["live_shadow"]["capital_risk"] == 0
    assert "automatic_2_percent_a_plus_risk" in risk["forbidden"]


def test_strategy_registry_classifies_all_required_initial_rules() -> None:
    registry = _load_yaml("governance/STRATEGY_EVIDENCE_REGISTRY.yaml")
    required_rule_ids = {
        "daily_4h_1h_alignment",
        "protected_structure",
        "internal_external_structure",
        "liquidity_sweeps",
        "displacement",
        "fvgs",
        "order_blocks",
        "premium_discount",
        "freshness_mitigation",
        "inducement",
        "sessions",
        "news_filters",
        "five_minute_confirmation",
        "fifteen_minute_confirmation",
        "fixed_3r_target",
        "liquidity_targets",
        "atr_stop_buffers",
        "confluence_scores",
        "risk_1pct_2pct",
        "fixed_holding_period",
        "retracement_entries",
        "market_on_close_entries",
        "state_machine_sequence",
        "vision_veto_downgrade",
        "ml_setup_scoring",
    }

    assert required_rule_ids.issubset(set(registry["rules"]))
    assert registry["rules"]["fixed_3r_target"]["status"] == "FAILED_OR_UNSUPPORTED"
    assert registry["rules"]["order_blocks"]["active_v1_policy"] == "excluded"
    assert registry["rules"]["displacement"]["active_v1_policy"] == "store_attributes_not_required_for_event_existence"


def test_dataset_registry_blocks_gold_or_performance_claims_for_local_lab() -> None:
    registry = _load_yaml("governance/DATASET_REGISTRY.yaml")
    lab = registry["datasets"]["LAB-20260625-100"]

    assert lab["frozen"] is False
    assert lab["reviewer_status"] == "unlabelled"
    assert "final_perception_accuracy_claims" in lab["prohibited_uses"]
    assert "prediction_training" in lab["prohibited_uses"]


def test_decision_policy_keeps_paper_execute_gate_disabled_until_validation() -> None:
    policy = _load_yaml("specs/DECISION_POLICY_V1.yaml")

    assert policy["paper_execute_gate"]["current_status"] == "disabled_until_validation"
    assert "SOURCE_MISMATCH" in policy["allowed_actions"]
    assert policy["downgrade_rules"]["source_mismatch"] == "SOURCE_MISMATCH"
