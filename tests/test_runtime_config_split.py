from __future__ import annotations

from smc_desk.rules import (
    DEFAULT_DETECTOR_CONFIG_PATH,
    DEFAULT_STRATEGY_CONFIG_PATH,
    LEGACY_MONOLITH_RULES_PATH,
    RUNTIME_CONFIG_SOURCE,
    RuleConfig,
    load_rule_config,
)


def test_default_rule_config_uses_split_runtime_source() -> None:
    config = RuleConfig()

    assert config.runtime_config_source == RUNTIME_CONFIG_SOURCE
    assert config.detector_config_id == "PERCEPTION_DETECTOR_CONFIG_V2"
    assert config.strategy_config_id == "STRATEGY_EXECUTION_CONFIG_V1"
    assert config.equal_level_tolerance_bps == 15.0
    assert config.risk_reward_floor == 3.0


def test_load_rule_config_without_path_uses_split_runtime_source() -> None:
    config = load_rule_config()

    assert config.runtime_config_source == RUNTIME_CONFIG_SOURCE
    assert config.detector_config_id == "PERCEPTION_DETECTOR_CONFIG_V2"
    assert config.strategy_config_id == "STRATEGY_EXECUTION_CONFIG_V1"


def test_load_rule_config_accepts_split_and_legacy_sources() -> None:
    detector_config = load_rule_config(str(DEFAULT_DETECTOR_CONFIG_PATH))
    strategy_config = load_rule_config(str(DEFAULT_STRATEGY_CONFIG_PATH))
    monolith_config = load_rule_config(str(LEGACY_MONOLITH_RULES_PATH))
    legacy_json_config = load_rule_config("strategies/smc/rules_widthfloor.json")

    assert detector_config.runtime_config_source == "detector_split_file_plus_default_strategy"
    assert strategy_config.runtime_config_source == "strategy_split_file_plus_default_detector"
    assert monolith_config.runtime_config_source == "compatibility_rule_file"
    assert legacy_json_config.runtime_config_source == "legacy_strategy_rule_file_adapter"
    assert legacy_json_config.min_poi_width_bps == 25.0
