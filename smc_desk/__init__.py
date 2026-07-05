"""Core package for the smc-codex-desk workstation.

Import functions directly from their submodules to avoid eagerly loading
optional dependencies (e.g. yaml) at import time:

    from smc_desk.engine import analyze_dataframe, analyze_ohlcv
    from smc_desk.rules import RuleConfig, load_rule_config
"""
